"""Mesh quiver chassis STEP files and compare four linear-elastic load cases."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
GMSH = Path(r"C:\Program Files\FreeCAD 1.1\bin\gmsh.exe")
CCX = Path(r"C:\Program Files\FreeCAD 1.1\bin\ccx.exe")
E_MPA, NU = 2050.0, 0.38


def mesh_step(label: str, step: Path) -> Path:
    mesh = ROOT / f"{label}_mesh.inp"
    subprocess.run(
        [str(GMSH), str(step), "-3", "-format", "inp", "-o", str(mesh), "-clmax", "5", "-clmin", "2.5", "-v", "1"],
        check=True,
    )
    return mesh


def read_mesh(path: Path):
    nodes, elements = {}, []
    section = None
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        upper = line.upper()
        if upper.startswith("*NODE"):
            section = "nodes"
            continue
        if upper.startswith("*ELEMENT"):
            section = "tetra" if "TYPE=C3D4" in upper else None
            continue
        if line.startswith("*"):
            section = None
            continue
        if section == "nodes" and line:
            values = [value.strip() for value in line.split(",")]
            nodes[int(values[0])] = tuple(map(float, values[1:4]))
        elif section == "tetra" and line:
            values = [int(value.strip()) for value in line.split(",") if value.strip()]
            elements.append(values)
    if not nodes or not elements:
        raise RuntimeError(f"No solid mesh in {path}")
    return nodes, elements


def ids_block(ids):
    ids = list(ids)
    return "\n".join(", ".join(map(str, ids[index : index + 16])) for index in range(0, len(ids), 16))


def write_case(label, case, nodes, elements, fixed, loaded, direction, total_force, opposed=None):
    job = ROOT / f"{label}_{case}"
    lines = ["*HEADING", f"{label} / {case}", "*NODE"]
    lines.extend(f"{number}, {x:.9g}, {y:.9g}, {z:.9g}" for number, (x, y, z) in nodes.items())
    lines.append("*ELEMENT, TYPE=C3D4, ELSET=SOLID")
    lines.extend(", ".join(map(str, element)) for element in elements)
    lines.extend(["*NSET, NSET=FIXED", ids_block(fixed), "*MATERIAL, NAME=PETG_HF", "*ELASTIC", f"{E_MPA}, {NU}", "*SOLID SECTION, ELSET=SOLID, MATERIAL=PETG_HF", "*STEP", "*STATIC", "*BOUNDARY", "FIXED, 1, 3"])
    lines.append("*CLOAD")
    force = total_force / len(loaded)
    lines.extend(f"{number}, {direction}, {force:.9g}" for number in loaded)
    if opposed:
        opposed_ids, opposed_force = opposed
        force = opposed_force / len(opposed_ids)
        lines.extend(f"{number}, {direction}, {force:.9g}" for number in opposed_ids)
    lines.extend(["*NODE FILE", "U", "*EL FILE", "S", "*END STEP", ""])
    job.with_suffix(".inp").write_text("\n".join(lines), encoding="ascii")
    subprocess.run([str(CCX), job.name], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    return job


def von_mises(stress):
    sx, sy, sz, txy, txz, tyz = stress
    return math.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (txy**2 + txz**2 + tyz**2))


def read_frd_fields(path: Path):
    """Read the DISP and STRESS result blocks emitted by this screening deck."""
    fields = {"DISP": {}, "STRESS": {}}
    active = None
    for raw in path.read_text(encoding="ascii", errors="ignore").splitlines():
        if raw.startswith(" -4  DISP"):
            active = "DISP"
            continue
        if raw.startswith(" -4  STRESS"):
            active = "STRESS"
            continue
        if raw.startswith(" -3") or raw.startswith(" 9999"):
            active = None
            continue
        if active and raw.startswith(" -1"):
            node = int(raw[3:13])
            count = 3 if active == "DISP" else 6
            fields[active][node] = tuple(
                float(raw[13 + 12 * index : 13 + 12 * (index + 1)])
                for index in range(count)
            )
    if not fields["DISP"] or not fields["STRESS"]:
        raise RuntimeError(f"Missing result fields in {path}")
    return fields


def collect(job: Path, loaded):
    result = read_frd_fields(job.with_suffix(".frd"))
    disp = result["DISP"]
    stress = result["STRESS"]
    loaded_disp = [math.sqrt(sum(value * value for value in disp[number])) for number in loaded if number in disp]
    equivalent = np.fromiter((von_mises(value) for value in stress.values()), dtype=float)
    return {
        "max_loaded_displacement_mm": max(loaded_disp),
        "max_von_mises_MPa": float(equivalent.max()),
        "p99_von_mises_MPa": float(np.percentile(equivalent, 99)),
        "p95_von_mises_MPa": float(np.percentile(equivalent, 95)),
        "result_nodes": len(disp),
    }


def analyze(label: str, step: Path):
    mesh = mesh_step(label, step)
    nodes, elements = read_mesh(mesh)
    max_z = max(z for _, _, z in nodes.values())
    # Fix only the rear bow-side plate.  Using y alone also selected the basket
    # rear wall after the shell refinement, artificially clamping the load end.
    fixed = [
        number
        for number, (x, y, z) in nodes.items()
        if abs(x) <= 21.5 and -20.0 <= y <= -13.4 and 68 <= z <= 140
    ]
    # Load a representative rear basket band instead of the entire top rim;
    # distributing a nodal force over unrelated disconnected rim loops creates
    # point singularities that dominate a coarse first-order tetra mesh.
    top = [
        number
        for number, (x, y, z) in nodes.items()
        if abs(x) <= 48 and y <= -8 and z >= max_z - 8
    ]
    bottom = [number for number, (_, _, z) in nodes.items() if z <= 0.5]
    if min(map(len, (fixed, top, bottom))) == 0:
        raise RuntimeError(f"Empty selection: fixed={len(fixed)}, top={len(top)}, bottom={len(bottom)}")
    cases = {
        "upper_lateral_250N": (top, 1, 250.0, None),
        "upper_fore_aft_250N": (top, 2, 250.0, None),
        "lower_lateral_150N": (bottom, 1, 150.0, None),
        "mount_moment_12Nm": (top, 2, 12000.0 / max_z, (bottom, -12000.0 / max_z)),
    }
    report = {"mesh_nodes": len(nodes), "mesh_tetrahedra": len(elements), "fixed_nodes": len(fixed), "cases": {}}
    for name, (loaded, direction, force, opposed) in cases.items():
        job = write_case(label, name, nodes, elements, fixed, loaded, direction, force, opposed)
        report["cases"][name] = collect(job, loaded)
    return report


def plot_results(report):
    designs = report["designs"]
    if not designs:
        return
    label, design = next(iter(designs.items()))
    cases = list(design["cases"])
    labels = ["Upper\nlateral", "Upper\nfore-aft", "Lower\nlateral", "12 N-m\nmoment"]
    x = np.arange(len(cases))
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
    for axis, metric, ylabel, title in (
        (axes[0], "max_loaded_displacement_mm", "maximum loaded displacement (mm)", "Displacement screening"),
        (axes[1], "p95_von_mises_MPa", "95th-percentile von Mises stress (MPa)", "Stress screening"),
    ):
        values = [design["cases"][case][metric] for case in cases]
        axis.bar(x, values, width=0.58, label=label, color="#365d73")
        axis.set_xticks(x, labels)
        axis.set_ylabel(ylabel)
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.2)
    axes[1].axhline(34, color="#9c4f3d", linestyle="--", linewidth=1.2, label="published tensile strength")
    axes[0].legend()
    axes[1].legend()
    fig.suptitle("Compact FDM LIFT X quiver — CalculiX screening model")
    fig.tight_layout()
    fig.savefig(ROOT / "spine_fea_screening.png", dpi=220)
    plt.close(fig)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: freecadcmd solid_spine_fea.py label=chassis.step [...]")
    report = {
        "basis": {
            "solver": "CalculiX linear static / Gmsh C3D4 mesh",
            "material": "Bambu PETG-HF",
            "elastic_modulus_MPa": E_MPA,
            "poisson_ratio_assumed": NU,
            "warning": "Screening model only; printed-part allowables and boundary conditions require physical correlation.",
        },
        "designs": {},
    }
    for value in sys.argv[1:]:
        label, filename = value.split("=", 1)
        report["designs"][label] = analyze(label, Path(filename).resolve())
    plot_results(report)
    (ROOT / "solid_fea_results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
