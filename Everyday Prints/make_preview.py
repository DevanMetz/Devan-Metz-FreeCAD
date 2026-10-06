"""Arrange the saved CAD snapshots into compact, labeled review sheets."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from build_collection import current_view_packets

ROOT = Path(__file__).resolve().parent
REVIEW = ROOT / "review"


def main():
    jobs = current_view_packets()
    font = ImageFont.load_default(size=20)
    for batch in range(0, len(jobs), 4):
        group = jobs[batch:batch+4]
        sheet = Image.new("RGB", (2000, len(group)*420), "#edf1f2")
        draw = ImageDraw.Draw(sheet)
        for row, job in enumerate(group):
            name = Path(job["input"]).name.removesuffix(".step.py").replace("_", " ")
            for col, output in enumerate(job["outputs"]):
                frame = Image.open(output["path"]).convert("RGB")
                frame.thumbnail((495, 375))
                sheet.paste(frame, (col*500+(500-frame.width)//2, row*420+35))
                draw.text((col*500+12, row*420+8), f"{name} / {('iso','opposite','top','front')[col]}",
                          fill="#17292f", font=font)
        sheet.save(REVIEW / f"review_sheet_{batch//4+1}.png")
    cover = Image.new("RGB", (1800, 120 + ((len(jobs)+2)//3)*470), "#edf1f2")
    draw = ImageDraw.Draw(cover)
    draw.text((32, 20), "EVERYDAY PRINTS  /  editable, open-source CAD", fill="#17292f",
              font=ImageFont.load_default(size=36))
    for i, job in enumerate(jobs):
        frame = Image.open(job["outputs"][0]["path"]).convert("RGB")
        frame.thumbnail((575, 400))
        x, y = (i%3)*600, 100+(i//3)*470
        cover.paste(frame, (x+(600-frame.width)//2, y))
        name = Path(job["input"]).name.removesuffix(".step.py").replace("_", " ").title()
        draw.text((x+25, y+410), name, fill="#17292f", font=ImageFont.load_default(size=26))
    cover.save(ROOT / "preview.png")
    # Stable documentation images follow the newest source snapshots.
    for source,target in (('strap_clamp_assembly','strap_clamp_preview'),
                           ('sorting_sieve','sorting_sieve_preview'),
                           ('divider_joint_assembly','divider_joint_preview')):
        job = next(job for job in jobs if Path(job['input']).name == source+'.step.py')
        Image.open(job['outputs'][0]['path']).save(ROOT/(target+'.png'))
    print("Saved diagnostic contact sheets and preview.png")
    from make_index import main as build_index
    build_index()


if __name__ == "__main__":
    main()
