"""2-D SIMP topology optimization for one longboard-holder bracket."""
from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
import trimesh

OUT = Path(__file__).parent
NX, NY = 54, 72
LENGTH, HEIGHT, THICKNESS = 45.0, 90.0, 32.0  # mm
E, NU = 3000.0, 0.35  # conservative printed-PETG values, MPa
LOAD = 12.0 * 9.81 * 3.0 / 2.0  # N: 12 kg board, 3g, shared by two brackets
VOLFRAC, PENAL, RMIN = 0.44, 3.0, 2.6
LOAD_X, LOAD_Y = (18.0, 28.0), 30.0


def element_stiffness():
    k = np.array([
        1 / 2 - NU / 6, 1 / 8 + NU / 8, -1 / 4 - NU / 12, -1 / 8 + 3 * NU / 8,
        -1 / 4 + NU / 12, -1 / 8 - NU / 8, NU / 6, 1 / 8 - 3 * NU / 8,
    ])
    return E / (1 - NU**2) * np.array([
        [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
        [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
        [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
        [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
        [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
        [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
        [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
        [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
    ])


def setup():
    nodes = np.arange((NX + 1) * (NY + 1)).reshape((NY + 1, NX + 1), order="F")
    vec = (2 * nodes[:-1, :-1] + 2).reshape(NX * NY, order="F")
    offsets = np.array([0, 1, 2 * NY + 2, 2 * NY + 3, 2 * NY, 2 * NY + 1, -2, -1])
    edof = vec[:, None] + offsets
    iK = np.kron(edof, np.ones((8, 1))).ravel()
    jK = np.kron(edof, np.ones((1, 8))).ravel()
    force = np.zeros(2 * (NX + 1) * (NY + 1))
    load_y = round(LOAD_Y / HEIGHT * NY)
    load_nodes = nodes[load_y, round(LOAD_X[0] / LENGTH * NX):round(LOAD_X[1] / LENGTH * NX) + 1]
    force[2 * load_nodes + 1] = -LOAD / len(load_nodes)
    fixed = np.ravel([[2 * n, 2 * n + 1] for n in nodes[:, 0]])
    free = np.setdiff1d(np.arange(force.size), fixed)
    return nodes, edof, iK, jK, force, free


def filter_matrix():
    rows, cols, vals = [], [], []
    for x in range(NX):
        for y in range(NY):
            row = x * NY + y
            for xx in range(max(0, x - int(RMIN) + 1), min(NX, x + int(RMIN))):
                for yy in range(max(0, y - int(RMIN) + 1), min(NY, y + int(RMIN))):
                    w = RMIN - np.hypot(x - xx, y - yy)
                    if w > 0:
                        rows.append(row); cols.append(xx * NY + yy); vals.append(w)
    H = coo_matrix((vals, (rows, cols)), shape=(NX * NY, NX * NY)).tocsr()
    return H, np.asarray(H.sum(1)).ravel()


def solve_density(xphys, edof, iK, jK, force, free, ke):
    stiffness = (1e-6 + xphys.ravel(order="F") ** PENAL * (1 - 1e-6))
    sK = (THICKNESS * ke.ravel()[:, None] * stiffness).ravel(order="F")
    K = coo_matrix((sK, (iK, jK)), shape=(force.size, force.size)).tocsc()
    u = np.zeros_like(force)
    u[free] = spsolve(K[free, :][:, free], force[free])
    ue = u[edof]
    ce = np.einsum("ij,ij->i", ue @ ke, ue).reshape((NY, NX), order="F")
    return u, ce


def optimize():
    _, edof, iK, jK, force, free = setup()
    ke, (H, Hs) = element_stiffness(), filter_matrix()
    x = np.full((NY, NX), VOLFRAC)
    solid = np.zeros_like(x, dtype=bool)
    solid[:, :6] = True                                                   # wall/fastener band
    solid[round(20 / HEIGHT * NY):round(31 / HEIGHT * NY), :round(36 / LENGTH * NX)] = True  # cradle floor
    solid[round(20 / HEIGHT * NY):round(49 / HEIGHT * NY), round(30 / LENGTH * NX):round(39 / LENGTH * NX)] = True  # lip
    void = np.zeros_like(solid)
    void[round(31 / HEIGHT * NY):, round(8 / LENGTH * NX):] = True         # deck keep-out
    void[solid] = False
    x[solid] = 1.0
    x[void] = 0.001
    history = []
    for iteration in range(80):
        xphys = (H @ x.ravel(order="F") / Hs).reshape((NY, NX), order="F")
        xphys[solid] = 1.0
        xphys[void] = 0.001
        u, ce = solve_density(xphys, edof, iK, jK, force, free, ke)
        dc = (-PENAL * xphys ** (PENAL - 1) * ce).ravel(order="F")
        dc = (H @ (x.ravel(order="F") * dc) / Hs / np.maximum(1e-3, x.ravel(order="F"))).reshape((NY, NX), order="F")
        lo, hi = 0.0, 1e9
        while (hi - lo) / (hi + lo + 1e-12) > 1e-4:
            mid = (lo + hi) / 2
            candidate = np.maximum(0.001, np.maximum(x - 0.2, np.minimum(1.0, np.minimum(x + 0.2, x * np.sqrt(np.maximum(0, -dc / mid))))))
            candidate[solid] = 1.0
            candidate[void] = 0.001
            if candidate.mean() > VOLFRAC:
                lo = mid
            else:
                hi = mid
        change = np.max(np.abs(candidate - x))
        x = candidate
        history.append(float(np.sum((1e-6 + xphys**PENAL) * ce)))
        if iteration > 20 and change < 0.01:
            break
    xphys = (H @ x.ravel(order="F") / Hs).reshape((NY, NX), order="F")
    xphys[solid] = 1.0
    xphys[void] = 0.001
    u, ce = solve_density(xphys, edof, iK, jK, force, free, ke)
    return xphys, u, ce, history, (edof, iK, jK, force, free, ke)


def stress_field(xphys, u, edof):
    # Constant-strain estimate at each element center; sufficient for comparing load paths.
    dx, dy = LENGTH / NX, HEIGHT / NY
    B = np.array([
        [-1, 0, 1, 0, 1, 0, -1, 0],
        [0, -1, 0, -1, 0, 1, 0, 1],
        [-1, -1, -1, 1, 1, 1, 1, -1],
    ], dtype=float)
    B[0] /= 2 * dx; B[1] /= 2 * dy; B[2, ::2] /= 2 * dy; B[2, 1::2] /= 2 * dx
    D = E / (1 - NU**2) * np.array([[1, NU, 0], [NU, 1, 0], [0, 0, (1 - NU) / 2]])
    s = (u[edof] @ B.T) @ D.T
    vm = np.sqrt(s[:, 0] ** 2 - s[:, 0] * s[:, 1] + s[:, 1] ** 2 + 3 * s[:, 2] ** 2)
    return (vm * xphys.ravel(order="F") ** PENAL).reshape((NY, NX), order="F")


def save_results(xphys, u, ce, history, system):
    edof, *_ = system
    vm = stress_field(xphys, u, edof)
    node_disp = np.hypot(u[0::2], u[1::2]).reshape((NY + 1, NX + 1), order="F")
    vmax = float(np.percentile(vm[xphys > 0.25], 99))
    dmax = float(node_disp.max())
    solid_mass_g = LENGTH * HEIGHT * THICKNESS * 1.27e-3
    mass_g = solid_mass_g * float(xphys.mean())

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    extent = [0, LENGTH, 0, HEIGHT]
    allowable = np.ones_like(xphys)
    allowable[round(31 / HEIGHT * NY):, round(8 / LENGTH * NX):] = 0
    allowable[round(20 / HEIGHT * NY):round(49 / HEIGHT * NY), round(30 / LENGTH * NX):round(39 / LENGTH * NX)] = 1
    axes[0, 0].imshow(allowable, origin="lower", extent=extent, cmap="gray_r", vmin=0, vmax=1)
    axes[0, 0].set_title("1  Allowable domain — deck keep-out removed")
    im = axes[0, 1].imshow(xphys, origin="lower", extent=extent, cmap="gray_r", vmin=0, vmax=1)
    axes[0, 1].set_title(f"2  SIMP result — {xphys.mean():.0%} material")
    fig.colorbar(im, ax=axes[0, 1], label="Material density")
    stress = np.ma.masked_where(xphys < 0.18, vm)
    im = axes[1, 0].imshow(stress, origin="lower", extent=extent, cmap="turbo", vmin=0, vmax=max(vmax, 1e-6))
    axes[1, 0].set_title(f"3  von Mises stress — 99th percentile {vmax:.1f} MPa")
    fig.colorbar(im, ax=axes[1, 0], label="Stress (MPa)")
    disp_e = gaussian_filter(node_disp[:-1, :-1], 0.7)
    im = axes[1, 1].imshow(np.ma.masked_where(xphys < 0.18, disp_e), origin="lower", extent=extent, cmap="viridis")
    axes[1, 1].set_title(f"4  Displacement magnitude — max {dmax:.2f} mm")
    fig.colorbar(im, ax=axes[1, 1], label="Displacement (mm)")
    for ax in axes.ravel():
        ax.set(xlabel="Projection from wall (mm)", ylabel="Height (mm)", aspect="equal")
        ax.plot(LOAD_X, [LOAD_Y, LOAD_Y], color="magenta", lw=4)
    fig.suptitle("Longboard wall holder — topology optimization and linear static check", fontsize=15)
    fig.savefig(OUT / "simulation-results.png", dpi=180)
    plt.close(fig)

    data = {
        "assumptions": {"board_mass_kg": 12, "shock_factor": 3, "bracket_count": 2, "load_per_bracket_N": LOAD,
                        "material": "printed PETG (isotropic approximation)", "elastic_modulus_MPa": E, "poisson_ratio": NU},
        "domain_mm": [LENGTH, HEIGHT, THICKNESS], "iterations": len(history), "material_fraction": float(xphys.mean()),
        "estimated_mass_g": mass_g, "stress_99pct_MPa": vmax, "max_displacement_mm": dmax,
        "note": "Concept-stage 2-D linear-static FEA; validate print orientation, fasteners, wall substrate, and real material before use."
    }
    (OUT / "simulation-summary.json").write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(data, indent=2))


def render_model():
    path = OUT / "Longboard_Wall_Holder.stl"
    if not path.exists():
        return
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    mesh = trimesh.load_mesh(path)
    fig = plt.figure(figsize=(12, 8), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(mesh.triangles[:, :, [0, 2, 1]], facecolor="#4f5965", edgecolor="#20252b", linewidth=0.08))
    lo, hi = mesh.bounds
    ax.set(xlim=(lo[0] - 5, hi[0] + 5), ylim=(lo[2] - 8, hi[2] + 8), zlim=(lo[1] - 5, hi[1] + 5))
    ax.set_box_aspect((0.7, 0.55, 1.2))
    ax.view_init(elev=18, azim=-58)
    ax.set(xlabel="Projection (mm)", ylabel="Width (mm)", zlabel="Height (mm)", title="Longboard edge cradle — print two")
    fig.savefig(OUT / "design-render.png", dpi=180, transparent=False)
    plt.close(fig)


def render_layout():
    from matplotlib.patches import FancyBboxPatch, Rectangle
    fig, (front, side) = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    deck = FancyBboxPatch((40, 35), 900, 240, boxstyle="round,pad=0,rounding_size=110", facecolor="#d97738", edgecolor="#472b1c", lw=2)
    front.add_patch(deck)
    front.text(490, 155, "BOTTOM / ARTWORK FACES OUT", ha="center", va="center", weight="bold", color="white")
    for x in (260, 720):
        front.add_patch(Rectangle((x - 16, 20), 32, 30, facecolor="#4f5965", edgecolor="#20252b"))
    front.set(xlim=(0, 980), ylim=(0, 310), aspect="equal", title="Front view — two holders spaced along the deck length", xlabel="Board length (mm)", ylabel="Board width (mm)")
    side.plot([0, 0], [0, 300], color="#777", lw=6, label="wall")
    side.add_patch(Rectangle((8, 20), 14, 240, angle=-2.7, facecolor="#d97738", edgecolor="#472b1c"))
    side.plot([7, 36, 36], [18, 18, 42], color="#4f5965", lw=12, solid_capstyle="butt")
    side.annotate("grip tape leans toward wall", (8, 235), (40, 270), arrowprops={"arrowstyle": "->"})
    side.annotate("padded edge cradle", (25, 22), (55, 70), arrowprops={"arrowstyle": "->"})
    side.set(xlim=(-15, 100), ylim=(0, 300), aspect="equal", title="Side view", xlabel="Projection from wall (mm)", ylabel="Height (mm)")
    fig.savefig(OUT / "display-layout.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    result = optimize()
    assert result[0].shape == (NY, NX) and np.isfinite(result[1]).all()
    save_results(*result)
    render_model()
    render_layout()
