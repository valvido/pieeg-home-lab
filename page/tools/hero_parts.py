"""
Cuts the page's hero art out of the README hero (docs/images/hero.svg), so the page and the repo show
the same bust and the same recording: athena.svg is the bust with its three leads, trace.svg is the
6 s of real EEG with its alpha bursts. Only the viewBox changes; the frame and background are dropped
so the art sits on the page's own ground (the same #0b0d33).

    python page/tools/hero_parts.py
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "images" / "hero.svg"
OUT = ROOT / "page" / "assets" / "svg"

PARTS = {
    "athena.svg": (640, 0, 340, 460, "Athena bust wearing the kit: a sticker on the left forehead, "
                   "its blue lead over the ear, REF and BIAS leads from behind the ear"),
    "trace.svg": (36, 350, 536, 100, "Six seconds of real EEG from PiEEG's example recording, "
                  "alpha bursts at 10 Hz in blue"),
}


def main():
    svg = SRC.read_text(encoding="utf-8")
    body = svg[svg.index(">") + 1:svg.rindex("</svg>")]
    body = re.sub(r'<rect width="1000" height="460"[^>]*/>', "", body, count=1)
    body = re.sub(r'<path class="bracket"[^>]*/>', "", body)
    for name, (x, y, w, h, label) in PARTS.items():
        part = body
        if name == "athena.svg":           # drop the left column's text and chips
            part = re.sub(r"<text[^>]*>[^<]*</text>", "", part)
            part = re.sub(r'<rect x="(4[0-9]|1[0-9]{2}|2[0-9]{2}|3[0-9]{2})(\.0)?" y="(29[0-9]|3[0-9]{2})(\.0)?"[^>]*/>', "", part)
        else:                              # the trace needs no bust image
            part = re.sub(r"<image[^>]*/>", "", part)
            part = re.sub(r"<rect[^>]*/>", "", part)    # the command box above reaches into the frame
        out = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {w} {h}" width="{w}" height="{h}" '
               f'role="img" aria-label="{label}">{part}</svg>\n')
        (OUT / name).write_text(out, encoding="utf-8")
        print("wrote", OUT / name, len(out) // 1024, "kB")


if __name__ == "__main__":
    main()
