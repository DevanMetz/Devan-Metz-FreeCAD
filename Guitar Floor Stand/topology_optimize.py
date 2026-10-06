"""2D SIMP topology optimization for one side frame of the guitar stand."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu


OUT = Path(__file__).resolve().parent
NELX, NELY = 69, 66
DEPTH, HEIGHT = 230, 220
VOLUME_FRACTION = 0.24
PENALTY = 3.0
FILTER_RADIUS = 2.4
MAX_ITERATIONS = 100


def element_stiffness(poisson=0.38):
    a11 = np.array([[12, 3, -6, -3], [3, 12, 3, 0], [-6, 3, 12, -3], [-3, 0, -3, 12]])
    a12 = np.array([[-6, -3, 0, 3], [-3, -6, -3, -6], [0, -3, -6, 3], [3, -6, 3, -6]])
    b11 = np.array([[-4, 3, -2, 9], [3, -4, -9, 4], [-2, -9, -4, -3], [9, 4, -3, -4]])
    b12 = np.array([[2, -3, 4, -9], [-3, 2, 9, -2], [4, 9, 2, 3], [-9, -2, 3, 2]])
    return 1 / (1 - poisson**2) / 24 * (
        np.block([[a11, a12], [a12.T, a11]]) + poisson * np.block([[b11, b12], [b12.T, b11]])
    )


def node(ix, iz):
    return (NELY + 1) * ix + iz


def build_filter():
    rows, cols, weights = [], [], []
    radius = int(np.ceil(FILTER_RADIUS)) - 1
    for ix in range(NELX):
        for iz in range(NELY):
            row = ix * NELY + iz
            for jx in range(max(ix - radius, 0), min(ix + radius + 1, NELX)):
                for jz in range(max(iz - radius, 0), min(iz + radius + 1, NELY)):
                    weight = FILTER_RADIUS - np.hypot(ix - jx, iz - jz)
                    if weight > 0:
                        rows.append(row)
                        cols.append(jx * NELY + jz)
                        weights.append(weight)
    matrix = coo_matrix((weights, (rows, cols)), shape=(NELX * NELY, NELX * NELY)).tocsr()
    return matrix, np.asarray(matrix.sum(axis=1)).ravel()


def optimize():
    elements = NELX * NELY
    dofs = 2 * (NELX + 1) * (NELY + 1)
    stiffness = element_stiffness()
    edof = np.zeros((elements, 8), dtype=int)
    for ix in range(NELX):
        for iz in range(NELY):
            element = ix * NELY + iz
            n1, n2 = node(ix, iz), node(ix + 1, iz)
            edof[element] = [
                2 * n1 + 2, 2 * n1 + 3, 2 * n2 + 2, 2 * n2 + 3,
                2 * n2, 2 * n2 + 1, 2 * n1, 2 * n1 + 1,
            ]
    ik = np.kron(edof, np.ones((8, 1), dtype=int)).ravel()
    jk = np.kron(edof, np.ones((1, 8), dtype=int)).ravel()

    # Three independent cases: guitar weight, rear bump, and backrest vertical load.
    force = np.zeros((dofs, 3))
    seat = node(round(25 / DEPTH * NELX), round(25 / HEIGHT * NELY))
    back = node(round(105 / DEPTH * NELX), round(165 / HEIGHT * NELY))
    force[2 * seat + 1, 0] = -1.0
    force[2 * back, 1] = 0.75
    force[2 * back + 1, 2] = -0.5

    floor_nodes = [node(0, 0), node(NELX // 2, 0), node(NELX, 0)]
    fixed = np.array([2 * floor_nodes[1], *(2 * item + 1 for item in floor_nodes)])
    free = np.setdiff1d(np.arange(dofs), fixed)
    density = np.full(elements, VOLUME_FRACTION)
    filter_matrix, filter_sum = build_filter()
    centers_x = (np.repeat(np.arange(NELX), NELY) + 0.5) * DEPTH / NELX
    centers_z = (np.tile(np.arange(NELY), NELX) + 0.5) * HEIGHT / NELY
    back_surface = 69 + 0.22 * (centers_z - 22)
    guitar_keepout = (centers_z > 45) & (centers_z < 180) & (centers_x < back_surface - 3)
    density[guitar_keepout] = 0.001
    first_compliance = None

    for iteration in range(1, MAX_ITERATIONS + 1):
        modulus = 1e-9 + density**PENALTY * (1 - 1e-9)
        sk = (stiffness.ravel()[:, None] * modulus).ravel(order="F")
        matrix = coo_matrix((sk, (ik, jk)), shape=(dofs, dofs)).tocsc()
        matrix = (matrix + matrix.T) * 0.5
        solver = splu(matrix[free][:, free])
        displacement = np.zeros_like(force)
        displacement[free] = solver.solve(force[free])

        energy = np.zeros(elements)
        for case in range(force.shape[1]):
            local = displacement[:, case][edof]
            energy += np.sum((local @ stiffness) * local, axis=1)
        compliance = float(np.sum(modulus * energy))
        if first_compliance is None:
            first_compliance = compliance
        sensitivity = -PENALTY * density ** (PENALTY - 1) * energy
        sensitivity = np.asarray(
            filter_matrix @ (density * sensitivity) / filter_sum / np.maximum(1e-3, density)
        ).ravel()

        lower, upper, move = 0.0, 1e9, 0.2
        while (upper - lower) / (upper + lower + 1e-12) > 1e-3:
            middle = 0.5 * (lower + upper)
            candidate = np.maximum(
                0.001,
                np.maximum(
                    density - move,
                    np.minimum(1.0, np.minimum(density + move, density * np.sqrt(-sensitivity / middle))),
                ),
            )
            candidate[guitar_keepout] = 0.001
            if candidate.mean() > VOLUME_FRACTION:
                lower = middle
            else:
                upper = middle
        change = float(np.max(np.abs(candidate - density)))
        density = candidate
        if iteration == 1 or iteration % 10 == 0 or change < 0.01:
            print(f"iteration={iteration:3d} compliance={compliance:9.3f} volume={density.mean():.3f} change={change:.3f}")
        if change < 0.01:
            break

    field = density.reshape((NELX, NELY)).T
    np.save(OUT / "topology-side.npy", field)
    fig, axis = plt.subplots(figsize=(8, 7))
    axis.imshow(field, cmap="gray_r", origin="lower", extent=(0, DEPTH, 0, HEIGHT), vmin=0, vmax=1)
    axis.scatter([25, 105], [25, 165], color=["#d62728", "#ff7f0e"], s=45, label="load points")
    axis.scatter([0, DEPTH / 2, DEPTH], [0, 0, 0], color="#1f77b4", marker="s", s=35, label="floor constraints")
    axis.set(xlabel="front-to-back depth (mm)", ylabel="height (mm)", title="Side-frame topology optimization")
    axis.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT / "topology-side.png", dpi=180)
    plt.close(fig)

    assert abs(density.mean() - VOLUME_FRACTION) < 0.005
    assert compliance < first_compliance
    print(f"final_compliance={compliance:.3f} reduction={(1 - compliance / first_compliance) * 100:.1f}%")


if __name__ == "__main__":
    optimize()
