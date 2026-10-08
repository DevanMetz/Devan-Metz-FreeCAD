"""Prepare the hosted catalog from the canonical collection; run with its CAD venv.

No second set of model definitions: the server executes these exact Python sources.
"""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
sys.path.insert(0, str(ROOT))
from make_index import catalog

PARTS = {
    "soap_dish_assembly": ["soap_dish_tray", "soap_dish_insert"],
    "sanding_assembly": ["sanding_block", "sanding_wedge"],
    "sliding_box_assembly": ["sliding_box", "sliding_lid", "sliding_fit_channel", "sliding_fit_slider"],
    "ruler_stop_assembly": ["ruler_stop", "ruler_wedge"],
    "strap_clamp_assembly": ["strap_corner"],
    "divider_joint_assembly": ["divider_joint"],
}
PART_COUNTS = {"sanding_wedge": 2, "strap_corner": 4}
FIT_COUPONS = {"sliding_fit_channel", "sliding_fit_slider"}
SYNONYMS = {
    "parts_tray": "organizer storage screws nuts bolts bin compartments drawer",
    "cable_comb": "wire organizer cable management desk",
    "divider_foot": "drawer partition board organizer",
    "phone_stand": "mobile smartphone desk holder dock",
    "hex_bit_rack": "screwdriver drill tool holder storage organizer",
    "cable_grommet": "desk wire pass through hole cable management",
    "sliding_box": "storage container enclosure case organizer",
    "hand_knob": "nut bolt grip handle fastener",
    "bookend": "books shelf support library",
    "plant_marker": "garden gardening label tag seed pot",
    "sorting_sieve": "sifting sorting screen filter garden",
    "tube_reducer": "hose pipe connector adapter tubing",
    "soap_dish_tray": "bathroom sink drain holder",
    "workshop_funnel": "pour filling liquid transfer",
    "strap_corner": "frame woodworking clamp band corner",
    "divider_joint": "drawer partition board organizer cross connector",
}


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.step.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def numeric(node):
    try:
        value = ast.literal_eval(node)
        return value if type(value) in (int, float) else None
    except (ValueError, TypeError):
        return None


def key(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "p":
        return node.slice.value if isinstance(node.slice, ast.Constant) else None
    return None


def hints(name, defaults):
    ranges = {k: {} for k in defaults}
    texts = [(ROOT / f"{name}.step.py").read_text(encoding="utf-8")]
    # Shared settings hold the guards for paired parts and their reference assemblies.
    for group in ("soap_dish", "sanding", "sliding_box", "ruler_stop", "strap_corner", "divider_joint"):
        if f"from {group}_common import" in texts[0]:
            texts.append((ROOT / f"{group}_common.py").read_text(encoding="utf-8"))
    for text in texts:
        for comparison in (node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Compare)):
            operands = [comparison.left] + comparison.comparators
            for left, operation, right in zip(operands, comparison.ops, operands[1:]):
                lkey, rkey, lnum, rnum = key(left), key(right), numeric(left), numeric(right)
                if lnum is not None and rkey in ranges and isinstance(operation, (ast.Lt, ast.LtE)):
                    ranges[rkey]["min"] = max(ranges[rkey].get("min", -1000), lnum)
                elif rnum is not None and lkey in ranges and isinstance(operation, (ast.Lt, ast.LtE)):
                    ranges[lkey]["max"] = min(ranges[lkey].get("max", 1000), rnum)
    result = []
    for name, default in defaults.items():
        sequence = isinstance(default, (list, tuple))
        integer = type(default) is int
        units = "degrees" if "angle" in name or name == "ports" else ("" if integer else "mm")
        result.append(dict(key=name, label=name.replace("_", " ").capitalize(), default=default,
                           type="list" if sequence else "integer" if integer else "number",
                           unit=units, step=1 if integer or units == "degrees" else .1,
                           **({} if sequence else ranges[name])))
    return result


def main():
    public = CLOUD / "public"
    generated = CLOUD / "src/generated"
    for directory in (public / "images", public / "models", public / "sources", generated):
        directory.mkdir(parents=True, exist_ok=True)
    items = catalog()
    bundle = {}
    for path in sorted([*ROOT.glob("*.step.py"), *ROOT.glob("*_common.py")]):
        bundle[path.name] = path.read_text(encoding="utf-8")
        shutil.copy2(path, public / "sources" / path.name)
    for path in sorted((CLOUD / "runtime").glob("*.py")):
        bundle[path.name] = path.read_text(encoding="utf-8")
    for filename in ("LICENSE", "NOTICE"):
        bundle[filename] = (ROOT / filename).read_text(encoding="utf-8")
    manifest = {}
    for item in items:
        name = item["name"]
        module = load(name)
        params = json.loads(json.dumps(module.PARAMETERS))
        item["parameters"] = hints(name, params)
        item["defaults"] = params
        item["tags"] = SYNONYMS.get(name, "")
        item["parts"] = PARTS.get(name, [])
        item["kit"] = [dict(model=part, quantity=PART_COUNTS.get(part, 1),
                            role="fit_coupon" if part in FIT_COUPONS else "component")
                       for part in item["parts"]]
        image = public / "images" / f"{name}.png"
        shutil.copy2(ROOT / item["images"][0], image)
        item["image"] = f"/images/{name}.png"
        item.pop("images")
        item.pop("files")
        facts = json.loads((ROOT / f"review/{name}.facts.json").read_text(encoding="utf-8-sig"))
        item["bounds_mm"] = facts["tokens"][0]["entryFacts"]["size"]
        preview = public / "models" / f"{name}.stl"
        if item["kind"] == "print":
            for extension in ("stl", "3mf", "step"):
                shutil.copy2(ROOT / f"{name}.{extension}", public / "models" / f"{name}.{extension}")
        else:
            # STL is only a browser visualization of an assembly, never offered as a print.
            from build123d import Mesher, Unit
            mesh = Mesher(unit=Unit.MM)
            mesh.add_shape(module.build(**params), linear_deflection=.01, angular_deflection=.05)
            mesh.write(preview)
            shutil.copy2(ROOT / f"{name}.step", public / "models" / f"{name}.step")
        item["mesh"] = f"/models/{name}.stl"
        item["mesh_sha256"] = hashlib.sha256(preview.read_bytes()).hexdigest()
        item["source"] = f"/sources/{name}.step.py"
        manifest[name] = dict(defaults=params, kind=item["kind"], parts=item["parts"], kit=item["kit"],
                              integer_parameters=[key for key, value in module.PARAMETERS.items() if type(value) is int])
    manifest_text = json.dumps(manifest, separators=(",", ":"), sort_keys=True)
    bundle["manifest.json"] = manifest_text
    version = hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()[:16]
    payload = dict(version=version, files=bundle, manifest=manifest)
    (generated / "runtime.json").write_text(json.dumps(payload), encoding="utf-8")
    local_runtime = ROOT.parent / ".cad-cache/cloud-runtime"
    local_runtime.mkdir(parents=True, exist_ok=True)
    for name, text in bundle.items():
        (local_runtime / name).write_text(text, encoding="utf-8")
    (local_runtime / "version.txt").write_text(version, encoding="utf-8")
    (public / "catalog.json").write_text(json.dumps(dict(version=version, models=items)), encoding="utf-8")
    for filename in ("LICENSE", "NOTICE", "README.md"):
        shutil.copy2(ROOT / filename, public / filename)
    shutil.copy2(CLOUD / "THIRD_PARTY_NOTICES.md", public / "THIRD_PARTY_NOTICES.md")
    print(f"Prepared {len(items)} models, {len(bundle)} source files; runtime {version}.")


if __name__ == "__main__":
    main()
