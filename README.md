# 🛠️ FreeCAD Designs

> A collection of my 3D models designed in [FreeCAD](https://www.freecad.org/) — ready to view, remix, and print.

![FreeCAD](https://img.shields.io/badge/Made%20with-FreeCAD-red?logo=freecad&logoColor=white)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue)](https://www.apache.org/licenses/LICENSE-2.0)
![3D Printable](https://img.shields.io/badge/3D-Printable-brightgreen)

---

## 📦 Models

### 🥤 Fridge Cup

<p align="center">
  <img src="images/fridge-cup.png" alt="Fridge Cup preview" width="320" />
</p>

A compact, slim-profile cup designed to fit neatly in a fridge door — perfect for saving space. Fully parametric FreeCAD model with variables exposed for every dimension, so you can resize the height, width, depth, wall thickness, and fillets to match your fridge without rebuilding the geometry.

| | |
|---|---|
| **Source file** | [`Fridge Cup.FCStd`](Fridge%20Cup/Fridge%20Cup.FCStd) |
| **Print-ready** | [`Fridge Cup.3mf`](Fridge%20Cup/Fridge%20Cup.3mf) |
| **License** | [LICENSE](Fridge%20Cup/LICENSE) |

#### Dimensions

<p align="center">
  <img src="images/fridge-cup-dimensions.svg" alt="Fridge Cup dimensioned drawing" width="640" />
</p>

#### Parameters (`VarSet`)

Open the `VarSet` in the FreeCAD model tree to edit any of these — the geometry rebuilds automatically.

| Variable | Default | Unit | Drives |
|---|---:|---|---|
| `Length` | 100 | mm | Outer footprint length (sketch constraint) |
| `Width` | 30 | mm | Outer footprint width (sketch constraint) |
| `Depth` | 75 | mm | Cup height / pad extrusion depth |
| `Thickness` | 3 | mm | Wall thickness (shell) |
| `Fillet` | 5 | mm | Vertical corner fillet radius (top edge uses 2 × `Fillet`) |
| `MagDiameter` | 6.2 | mm | Magnet pocket diameter |
| `MagThickness` | 2 | mm | Magnet pocket depth |
| `MagInset` | 10 | mm | Magnet inset from each corner |
| `Angle` | 60 | ° | Base angle of the trapezoidal bottom face |

---

## 🖥️ Opening the Files

1. Install [FreeCAD](https://www.freecad.org/downloads.php) (free & open source).
2. Clone this repo:
   ```bash
   git clone https://github.com/DevanMetz/Devan-Metz-FreeCAD.git
   ```
3. Open any `.FCStd` file in FreeCAD to view, edit, or remix the design.

## 🖨️ 3D Printing

`.3mf` files are ready to slice in [PrusaSlicer](https://www.prusa3d.com/page/prusaslicer_424/), [Bambu Studio](https://bambulab.com/en/download/studio), [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer), or [Cura](https://ultimaker.com/software/ultimaker-cura/).

---

## 📜 License

Released under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). You're free to use, modify, and distribute these designs — including for commercial purposes — provided you retain the license and attribution notices.

---

<p align="center"><sub>Built with ❤️ and FreeCAD</sub></p>
