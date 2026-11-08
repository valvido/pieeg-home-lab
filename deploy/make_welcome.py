"""
Builds the SSH welcome for the Pi, deploy/update-motd.d/05-welcome, from the repo's own sources:
the bust from docs/images/hero.png, the PIEEG title, and 6 s of the real recording the hero shows
(docs/figures/data/hero_trace.json). The art is fixed at build time; service status and power are
read live on every login. 256 colors, 80 columns, so it looks the same in any terminal.

    python deploy/make_welcome.py            # writes deploy/update-motd.d/05-welcome
    python deploy/make_welcome.py --preview  # also renders deploy/welcome-preview.png
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deploy" / "update-motd.d" / "05-welcome"
ESC = "\x1b"

# Lab theme, nearest xterm 256 colors
CREAM, SHADE, GOLD, DIM, INK = 187, 60, 179, 103, 252
E1, E2, REF, BIAS, TRACE = 63, 105, 45, 141, 146
GROUND = (11, 13, 51)


def fg(c):
    return f"{ESC}[38;5;{c}m"


def bg(c):
    return f"{ESC}[48;5;{c}m"


RST, BOLD = f"{ESC}[0m", f"{ESC}[1m"


def xterm_palette():
    lv = [0, 95, 135, 175, 215, 255]
    pal = [(r, g, b) for r in lv for g in lv for b in lv]
    pal += [(8 + 10 * i,) * 3 for i in range(24)]
    return np.array(pal, float), list(range(16, 256))


PAL, IDX = xterm_palette()


def nearest(rgb):
    return IDX[int(np.argmin(((PAL - rgb) ** 2).sum(1)))]


class Grid:
    """Cells of (text, fg, bg). Text may carry no escapes; colors are per cell."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.c = [[(" ", None, None) for _ in range(w)] for _ in range(h)]

    def put(self, x, y, s, f=None, b=None):
        for i, ch in enumerate(s):
            if 0 <= x + i < self.w and 0 <= y < self.h:
                self.c[y][x + i] = (ch, f, b)

    def ansi(self, indent=0):
        lines = []
        for row in self.c:
            last = None
            out = " " * indent
            end = max([i + 1 for i, (ch, f, b) in enumerate(row) if ch != " " or b is not None] or [0])
            for ch, f, b in row[:end]:
                if (f, b) != last:
                    out += RST + (fg(f) if f is not None else "") + (bg(b) if b is not None else "")
                    last = (f, b)
                out += ch
            lines.append(out + RST)
        return "\n".join(lines)


def bust(grid, x0, y0, rows):
    """The bust from the hero as a line drawing in braille dots (2 by 4 per cell): a dot wherever the
    marble meets a dark line or the ground. Cells whose dots lie on the blue lead take its color."""
    from PIL import ImageFilter
    im = Image.open(ROOT / "docs" / "images" / "hero.png").convert("RGB").crop((1300, 0, 1960, 920))
    H = rows * 4
    W = round(im.width * H / im.height / 2) * 2
    big = im.resize((W * 4, H * 4), Image.BOX)
    rgb = np.asarray(big).astype(int)
    bright = rgb.mean(2) > 120
    edge = np.asarray(Image.fromarray(np.uint8(bright * 255)).filter(ImageFilter.FIND_EDGES)) > 0
    blue = (rgb[..., 2] - rgb[..., 0] > 60) & (rgb[..., 2] > 140)
    dots = (edge | blue).reshape(H, 4, W, 4).any((1, 3))
    lead = blue.reshape(H, 4, W, 4).any((1, 3))
    bits = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]
    for r in range(rows):
        for c in range(W // 2):
            code, on_lead = 0, False
            for dy in range(4):
                for dx in range(2):
                    if dots[r * 4 + dy, c * 2 + dx]:
                        code |= bits[dy][dx]
                        on_lead |= lead[r * 4 + dy, c * 2 + dx]
            if code:
                grid.put(x0 + c, y0 + r, chr(0x2800 + code), E1 if on_lead else CREAM)
    return W // 2


def title(grid, x0, y0):
    import pyfiglet
    big = pyfiglet.figlet_format("PIEEG", font="ansi_shadow").splitlines()[:6]
    for i, line in enumerate(big):
        for j, ch in enumerate(line):
            if ch == "█":
                grid.put(x0 + j, y0 + i, ch, CREAM)
            elif ch != " ":
                grid.put(x0 + j, y0 + i, ch, SHADE)
    small = pyfiglet.figlet_format("HOME LAB", font="calvin_s").splitlines()[:3]
    for i, line in enumerate(small):
        grid.put(x0 + 1, y0 + 7 + i, line, GOLD)


def trace(grid, x0, y0, cols, rows, seconds=2.0):
    """Braille plot of the 2 s of the hero's trace with the most alpha: each cell is 2 by 4 dots. Columns inside an alpha burst
    (8 to 12 Hz envelope above its median) are drawn in E1 blue, the rest in lavender."""
    from scipy import signal
    t = json.loads((ROOT / "docs" / "figures" / "data" / "hero_trace.json").read_text())
    v = np.asarray(t["microvolts"], float)
    sr = t["sample_rate_hz"]
    sos = signal.butter(4, [8, 12], "bandpass", fs=sr, output="sos")
    env = np.abs(signal.hilbert(signal.sosfiltfilt(sos, v)))
    n = int(seconds * sr)                       # the window with the strongest alpha
    k = int(np.argmax(np.convolve(env, np.ones(n), "valid")))
    v, env = v[k:k + n], env[k:k + n]
    nx, ny = cols * 2, rows * 4
    xs = np.linspace(0, len(v) - 1, nx * 6)
    vv = np.interp(xs, np.arange(len(v)), v)
    lo, hi = np.percentile(vv, [1, 99])
    yy = np.clip((hi - vv) / (hi - lo) * (ny - 1), 0, ny - 1)
    dots = np.zeros((ny, nx), bool)
    for i in range(len(xs) - 1):
        x = int(i * nx / len(xs))
        a, b = sorted((int(round(yy[i])), int(round(yy[i + 1]))))
        dots[a:b + 1, x] = True
    burst = np.interp(np.linspace(0, len(v) - 1, cols), np.arange(len(v)), env) > np.median(env) * 1.25
    bits = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]
    for r in range(rows):
        for c in range(cols):
            code = 0
            for dy in range(4):
                for dx in range(2):
                    if dots[r * 4 + dy, c * 2 + dx]:
                        code |= bits[dy][dx]
            if code:
                grid.put(x0 + c, y0 + r, chr(0x2800 + code), E1 if burst[c] else TRACE)


def banner():
    rows = 20
    probe = Grid(80, rows)
    bw = bust(probe, 0, 0, rows)
    g = Grid(80, rows)
    g.put(1, 1, "OPEN SOURCE EEG  ·  STARTER KIT", DIM)
    title(g, 1, 3)
    g.put(1, 14, "8 CHANNELS · ADS1299 · 24 BIT · 250 HZ · PI 3", DIM)
    trace(g, 1, 15, 46, 4)
    g.put(1, 19, "REAL EEG, 2 S, PIEEG EXAMPLE DATA", DIM)
    g.put(36, 19, "ALPHA 10 HZ", E1)
    bust(g, 79 - bw, 0, rows)
    return g.ansi(1)


SCRIPT = r'''#!/bin/sh
# Welcome on every SSH login: the lab, live status, how to run a session, a few commands.
# Built by deploy/make_welcome.py in pieeg-home-lab. Edit that file, not this one.
e=$(printf '\033')
B="${e}[1m"; R="${e}[0m"
c() { printf '%s[38;5;%sm' "$e" "$1"; }
GOLD=$(c 179); DIM=$(c 103); INK=$(c 252); OK=$(c 114); BAD=$(c 203)
E1=$(c 63); REF=$(c 45); BIAS=$(c 141)

dot() { if [ "$1" = active ]; then printf '%s●%s %s' "$OK" "$R" "$2"; else printf '%s●%s %s %s(%s)%s' "$BAD" "$R" "$2" "$DIM" "$1" "$R"; fi; }
srv=$(systemctl is-active pieeg-server 2>/dev/null)
page=$(systemctl is-active tina-page 2>/dev/null)
thr=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
# Anything but a number (an error message, "1 error_msg=...") would abort the whole banner
# at the arithmetic below, so treat it as "unknown" instead.
case "$thr" in 0x[0-9a-fA-F]*|[0-9]*) ;; *) thr="" ;; esac
pwnote=""
if [ -z "$thr" ]; then pw="${DIM}●${R} power"
elif [ $((thr & 1)) -ne 0 ]; then pw="${BAD}●${R} power"
  pwnote="  ${BAD}Power is too low right now.${R} Use the 3 A power bank and the official cable.
"
elif [ $((thr & 0x10000)) -ne 0 ]; then pw="${GOLD}●${R} power"
  pwnote="  ${GOLD}Power dipped since boot.${R} Check the cable, then reboot.
"
else pw="${OK}●${R} power"; fi
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -n "$IP" ] || IP="the address from the router's device list"

cat <<'ART'

@@ART@@

ART
cat <<TXT
  ${B}${INK}Welcome to tina. This is your EEG lab.${R}

  $(dot "$srv" "PiEEG Server")    $(dot "$page" "your page")    $pw
${pwnote}
  ${GOLD}OPEN ON YOUR LAPTOP${R}
    ${B}Your page${R}     http://tina.local:8080   ${DIM}manual, kit, live signal${R}
    ${B}Dashboard${R}     http://tina.local:1617   ${DIM}press Connect${R}
    ${B}Data${R}          ws://tina.local:1616     ${DIM}Python on your laptop${R}
    ${DIM}If .local does not answer, use $IP instead.${R}

  ${GOLD}A SESSION IN FOUR STEPS${R}
    ${B}1  Power${R}    Pi on the power bank, bank not charging. Laptop on battery.
                No HDMI, no Ethernet cable while stickers are on.
    ${B}2  Skin${R}     Alcohol on each spot, 30 s to dry, fresh stickers, press 5 s.
    ${B}3  Stick${R}    ${E1}E1${R} left forehead   ${REF}REF${R} behind left ear   ${BIAS}BIAS${R} behind right ear
    ${B}4  Plug${R}     ${E1}E1${R} on pin E1   ${REF}REF${R} on Ref   ${BIAS}BIAS${R} on Biasout   ${DIM}clip on the snap${R}
                Dashboard: Connect, close your eyes, alpha shows up at 10 Hz.

  ${GOLD}HERE ON THE PI${R}
    pieeg-server doctor                  ${DIM}checks the board and the chain${R}
    systemctl status pieeg-server        ${DIM}is the server running${R}
    sudo systemctl restart pieeg-server  ${DIM}restart it${R}
    sudo shutdown -h now                 ${DIM}off; unplug when the green light stops${R}

  ${DIM}Guide and code: github.com/jurecerkez-code/pieeg-home-lab${R}
  ${DIM}Not a medical device.${R}

TXT
'''


def main():
    art = banner()
    OUT.write_text(SCRIPT.replace("@@ART@@", art), encoding="utf-8")
    OUT.chmod(0o755)
    print("wrote", OUT)
    if "--preview" in sys.argv:
        preview(ROOT / "deploy" / "welcome-preview.png")


def preview(path):
    """Runs the script with stand ins for systemctl and vcgencmd, feeds the output through a
    terminal emulator (pyte) and draws the screen."""
    import os
    import subprocess
    import tempfile

    import pyte
    from PIL import ImageDraw, ImageFont
    d = Path(tempfile.mkdtemp())
    (d / "systemctl").write_text("#!/bin/sh\necho active\n")
    (d / "vcgencmd").write_text("#!/bin/sh\necho throttled=0x0\n")
    (d / "hostname").write_text("#!/bin/sh\necho 192.168.1.50\n")
    for f in d.iterdir():
        f.chmod(0o755)
    out = subprocess.run(["sh", str(OUT)], capture_output=True, text=True,
                         env={**os.environ, "PATH": f"{d}:{os.environ['PATH']}"}).stdout
    lines = out.count("\n") + 2
    scr = pyte.Screen(82, lines)
    st = pyte.Stream(scr)
    st.feed(out.replace("\n", "\r\n"))
    cw, ch = 10, 20
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16)
    bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 16)
    BGC = (24, 24, 30)
    img = Image.new("RGB", (82 * cw + 20, lines * ch + 20), BGC)
    dr = ImageDraw.Draw(img)

    def col(c, default):
        if c == "default":
            return default
        if isinstance(c, str) and len(c) == 6:
            return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
        return default
    for y in range(lines):
        for x in range(82):
            cell = scr.buffer[y][x]
            f, b = col(cell.fg, (220, 220, 220)), col(cell.bg, BGC)
            px, py = 10 + x * cw, 10 + y * ch
            dr.rectangle([px, py, px + cw - 1, py + ch - 1], fill=b)
            if cell.data == "▀":
                dr.rectangle([px, py, px + cw - 1, py + ch // 2 - 1], fill=f)
            elif cell.data == "▄":
                dr.rectangle([px, py + ch // 2, px + cw - 1, py + ch - 1], fill=f)
            elif cell.data == "█":
                dr.rectangle([px, py, px + cw - 1, py + ch - 1], fill=f)
            elif 0x2800 <= ord(cell.data[:1] or " ") <= 0x28FF:
                code = ord(cell.data) - 0x2800
                for k, (dx, dy) in enumerate([(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3)]):
                    if code >> k & 1:
                        cx, cy = px + 3 + dx * 4, py + 3 + dy * 4.5
                        dr.ellipse([cx - 1.3, cy - 1.3, cx + 1.3, cy + 1.3], fill=f)
            elif cell.data.strip():
                dr.text((px, py + 1), cell.data, fill=f, font=bold if cell.bold else font)
    img.save(path)
    print("preview", path)


if __name__ == "__main__":
    main()
