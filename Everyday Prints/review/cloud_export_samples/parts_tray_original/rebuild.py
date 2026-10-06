"""Rebuild the saved dimensions from the CAD download's canonical sources."""
import importlib.util
import json
from pathlib import Path
import sys


def load_source(name, sources):
    if not isinstance(name, str) or not name.replace("_", "").isalnum():
        raise ValueError("Invalid model name in parameters.json.")
    spec = importlib.util.spec_from_file_location(name, sources / f"{name}.step.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export_model(name, parameters, sources, output, *, inventory=None):
    # Canonical assembly names identify references; editing the metadata cannot
    # turn a reference assembly into a supported print file.
    printable = not name.endswith("_assembly")
    shape = load_source(name, sources).build(**parameters)
    solids = shape.solids()
    if not shape.is_valid or not solids or any(solid.volume <= 0 for solid in solids):
        raise ValueError("These parameters did not produce valid solid geometry.")
    if printable and (len(solids) != 1 or abs(shape.bounding_box().min.Z) > 1e-6):
        raise ValueError("A print file must have one solid with its bed at Z=0.")
    from build123d import export_step, Mesher, Unit
    output.mkdir(parents=True, exist_ok=True)
    if not export_step(shape, output / f"{name}.step"):
        raise ValueError("STEP export failed.")
    if printable:
        mesh = Mesher(unit=Unit.MM)
        mesh.add_shape(shape, linear_deflection=.01, angular_deflection=.05)
        for extension in ("stl", "3mf"):
            mesh.write(output / f"{name}.{extension}")
    saved = dict(model=name, parameters=parameters, units="mm", printable=printable,
        bounds_mm=list(shape.bounding_box().size), volume_mm3=shape.volume,
        solid_count=len(solids), physical_print_tested=False)
    saved.update(inventory or {})
    (output / "parameters.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")


def main():
    root = Path(__file__).resolve().parent
    record = json.loads((root / "parameters.json").read_text(encoding="utf-8"))
    name = record["model"]
    sources = root / "sources"
    sys.path.insert(0, str(sources))
    output = root / "rebuilt"
    export_model(name, record["parameters"], sources, output,
        inventory={"kit": record.get("kit", [])})
    if name.endswith("_assembly"):
        for part in record.get("kit", []):
            model = part["model"]
            if model.endswith("_assembly"):
                raise ValueError("A kit component must be a printable part.")
            defaults = load_source(model, sources).PARAMETERS
            shared = {key: value for key, value in record["parameters"].items() if key in defaults}
            export_model(model, defaults | shared, sources, output / "parts" / model,
                inventory={"quantity": part["quantity"], "role": part["role"]})
        print("Rebuilt kit quantities:", ", ".join(f"{part['model']} x{part['quantity']}" for part in record.get("kit", [])))
    print(f"Rebuilt {name} with the saved parameters in {output}")


if __name__ == "__main__":
    main()
