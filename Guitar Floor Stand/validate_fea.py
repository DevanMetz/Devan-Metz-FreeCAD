"""Create a CalculiX input deck from the Gmsh mesh for a conservative PETG check."""

from pathlib import Path


OUT = Path(__file__).resolve().parent
MESH = OUT / "guitar-floor-stand.msh"
INPUT = OUT / "fea-guitar-stand.inp"


def read_gmsh():
    lines = MESH.read_text().splitlines()
    node_start = lines.index("$Nodes") + 1
    node_count = int(lines[node_start])
    nodes = {}
    for line in lines[node_start + 1 : node_start + 1 + node_count]:
        number, x, y, z = line.split()
        nodes[int(number)] = (float(x), float(y), float(z))

    element_start = lines.index("$Elements") + 1
    element_count = int(lines[element_start])
    tetrahedra = []
    for line in lines[element_start + 1 : element_start + 1 + element_count]:
        fields = [int(value) for value in line.split()]
        if fields[1] == 4:
            tetrahedra.append(fields[3 + fields[2] :])
    return nodes, tetrahedra


def rows(values, width=16):
    values = list(values)
    return [", ".join(str(item) for item in values[index : index + width]) for index in range(0, len(values), width)]


def build_input():
    nodes, tetrahedra = read_gmsh()
    floor = [number for number, (_, _, z) in nodes.items() if z < 0.05]
    seat = [
        number
        for number, (x, y, z) in nodes.items()
        if 30 < z < 55
        and abs(y - (20 + 0.212556 * (z - 35))) < 0.6
        and (20 < x < 55 or 175 < x < 210)
    ]
    back = [
        number
        for number, (x, y, z) in nodes.items()
        if 160 < z < 184
        and abs(y - (20 + 51 / 0.978148 + 0.212556 * (z - 35))) < 7
        and (25 < x < 58 or 172 < x < 205)
    ]
    assert floor and seat and back

    output = ["*HEADING", "Topology-guided guitar stand: PETG combined load check", "*NODE"]
    output.extend(f"{number}, {x:.7g}, {y:.7g}, {z:.7g}" for number, (x, y, z) in nodes.items())
    output.append("*ELEMENT, TYPE=C3D4, ELSET=EALL")
    output.extend(f"{number}, " + ", ".join(map(str, connectivity)) for number, connectivity in enumerate(tetrahedra, 1))
    for name, values in (("NALL", nodes), ("FLOOR", floor), ("SEAT", seat), ("BACK", back)):
        output.append(f"*NSET, NSET={name}")
        output.extend(rows(values))
    output.extend(
        [
            "*MATERIAL, NAME=PETG",
            "*ELASTIC",
            "2000., 0.38",
            "*SOLID SECTION, ELSET=EALL, MATERIAL=PETG",
            "*BOUNDARY",
            "FLOOR, 1, 3",
            "*STEP",
            "*STATIC",
            "0.1, 1.0",
            "*CLOAD",
            f"SEAT, 3, {-150 / len(seat):.8g}",
            f"BACK, 1, {50 / len(back):.8g}",
            f"BACK, 2, {50 / len(back):.8g}",
            "*NODE PRINT, NSET=NALL",
            "U",
            "*EL PRINT, ELSET=EALL",
            "S",
            "*END STEP",
        ]
    )
    INPUT.write_text("\n".join(output) + "\n")
    print(f"nodes={len(nodes)} tetrahedra={len(tetrahedra)} floor={len(floor)} seat={len(seat)} back={len(back)}")


if __name__ == "__main__":
    build_input()
