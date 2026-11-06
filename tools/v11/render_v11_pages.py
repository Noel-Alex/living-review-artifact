"""Render paper-v11.pdf to PNG pages and two-page contact sheets for visual QA.

Run: python -I -B tools/v11/render_v11_pages.py [dpi]   (from paper-drafts/; needs Ghostscript)
Writes review/v11-wpg2-pages/page-NN.png and sheet-NN.png (pages 2k-1 and 2k side by side).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/vendor"))
from PIL import Image  # noqa: E402

GS = shutil.which("gswin64c") or r"C:\Program Files\gs\gs10.07.0\bin\gswin64c.exe"


def main() -> None:
    dpi = sys.argv[1] if len(sys.argv) > 1 else "90"
    out = ROOT / "review/v11-wpg2-pages"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    subprocess.run([GS, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m", f"-r{dpi}",
                    f"-sOutputFile={out / 'page-%02d.png'}", str(ROOT / "v11-professor-revision/paper-v11.pdf")], check=True)
    pages = sorted(out.glob("page-*.png"))
    for k in range(0, len(pages), 2):
        ims = [Image.open(p) for p in pages[k:k + 2]]
        sheet = Image.new("RGB", (sum(i.width for i in ims) + 10 * (len(ims) - 1), max(i.height for i in ims)), "gray")
        x = 0
        for im in ims:
            sheet.paste(im, (x, 0))
            x += im.width + 10
        sheet.save(out / f"sheet-{k // 2 + 1:02d}.png")
    print(f"{len(pages)} pages")


if __name__ == "__main__":
    main()
