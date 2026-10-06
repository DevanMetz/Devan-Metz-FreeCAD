"""Bounded CAD job process. Only the shipped model manifest may select a source."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent


def validate(payload, manifest):
    if not isinstance(payload, dict) or set(payload) - {"model", "parameters", "format"}:
        raise ValueError("Expected a model name and a parameters object.")
    if payload.get("format", "stl") not in ("stl", "cad"):
        raise ValueError("Choose STL or CAD format.")
    name = payload.get("model")
    if not isinstance(name, str) or name not in manifest:
        raise ValueError("Unknown model.")
    overrides = payload.get("parameters", {})
    if not isinstance(overrides, dict) or set(overrides) - set(manifest[name]["defaults"]):
        raise ValueError("Unknown parameter. Use only the fields shown for this model.")
    parameters = manifest[name]["defaults"] | overrides
    for key, value in parameters.items():
        default = manifest[name]["defaults"][key]
        if isinstance(default, list):
            if not isinstance(value, list) or not 1 <= len(value) <= 16:
                raise ValueError(f"{key} must be a list of 1 to 16 numbers.")
            values = value
        else:
            if type(default) is int and (type(value) not in (int, float) or not float(value).is_integer()):
                raise ValueError(f"{key} must be an integer.")
            values = [value]
        if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1000 for v in values):
            raise ValueError(f"{key} must contain finite numbers between -1000 and 1000.")
        if type(default) is int:
            parameters[key] = int(value)
    return name, parameters


def build_shape(name, parameters, printable):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.step.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    shape = module.build(**parameters)
    solids = shape.solids()
    if not shape.is_valid or not solids or any(s.volume <= 0 for s in solids):
        raise ValueError("These parameters did not produce valid solid geometry.")
    if printable and (len(solids) != 1 or abs(shape.bounding_box().min.Z) > 1e-6):
        raise ValueError("The result must be one connected solid with its print bed at Z=0.")
    return shape


def cad_archive(name, shape, mesh, metadata, manifest, directory):
    """Preserve exact solids, one print tessellation, and portable parameter edits."""
    from build123d import export_step
    step = directory / f"{name}.step"
    if not export_step(shape, step):
        raise ValueError("The STEP export could not be written.")
    files = {step.name: step.read_bytes()}
    if metadata["printable"]:
        files[f"{name}.stl"] = (directory / "model.stl").read_bytes()
        mesh.write(directory / f"{name}.3mf")
        files[f"{name}.3mf"] = (directory / f"{name}.3mf").read_bytes()
    else:
        for part in metadata["kit"]:
            model = part["model"]
            if model not in manifest or manifest[model]["kind"] != "print":
                raise ValueError("The kit contains an unsupported print component.")
            defaults = manifest[model]["defaults"]
            shared = {key: value for key, value in metadata["parameters"].items() if key in defaults}
            # The normal generator applies defaults, type guards, solid checks,
            # and the same tessellation to every separately printable component.
            part_directory = directory / "parts" / model
            part_directory.mkdir(parents=True)
            generate(dict(model=model, parameters=shared), part_directory, include_step=True)
            part_metadata = json.loads((part_directory / "metadata.json").read_text())
            for extension, path in (("step", f"{model}.step"), ("stl", "model.stl"), ("3mf", f"{model}.3mf")):
                files[f"parts/{model}/{model}.{extension}"] = (part_directory / path).read_bytes()
            part_metadata.update(quantity=part["quantity"], role=part["role"])
            files[f"parts/{model}/parameters.json"] = json.dumps(part_metadata, indent=2).encode("utf-8")
    sources = {f"{model}.step.py" for model in [name, *manifest[name].get("parts", [])]}
    sources.update(path.name for path in ROOT.glob("*_common.py"))
    for source in sorted(sources):
        files[f"sources/{source}"] = (ROOT / source).read_bytes()
    for filename in ("LICENSE", "NOTICE", "rebuild.py"):
        files[filename] = (ROOT / filename).read_bytes()
    files["requirements.txt"] = b"build123d==0.11.1\ncadgen==0.4.4\n"
    files["parameters.json"] = json.dumps(metadata, indent=2).encode("utf-8")
    files["README.md"] = (f"# {name} — saved CAD dimensions\n\n"
        "All dimensions are in millimeters. STEP contains the editable solid geometry; "
        "parameters.json records the applied dimensions.\n\n"
        + ("The STL is the exact verified preview mesh. 3MF uses the same tessellation and millimeter units.\n\n"
           if metadata["printable"] else "The root STEP is a reference assembly. Print the files in parts/ separately in their saved bed orientation. "
           "Illustrative hardware is excluded; there is no combined assembly print mesh.\n\n"
           + "| Part | Quantity | Use |\n| --- | ---: | --- |\n"
           + "".join(f"| {part['model']} | {part['quantity']} | {'Fit coupon — test before full parts' if part['role'] == 'fit_coupon' else 'Assembly component'} |\n" for part in metadata["kit"])
           + "\nEach folder contains STEP, STL, 3MF, and its applied parameters. Print the indicated number of copies; repeated parts share one file.\n\n")
        + "To rebuild with Python, install the pinned dependencies in a virtual environment:\n\n"
        "```text\npython -m pip install -r requirements.txt\npython rebuild.py\n```\n\n"
        "Edit the parameters object in parameters.json and run rebuild.py again. "
        "Outputs go to rebuilt/ beside this file. Canonical source and shared helpers are in sources/. "
        "The source defaults describe the original design; rebuild.py applies your saved dimensions. "
        "Assembly rebuilds also regenerate the kit's components, sharing the changed dimensions with each part.\n\n"
        "SHA256SUMS.json verifies all supplied files. Apache-2.0 licensing applies. "
        "Physical printing and performance have not been tested.\n").encode("utf-8")
    if sum(map(len, files.values())) > 24 * 1024 * 1024:
        raise ValueError("The CAD download is too large. Reduce the repeated features.")
    checksums = {path: hashlib.sha256(body).hexdigest() for path, body in files.items()}
    files["SHA256SUMS.json"] = json.dumps(checksums, indent=2).encode("utf-8")
    output = directory / "model.zip"
    with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        for path, body in files.items():
            archive.writestr(path, body)
    return output


def generate(payload, directory, include_step=False):
    manifest = json.loads((ROOT / "manifest.json").read_text())
    name, parameters = validate(payload, manifest)
    printable = manifest[name]["kind"] == "print"
    shape = build_shape(name, parameters, printable)
    from build123d import Mesher, Unit
    mesh = Mesher(unit=Unit.MM)
    mesh.add_shape(shape, linear_deflection=.01, angular_deflection=.05)
    output = directory / "model.stl"
    mesh.write(output)
    if output.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("The mesh is too large. Reduce the number of repeated features.")
    metadata = dict(model=name, parameters=parameters, units="mm", printable=printable,
                    bounds_mm=list(shape.bounding_box().size), volume_mm3=shape.volume,
                    solid_count=len(shape.solids()), physical_print_tested=False,
                    mesh_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    if include_step:
        from build123d import export_step
        if not printable or not export_step(shape, directory / f"{name}.step"):
            raise ValueError("The component STEP export could not be written.")
        mesh.write(directory / f"{name}.3mf")
    metadata["format"] = payload.get("format", "stl")
    if metadata["format"] == "cad":
        metadata["kit"] = manifest[name]["kit"]
        output = cad_archive(name, shape, mesh, metadata, manifest, directory)
    if output.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("The download is too large. Reduce the repeated features.")
    metadata["file_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return output


if __name__ == "__main__":
    try:
        generate(json.loads(sys.stdin.read(16385)), Path(sys.argv[1]))
    except (ValueError, TypeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
    except Exception as error:
        # Return geometry failures without exposing filesystem paths or source internals.
        print(json.dumps({"error": "The CAD builder could not construct this combination. Adjust the parameters."}))
        print(type(error).__name__, file=sys.stderr)
        sys.exit(3)
