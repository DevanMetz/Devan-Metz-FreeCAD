"""Rebuild a design with build123d, without the CAD skill or browser runtime.

Example: python export_design.py label_stand --set slot_gap=1.2
Writes STEP, STL, 3MF, and parameters to exports/<name> by default.
Reference assemblies produce STEP only; print their constituent parts.
"""
import argparse
import importlib.util
import json
from pathlib import Path

from build_collection import NAMES, ASSEMBLIES

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=NAMES+ASSEMBLIES)
    parser.add_argument("--set", action="append", default=[], metavar="NAME=JSON",
                        help="Override one parameter; repeat for more. Lists use JSON syntax.")
    parser.add_argument("--output-dir", type=Path, help="Default: exports/<name> under this collection.")
    args = parser.parse_args()
    overrides = {}
    for setting in args.set:
        try:
            key,value = setting.split("=",1)
            overrides[key] = json.loads(value)
        except ValueError:
            parser.error(f"Expected NAME=JSON, received {setting!r}.")
    spec = importlib.util.spec_from_file_location(args.name,ROOT/f"{args.name}.step.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    unknown = set(overrides)-set(module.PARAMETERS)
    if unknown:
        parser.error(f"Unknown parameter(s): {', '.join(sorted(unknown))}")
    parameters = module.PARAMETERS | overrides
    try:
        shape = module.build(**parameters)
    except (ValueError,TypeError) as error:
        parser.error(str(error))
    printable = args.name in NAMES
    solids = shape.solids()
    if not shape.is_valid or not solids or any(s.volume <= 0 for s in solids):
        raise RuntimeError("Source did not produce valid, positive-volume solids.")
    if printable and (len(solids) != 1 or abs(shape.bounding_box().min.Z) > 1e-6):
        raise RuntimeError("A print file must have one solid and its bed at Z=0.")
    # Importing here keeps --help available without loading the CAD kernel.
    from build123d import Mesher, Unit, export_step
    output = args.output_dir or ROOT/"exports"/args.name
    output.mkdir(parents=True,exist_ok=True)
    if not export_step(shape,output/f"{args.name}.step"):
        raise RuntimeError("STEP export failed.")
    formats = ["step"]
    if printable:
        mesh = Mesher(unit=Unit.MM)
        mesh.add_shape(solids[0],linear_deflection=.01,angular_deflection=.05)
        for extension in ("stl","3mf"):
            mesh.write(output/f"{args.name}.{extension}")
            formats.append(extension)
    record = dict(model=args.name,parameters=parameters,units="mm",printable=printable,
                  solid_count=len(solids),bounds_mm=list(shape.bounding_box().size),
                  volume_mm3=shape.volume,formats=formats,physical_print_tested=False)
    (output/"parameters.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
    print(f"Exported {args.name}: {', '.join(formats)} to {output.resolve()}")


if __name__ == "__main__":
    main()
