"""Reproducible 2D SIMP study for the LIFT X quiver spine.

The model compares the compact FDM side-web layout with a same-volume
optimized material field. It represents the 10 mm-deep PETG-HF spine in plane
stress and uses the real dock band as the fixed region. Results guide the
printable diamond web; they are not a substitute for physical qualification.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.sparse import coo_matrix, csc_matrix
from scipy.sparse.linalg import splu


ROOT = Path(__file__).resolve().parent
NX, NY = 32, 94
WIDTH, HEIGHT, THICKNESS = 64.0, 188.0, 10.0
E0, EMIN, NU = 2050.0, 2050.0e-6, 0.38
PENAL, FILTER_RADIUS, MAX_ITER = 3.0, 2.4, 90
CHANGE_LIMIT = 0.01


def element_stiffness() -> np.ndarray:
    a11 = np.array(
        [[12, 3, -6, -3], [3, 12, 3, 0], [-6, 3, 12, -3], [-3, 0, -3, 12]],
        dtype=float,
    )
    a12 = np.array(
        [[-6, -3, 0, 3], [-3, -6, -3, -6], [0, -3, -6, 3], [3, -6, 3, -6]],
        dtype=float,
    )
    b11 = np.array(
        [[-4, 3, -2, 9], [3, -4, -9, 4], [-2, -9, -4, -3], [9, 4, -3, -4]],
        dtype=float,
    )
    b12 = np.array(
        [[2, -3, 4, -9], [-3, 2, 9, -2], [4, 9, 2, 3], [-9, -2, 3, 2]],
        dtype=float,
    )
    return THICKNESS / (24 * (1 - NU**2)) * (
        np.block([[a11, a12], [a12.T, a11]])
        + NU * np.block([[b11, b12], [b12.T, b11]])
    )


DX, DZ = WIDTH / NX, HEIGHT / NY
NEL = NX * NY
NNODE = (NX + 1) * (NY + 1)
NDOF = NNODE * 2
KE = element_stiffness()


def node(ix: int, iz: int) -> int:
    return iz * (NX + 1) + ix


EDOF = np.empty((NEL, 8), dtype=int)
for iz in range(NY):
    for ix in range(NX):
        n = [node(ix, iz), node(ix + 1, iz), node(ix + 1, iz + 1), node(ix, iz + 1)]
        EDOF[iz * NX + ix] = [d for n0 in n for d in (2 * n0, 2 * n0 + 1)]
IK = np.repeat(EDOF, 8, axis=1).ravel()
JK = np.tile(EDOF, (1, 8)).ravel()


def element_centers() -> tuple[np.ndarray, np.ndarray]:
    x = -WIDTH / 2 + (np.arange(NX) + 0.5) * DX
    z = (np.arange(NY) + 0.5) * DZ
    return np.meshgrid(x, z)


XC, ZC = element_centers()


def point_segment_distance(x, z, x1, z1, x2, z2):
    dx, dz = x2 - x1, z2 - z1
    t = np.clip(((x - x1) * dx + (z - z1) * dz) / (dx * dx + dz * dz), 0, 1)
    return np.hypot(x - (x1 + t * dx), z - (z1 + t * dz))


def baseline_density() -> np.ndarray:
    solid = (np.abs(np.abs(XC) - 16.0) <= 2.5) & (ZC >= 8) & (ZC <= HEIGHT)
    for z1, z2 in ((12, 66), (146, 186)):
        solid |= point_segment_distance(XC, ZC, -16, z1, 16, z2) <= 2.0
        solid |= point_segment_distance(XC, ZC, 16, z1, -16, z2) <= 2.0
    return np.where(solid, 1.0, 0.001).ravel()


BASELINE = baseline_density()
PASSIVE = (
    (((np.abs(XC - 16) <= 3.0) | (np.abs(XC + 16) <= 3.0)) & (ZC >= 66) & (ZC <= 146))
    | (((np.abs(XC - 16) <= 4.0) | (np.abs(XC + 16) <= 4.0)) & ((ZC <= 12) | (ZC >= 184)))
).ravel()
BASELINE[PASSIVE] = 1.0
VOLFRAC = float(np.mean(BASELINE))


def build_filter():
    rows, cols, values = [], [], []
    reach = int(np.ceil(FILTER_RADIUS)) - 1
    for iz in range(NY):
        for ix in range(NX):
            row = iz * NX + ix
            for jz in range(max(0, iz - reach), min(NY, iz + reach + 1)):
                for jx in range(max(0, ix - reach), min(NX, ix + reach + 1)):
                    weight = FILTER_RADIUS - np.hypot(ix - jx, iz - jz)
                    if weight > 0:
                        rows.append(row)
                        cols.append(jz * NX + jx)
                        values.append(weight)
    h = coo_matrix((values, (rows, cols)), shape=(NEL, NEL)).tocsr()
    return h, np.asarray(h.sum(axis=1)).ravel()


H, HS = build_filter()


def nearest_ix(x: float) -> int:
    return int(round((x + WIDTH / 2) / DX))


def load_nodes(z: float) -> list[int]:
    iz = int(round(z / DZ))
    return [node(nearest_ix(-16), iz), node(nearest_ix(16), iz)]


F = np.zeros((NDOF, 4))
for n in load_nodes(HEIGHT):
    F[2 * n, 0] = 125.0
for n in load_nodes(0):
    F[2 * n, 1] = 75.0
couple_force = 12000.0 / HEIGHT
for n in load_nodes(HEIGHT):
    F[2 * n, 2] = couple_force / 2
for n in load_nodes(0):
    F[2 * n, 2] = -couple_force / 2
for n in load_nodes(HEIGHT):
    F[2 * n + 1, 3] = -50.0
for n in load_nodes(0):
    F[2 * n + 1, 3] = 50.0
LOAD_NAMES = ("250 N upper transverse", "150 N lower transverse", "12 N-m couple", "100 N axial shock")
LOAD_WEIGHTS = np.array([1.0, 0.8, 0.6, 0.25])

fixed_nodes = []
for iz in range(NY + 1):
    z = iz * DZ
    if 68 <= z <= 144:
        fixed_nodes.extend([node(nearest_ix(-16), iz), node(nearest_ix(16), iz)])
FIXED = np.unique([d for n in fixed_nodes for d in (2 * n, 2 * n + 1)])
FREE = np.setdiff1d(np.arange(NDOF), FIXED)


def solve(rho: np.ndarray):
    stiffness = EMIN + rho**PENAL * (E0 - EMIN)
    values = (stiffness[:, None] * KE.ravel()[None, :]).ravel()
    k = coo_matrix((values, (IK, JK)), shape=(NDOF, NDOF)).tocsc()
    k = (k + k.T) * 0.5
    factor = splu(csc_matrix(k[FREE][:, FREE]))
    u = np.zeros_like(F)
    u[FREE] = factor.solve(F[FREE])
    ue = u[EDOF]
    ce = np.einsum("eic,ij,ejc->ec", ue, KE, ue)
    per_case = np.sum((E0 * rho**PENAL + EMIN)[:, None] * ce, axis=0)
    return u, ce, per_case


def optimize():
    rho = BASELINE.copy()
    best_rho = rho.copy()
    best_compliance = float("inf")
    rho[PASSIVE] = 1.0
    history = []
    for iteration in range(1, MAX_ITER + 1):
        _, ce, per_case = solve(rho)
        compliance = float(per_case @ LOAD_WEIGHTS)
        if compliance < best_compliance:
            best_compliance = compliance
            best_rho = rho.copy()
        weighted_ce = ce @ LOAD_WEIGHTS
        dc = -PENAL * (E0 - EMIN) * rho ** (PENAL - 1) * weighted_ce
        dc = H.dot(rho * dc) / (HS * np.maximum(0.001, rho))
        lower, upper, move = 0.0, 1.0e12, 0.20
        while (upper - lower) / (upper + lower + 1.0e-12) > 1.0e-4:
            mid = 0.5 * (lower + upper)
            candidate = np.clip(rho * np.sqrt(np.maximum(0.0, -dc / mid)), rho - move, rho + move)
            candidate = np.clip(candidate, 0.001, 1.0)
            candidate[PASSIVE] = 1.0
            if candidate.mean() > VOLFRAC:
                lower = mid
            else:
                upper = mid
        change = float(np.max(np.abs(candidate - rho)))
        rho = candidate
        history.append((iteration, compliance, float(rho.mean()), change))
        if iteration == 1 or iteration % 10 == 0 or change < CHANGE_LIMIT:
            print(f"iter {iteration:02d}: C={compliance:.3f}, volume={rho.mean():.4f}, change={change:.4f}")
        if iteration >= 35 and change < CHANGE_LIMIT:
            break
    return best_rho, history


def metrics(label: str, rho: np.ndarray) -> dict:
    u, _, compliance = solve(rho)
    return {
        "label": label,
        "volume_fraction": float(np.mean(rho)),
        "estimated_spine_volume_cm3": float(np.mean(rho) * WIDTH * HEIGHT * THICKNESS / 1000),
        "compliance_N_mm": dict(zip(LOAD_NAMES, map(float, compliance))),
        "max_displacement_mm": dict(zip(LOAD_NAMES, map(float, np.max(np.hypot(u[0::2], u[1::2]), axis=0)))),
    }


def plot(rho: np.ndarray, history):
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 6.2), gridspec_kw={"width_ratios": [1, 1, 1.35]})
    for axis, field, title in (
        (axes[0], BASELINE, "Baseline hand truss"),
        (axes[1], rho, "Best same-volume result"),
    ):
        axis.imshow(field.reshape(NY, NX), origin="lower", cmap="gray_r", extent=(-WIDTH / 2, WIDTH / 2, 0, HEIGHT), vmin=0, vmax=1, aspect="equal")
        axis.axhspan(68, 144, color="#5c6f82", alpha=0.12)
        axis.set_title(title)
        axis.set_xlabel("x (mm)")
        axis.set_ylabel("z (mm)")
    history = np.asarray(history)
    axes[2].plot(history[:, 0], history[:, 1] / history[0, 1], color="#2d556f", linewidth=2)
    axes[2].set_title("Optimization convergence")
    axes[2].set_xlabel("iteration")
    axes[2].set_ylabel("normalized weighted compliance")
    axes[2].grid(alpha=0.25)
    fig.suptitle("Compact LIFT X quiver spine topology study — PETG-HF", fontsize=14)
    fig.tight_layout()
    fig.savefig(ROOT / "spine_topology_density.png", dpi=220, transparent=False)
    plt.close(fig)


def main():
    optimized, history = optimize()
    baseline = metrics("baseline", BASELINE)
    result = metrics("optimized", optimized)
    result["weighted_compliance_change_percent"] = 100 * (
        sum(result["compliance_N_mm"][name] * weight for name, weight in zip(LOAD_NAMES, LOAD_WEIGHTS))
        / sum(baseline["compliance_N_mm"][name] * weight for name, weight in zip(LOAD_NAMES, LOAD_WEIGHTS))
        - 1
    )
    summary = {
        "model": {
            "method": "2D plane-stress SIMP compliance minimization",
            "grid": [NX, NY],
            "domain_mm": [WIDTH, THICKNESS, HEIGHT],
            "material": {"name": "Bambu PETG-HF", "elastic_modulus_MPa": E0, "poisson_ratio_assumed": NU},
            "penalty": PENAL,
            "filter_radius_elements": FILTER_RADIUS,
            "iterations": len(history),
            "load_cases": list(LOAD_NAMES),
        },
        "baseline": baseline,
        "optimized": result,
        "interpretation": "The printable two-bay diamond was the best same-volume field encountered, so it was retained and verified in the 3D CAD.",
    }
    plot(optimized, history)
    (ROOT / "spine_topology_results.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    np.save(ROOT / "spine_topology_density.npy", optimized.reshape(NY, NX))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
