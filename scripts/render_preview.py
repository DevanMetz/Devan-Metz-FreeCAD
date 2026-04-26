"""Render a high-resolution, alpha-cropped preview of a FreeCAD model.

Usage (from the FreeCAD-bundled Python — required, since rendering needs the GUI):

    "C:/Program Files/FreeCAD 1.0/bin/python.exe" scripts/render_preview.py \
        "Fridge Cup/Fridge Cup.FCStd" images/fridge-cup.png

Optional flags:
    --width  4000   Render width in pixels  (default: 4000)
    --height 4000   Render height in pixels (default: 4000)
    --padding 16    Transparent padding kept around the model (default: 16 px)
    --view iso      One of: iso, front, top, right, left, back, bottom (default: iso)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import FreeCAD  # type: ignore
import FreeCADGui  # type: ignore
from PIL import Image


VIEWS = {
    "iso": "viewAxonometric",
    "front": "viewFront",
    "top": "viewTop",
    "right": "viewRight",
    "left": "viewLeft",
    "back": "viewRear",
    "bottom": "viewBottom",
}


def render(fcstd: Path, out: Path, width: int, height: int, padding: int, view: str) -> None:
    FreeCADGui.showMainWindow()
    doc = FreeCAD.open(str(fcstd))
    FreeCADGui.ActiveDocument = FreeCADGui.getDocument(doc.Name)

    gui_view = FreeCADGui.ActiveDocument.ActiveView
    getattr(gui_view, VIEWS[view])()
    gui_view.fitAll()

    raw = out.with_suffix(".raw.png")
    gui_view.saveImage(str(raw), width, height, "Transparent")

    with Image.open(raw) as img:
        img = img.convert("RGBA")
        bbox = img.split()[-1].getbbox()
        if bbox is None:
            raise RuntimeError("Rendered image is fully transparent — nothing visible in the view.")
        cropped = img.crop(bbox)

        if padding > 0:
            padded = Image.new("RGBA", (cropped.width + 2 * padding, cropped.height + 2 * padding))
            padded.paste(cropped, (padding, padding))
            cropped = padded

        cropped.save(out, "PNG", optimize=True)

    raw.unlink(missing_ok=True)
    FreeCAD.closeDocument(doc.Name)
    print(f"Wrote {out} ({cropped.width}x{cropped.height})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fcstd", type=Path, help="Input .FCStd file")
    parser.add_argument("out", type=Path, help="Output .png file")
    parser.add_argument("--width", type=int, default=4000)
    parser.add_argument("--height", type=int, default=4000)
    parser.add_argument("--padding", type=int, default=16)
    parser.add_argument("--view", choices=VIEWS.keys(), default="iso")
    args = parser.parse_args()

    if not args.fcstd.exists():
        sys.exit(f"Input file not found: {args.fcstd}")
    args.out.parent.mkdir(parents=True, exist_ok=True)

    render(args.fcstd, args.out, args.width, args.height, args.padding, args.view)


if __name__ == "__main__":
    main()
