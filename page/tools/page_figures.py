"""
Figures for the Pi's page (index.html, assets/svg). True scale renders made with the renderer and parts
of the pieeg-home-lab repo (docs/figures/render3d.py and parts3d.py), on a transparent background so
they sit on the page's own navy ground (the repo's Lab theme), with labels in the page's fonts and colors.

    python page/tools/page_figures.py                 # all six, into page/assets/svg
    python page/tools/page_figures.py . page/assets/svg electrodes   # just one
"""

import base64
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE.parents[1]
OUT = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else HERE.parent / "assets" / "svg"
sys.path.insert(0, str(REPO / "docs" / "figures"))
import parts3d as P3          # noqa: E402
import render3d as R          # noqa: E402

DATA = REPO / "docs" / "figures" / "data"
W = 600
FG, MUTED, ACCENT, HAIR = "#ecebf7", "#9a9ccc", "#d8b55a", "#3d4390"      # Lab theme: ink, muted, gold, line
E1C, E2C, E3C, E4C, REFC, BIASC = "#4b4bff", "#8f96ff", "#5fd3a5", "#f0a35e", "#22d3ff", "#c792ff"
MONO = "DejaVu Sans Mono, Menlo, Consolas, ui-monospace, monospace"
for name, col in {"E1": E1C, "E2": E2C, "E3": E3C, "E4": E4C, "REF": REFC, "BIAS": BIASC}.items():
    R.material("rim_" + name, col, 0.6, 0.0, 8, 0.7, emit=0.55)
    R.material("wire_" + name, col, 0.75, 0.25, 30, 0.6, emit=0.25)
R.material("table", "#161a52", 0.85, 0.05, 10, 0.6)
R.material("foam", "#fdfdfb", 0.9, 0.0, 8, 0.7, emit=0.7)       # white foam reads as white, not as texture


class Page:
    def __init__(self, h):
        self.h, self.items = h, []

    def image(self, r):
        x, y, w, h = r.image_box()
        b64 = base64.b64encode(r.png()).decode()
        self.items.append(f'<image x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" href="data:image/png;base64,{b64}"/>')

    def text(self, x, y, s, color=MUTED, size=11, anchor="start", weight=400, spacing=0.8):
        s = str(s).replace("&", "&amp;").replace("<", "&lt;")
        self.items.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{MONO}" font-size="{size}" font-weight="{weight}" '
                          f'letter-spacing="{spacing}" fill="{color}" text-anchor="{anchor}">{s}</text>')

    def label(self, x, y, title, sub, color, anchor="start"):
        self.text(x, y, title, color, 12, anchor, 600, 1.2)
        for i, line in enumerate(sub if isinstance(sub, list) else [sub]):
            if line:
                self.text(x, y + 15 + 14 * i, line, MUTED, 10.5, anchor)

    def leader(self, pts, color):
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        self.items.append(f'<path d="{d}" stroke="{color}" stroke-width="1" fill="none" stroke-linejoin="round"/>')
        self.items.append(f'<circle cx="{pts[0][0]:.1f}" cy="{pts[0][1]:.1f}" r="2.2" fill="{color}"/>')

    def line(self, x1, y1, x2, y2, color=HAIR, w=1, dash=None):
        ds = f' stroke-dasharray="{dash}"' if dash else ""
        self.items.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{w}"{ds}/>')

    def scale(self, x, y, mm, k, label=None):
        L = mm * k
        self.line(x, y, x + L, y, MUTED, 1)
        for t in (0, 1):
            self.line(x + L * t, y - 4, x + L * t, y + 4, MUTED, 1)
        self.text(x + L + 8, y + 3.5, label or f"{mm} mm", MUTED, 10.5)

    def save(self, name, aria):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {self.h}" width="{W}" height="{self.h}" '
               f'role="img" aria-label="{aria}">' + "\n".join(self.items) + "</svg>")
        (OUT / name).write_text(svg)
        print("wrote", OUT / name, f"{len(svg) // 1024} kB")


def stickers(sc, skin, spots):
    """spots: lead -> (point near the skin, view direction to project from). Returns stud tops."""
    studs = {}
    for lead, p in spots.items():
        v, f, m, c, n = R.sticker_mesh(skin, p, "rim_" + lead)
        sc.add(v, f, m)
        studs[lead] = c + n * (R.FOAM_T + R.STUD_H)
    return studs


def front_point(skin, x, z, y_from=400.0, step=-1.0):
    """The skin point seen from the front at (x, z): march in from the front until the skin."""
    for y in np.arange(y_from, -200, step * 2):
        sd, q, n = skin.signed_distance(np.array([[x, y, z]]))
        if sd[0] < 1.0 and n[0][1] > 0.1:
            return q[0]
    raise ValueError("no skin")


def body_mesh(keep, subdiv=0, cut=()):
    import collections
    import trimesh
    verts, groups, g = [], collections.defaultdict(list), None
    for line in (DATA / "makehuman_base.obj").read_text().splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("g "):
            g = line.split()[1]
        elif line.startswith("f "):
            groups[g].append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
    v = np.array(verts)
    V = np.c_[-v[:, 0], v[:, 2], v[:, 1]] * 100
    tris = np.array([[f[0], f[i], f[i + 1]] for name in ("body",) for f in groups[name] for i in range(1, len(f) - 1)])
    m = trimesh.Trimesh(V, tris[keep(V[tris].mean(1))], process=True)
    m.remove_unreferenced_vertices()
    for _ in range(subdiv):
        vv, ff = trimesh.remesh.subdivide_loop(m.vertices, m.faces, iterations=1)
        m = trimesh.Trimesh(vv, ff, process=True)
    for n, d in cut:
        n = np.asarray(n, float)
        k = np.linalg.norm(n)
        m = m.slice_plane(n / k * d / k, n / k, cap=True)
    cap = np.zeros(len(m.faces), bool)
    for n, d in cut:
        n = np.asarray(n, float)
        k = np.linalg.norm(n)
        cap |= (np.abs(m.triangles_center @ (n / k) - d / k) < 0.05) & (m.face_normals @ (n / k) < -0.99)
    return m.vertices, m.faces, cap


R.material("bust", "#e7e2d6", 0.84, 0.035, 14, 0.62)
R.material("bust_cut", "#cfc8b9", 0.80, 0.0, 10, 0.6)


# ---------------------------------------------------------------- 01 the start montage on the head
def head_map():
    d = np.load(DATA / "head_makehuman.npz")
    V, F = d["V"].astype(float), d["F"].astype(np.int64)
    E = json.loads((DATA / "head_electrodes.json").read_text())
    skin = R.Skin(V, F)
    sc = R.Scene().add(V, F, "bust", smooth=True)
    pos = {k: np.array(v["pos"]) for k, v in E["channels"].items()}
    stickers(sc, skin, {"E1": pos["Fp1"], "REF": pos["M1"]})
    cam = R.Camera.orbit(38, 12)
    k = 1.05
    r = R.Render(sc, cam, k, 0, 0, cut=((0, 0, 1), 606.0)).move_to(172, 14)
    pg = Page(int(r.image_box()[3] + 40))
    pg.image(r)

    def P(p):
        return r.to_svg(np.atleast_2d(p))[0]
    # 10-20 sites the text talks about, as small marks on the skin where they can be seen
    for c in ("Fz", "C3", "P7", "O1", "F7", "T7"):
        if r.visible(pos[c][None], tol=2.0)[0]:
            x, y = P(pos[c])
            pg.items.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="#e7e2d6" stroke="#0b0d33" stroke-width="1.2"/>')
            pg.text(x, y - 6, c, "#0b0d33", 10, "middle", 700, 0.3)
    x, y = P(pos["Fp1"])
    pg.leader([(x - 14, y - 4), (166, y - 40), (156, y - 40)], E1C)
    pg.label(150, y - 44, "E1 · FP1", ["LEFT FOREHEAD", "ABOVE THE EYEBROW"], E1C, "end")
    x, y = P(pos["M1"])
    pg.leader([(x + 12, y + 6), (436, y + 40), (446, y + 40)], REFC)
    pg.label(452, y + 36, "REF · M1", ["BONE BEHIND", "THE LEFT EAR"], REFC)
    pg.label(452, 60, "BIAS · M2", ["SAME SPOT, RIGHT", "EAR, HIDDEN HERE"], BIASC)
    pg.text(150, pg.h - 14, "STICKERS AT TRUE SIZE", MUTED, 10.5, "end")
    pg.save("head-map.svg", "Adult head seen from the front left: E1 sticker on the left forehead at Fp1, REF on the bone behind the left ear, BIAS behind the right ear")


# ---------------------------------------------------------------- 02 forearm EMG
def forearm():
    elbow, hand = np.array([-312.9, 13.2, 349.3]), np.array([-431.2, 175.7, 245.2])
    shoulder = np.array([-167.7, 14.6, 524.6])
    ax = hand - elbow
    L = np.linalg.norm(ax)
    u = ax / L
    d = (elbow - shoulder) / np.linalg.norm(elbow - shoulder)
    c0 = elbow - d * 30.0                                   # upper arm cut 30 mm above the elbow
    c1 = elbow + u * L * 1.06                               # hand cut across the palm, past the wrist

    def keep(C):
        t = (C - elbow) @ u / L
        return (C[:, 0] < -200) & (C[:, 2] > 150) & (C[:, 2] < 470) & (t < 1.25)
    V, F, cap = body_mesh(keep, 1, cut=[(tuple(d), float(c0 @ d)), (tuple(-u), float(-(c1 @ u)))])
    skin = R.Skin(V, F[~cap])
    sc = R.Scene().add(V, F[~cap], "bust", smooth=True).add(V, F[cap], "bust_cut")
    look = np.array([-1.0, -0.42, 0.18])
    look = look - (look @ u) * u
    look /= np.linalg.norm(look)
    up = np.cross(look, u)
    up = up if up[2] > 0 else -up
    cam = R.Camera(look, up=up)

    def on_arm(f, side=0.0):
        """Skin on the palm side of the forearm, a fraction f from elbow to wrist."""
        p = elbow + u * L * f + up * side
        q, n = skin.project((p - cam.d * 80)[None])
        return q[0]
    spots = {"E1": on_arm(0.24), "E2": on_arm(0.38), "E3": on_arm(0.52), "E4": on_arm(0.66),
             "REF": on_arm(-0.04, 14), "BIAS": on_arm(0.90, -8)}
    stickers(sc, skin, spots)
    k = 1.55
    r = R.Render(sc, cam, k, 0, 0).move_to(40, 50)
    pg = Page(int(r.image_box()[3] + 130))
    pg.image(r)

    def P(p):
        return r.to_svg(np.atleast_2d(p))[0]
    for lead, col in [("E1", E1C), ("E2", E2C), ("E3", E3C), ("E4", E4C)]:
        x, y = P(spots[lead])
        pg.leader([(x, y - 22), (x, 40)], col)
        pg.text(x, 32, lead, col, 12, "middle", 600, 1.2)
    ybot = r.image_box()[1] + r.image_box()[3]
    x, y = P(spots["REF"])
    pg.leader([(x, y + 22), (x, ybot + 14)], REFC)
    pg.label(x, ybot + 30, "REF", ["ELBOW BONE"], REFC, "middle")
    x, y = P(spots["BIAS"])
    pg.leader([(x, y + 22), (x, ybot + 14)], BIASC)
    pg.label(x, ybot + 30, "BIAS", ["WRIST BONE"], BIASC, "middle")
    pg.text(W / 2, pg.h - 8, "LEFT FOREARM, PALM SIDE. EACH CHANNEL READS ITS STICKER AGAINST REF", MUTED, 10.5, "middle")
    pg.save("placement-forearm.svg", "Left forearm, palm side: four stickers E1 to E4 along the forearm flexors, REF on the elbow bone, BIAS on the wrist bone")


# ---------------------------------------------------------------- 03 chest ECG
def chest():
    cut = [((0, 0, 1), 262.0), ((0, 0, -1), -598.0), ((1, 0, 0), -205.0), ((-1, 0, 0), -205.0)]
    V, F, cap = body_mesh(lambda C: (C[:, 2] > 140) & (C[:, 2] < 680) & (np.abs(C[:, 0]) < 300), 1, cut=cut)
    skin = R.Skin(V, F[~cap])
    sc = R.Scene().add(V, F[~cap], "bust", smooth=True).add(V, F[cap], "bust_cut")
    spots = {"E1": front_point(skin, -72, 490), "REF": front_point(skin, 72, 490),
             "E3": front_point(skin, -82, 372), "E2": front_point(skin, -95, 300), "BIAS": front_point(skin, 95, 300)}
    stickers(sc, skin, spots)
    cam = R.Camera.orbit(80, 6)
    k = 0.8
    r = R.Render(sc, cam, k, 0, 0).move_to(128, 16)
    pg = Page(int(r.image_box()[3] + 40))
    pg.image(r)

    def P(p):
        return r.to_svg(np.atleast_2d(p))[0]
    labels = [("E1", "LEAD I", ["BELOW THE LEFT", "COLLARBONE"], E1C, "R"), ("E3", "V4", ["5TH RIB SPACE,", "LEFT"], E3C, "R"),
              ("E2", "LEAD II", ["LOWER LEFT RIBS"], E2C, "R"),
              ("REF", "", ["BELOW THE RIGHT", "COLLARBONE"], REFC, "L"), ("BIAS", "", ["LOWER RIGHT RIBS"], BIASC, "L")]
    for lead, what, where, col, side in labels:
        x, y = P(spots[lead])
        if side == "R":
            lx = r.image_box()[0] + r.image_box()[2] + 6
            pg.leader([(x + 14, y), (lx - 8, y)], col)
            pg.label(lx, y + 4, f"{lead}{' · ' + what if what else ''}", where, col)
        else:
            lx = r.image_box()[0] - 6
            pg.leader([(x - 14, y), (lx + 8, y)], col)
            pg.label(lx, y + 4, lead, where, col, "end")
    pg.text(W / 2, pg.h - 12, "EACH CHANNEL AGAINST REF, SO E1 GIVES LEAD I AND E2 LEAD II", MUTED, 10.5, "middle")
    pg.save("placement-chest.svg", "Chest seen from the front: E1 below the left collarbone, E3 at V4, E2 on the lower left ribs, REF below the right collarbone, BIAS on the lower right ribs")


# ---------------------------------------------------------------- 04 power: powerbank, cable, Pi
def powerbank():
    sc = R.Scene()
    P3.raspberry_pi(sc)
    P3.pieeg(sc)
    pb = (-6.0, -122.0, -2.0, 98.0, -56.0, 14.0)
    V, F = R.box(*pb)
    R.material("powerbank", "#3a3d57", 0.80, 0.25, 30, 0.5)
    R.material("usb", "#b0465a", 0.75, 0.25, 30, 0.6)
    sc.add(V, F, "powerbank")
    mu = np.array([10.6, -0.6, P3.PI_T + 1.3])
    m_end = mu + [0, -20.0, 0]

    def obox(a, b, w, h, mat):
        a, b = np.asarray(a, float), np.asarray(b, float)
        axv = (b - a) / np.linalg.norm(b - a)
        side = np.cross(axv, [0, 0, 1.0])
        side /= np.linalg.norm(side)
        nrm = np.cross(side, axv)
        Vb = np.array([c + side * sx * w / 2 + nrm * sy * h / 2 for c in (a, b) for sx, sy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])
        Fb = np.array([[0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7], [0, 3, 2], [0, 2, 1], [4, 5, 6], [4, 6, 7]])
        sc.add(Vb, Fb, mat)
    obox(mu, m_end, 10.5, 6.5, "plastic")
    pa = np.array([62.0, -56.0, 6.0])
    a_end = pa + [0, 24.0, 0]
    obox(pa, a_end, 16.0, 8.5, "plastic")
    path = P3.hang(m_end, (0, -1, 0), a_end, 150.0, d1=np.array([0, -1.0, 0]), floors=[((0, 0, 1), -2.0)],
                   boxes=[(0, 0, -2, 87, 56, 14), pb], radius=1.6)
    Vc, Fc = R.tube(P3.smooth_path(path), 1.6, 10)
    sc.add(Vc, Fc, "usb", smooth=True)
    cam = R.Camera.orbit(-62, 36)
    k = 2.2
    r = R.Render(sc, cam, k, 0, 0, catcher=-2.0).move_to(160, 20)
    pg = Page(int(r.image_box()[3] + 70))
    pg.image(r)

    def P(p):
        return r.to_svg(np.atleast_2d(p))[0]
    x, y = P([46, -122, 2])
    ybot = r.image_box()[1] + r.image_box()[3]
    pg.leader([(x, y), (x, ybot + 2)], FG)
    pg.label(x, ybot + 18, "POWERBANK, 5 V", ["CHARGED, NOT CHARGING,", "WHILE STICKERS ARE ON"], FG, "middle")
    x, y = P(mu + [0, -8, 3])
    pg.leader([(x, y), (150, y)], ACCENT)
    pg.label(144, y + 4, "INTO PWR IN", ["OFFICIAL MICRO USB", "CABLE, SHORTENED"], ACCENT, "end")
    x, y = P([40, 30, P3.PE_TOP + 0.5])
    pg.leader([(x, y), (x + 40, 30), (W - 140, 30)], ACCENT)
    pg.label(W - 134, 34, "PIEEG-8 ON PI 3", [], ACCENT)
    pg.save("powerbank.svg", "Raspberry Pi 3 with the PiEEG-8 on top, powered by a power bank through a micro USB cable into PWR IN")


# ---------------------------------------------------------------- 05 mounting the shield
def shield():
    sc = R.Scene()
    P3.raspberry_pi(sc)
    lift = 26.0
    sub = R.Scene()
    P3.pieeg(sub)
    for V, F, M in zip(sub.V, sub.F, sub.M):
        sc.add(V + [0, 0, lift], F - F.min(), M)
    cam = R.Camera.orbit(-58, 30)
    k = 2.55
    r = R.Render(sc, cam, k, 0, 0, catcher=-2.0).move_to(150, 12)
    pg = Page(int(r.image_box()[3] + 24))
    pg.image(r)

    def P(p):
        return r.to_svg(np.atleast_2d(p))[0]
    p1 = P3.PI["gpio_pin1"]
    a, b = P([*p1, P3.PI_T + P3.HDR_BASE + P3.PIN_UP]), P([*p1, P3.PE_Z0 + lift])
    pg.line(a[0], a[1], b[0], b[1], ACCENT, 1.2, "3 3")
    x, y = P([*p1, P3.PE_TOP + lift])
    pg.leader([(x, y), (x - 40, y - 20), (146, y - 20)], ACCENT)
    pg.label(140, y - 16, "PIN 1", ["ON BOTH BOARDS,", "AT THE MICROSD END"], ACCENT, "end")
    x, y = P([30, 54, P3.PE_TOP + lift])
    pg.leader([(x, y), (x + 30, y - 40), (W - 150, y - 40)], FG)
    pg.label(W - 144, y - 36, "40 PIN SOCKET", ["STRAIGHT DOWN ONTO", "THE PI'S PINS"], FG)
    x, y = P([P3.PIEEG["header_x"], 20, P3.EL_PIN_TOP + lift])
    pg.leader([(x, y), (x - 20, y + 70), (146, y + 70)], FG)
    pg.label(140, y + 74, "ELECTRODE PINS", ["POINT UP"], FG, "end")
    x, y = P([80, 30, P3.PI_T + 16])
    pg.leader([(x, y), (x + 20, y + 40), (W - 150, y + 40)], MUTED)
    pg.label(W - 144, y + 44, "USB AND ETHERNET", ["STAY FREE"], FG)
    pg.save("shield-orientation.svg", "PiEEG-8 held above the Raspberry Pi 3, pin 1 lined up with pin 1 at the microSD end, ready to press straight down")


# ---------------------------------------------------------------- 06 one lead, sticker to pin
def electrodes():
    sc = R.Scene()
    flat_V = np.array([[x, y, 0.0] for x in np.linspace(-30, 60, 20) for y in np.linspace(-40, 40, 20)])
    # a flat patch of 'skin' for the sticker
    gx, gy = np.meshgrid(np.linspace(-40, 40, 41), np.linspace(-40, 40, 41))
    GV = np.c_[gx.ravel(), gy.ravel(), np.zeros(gx.size)]
    GF = []
    for i in range(40):
        for j in range(40):
            a = i * 41 + j
            GF += [[a, a + 1, a + 42], [a, a + 42, a + 41]]
    skin = R.Skin(GV, np.array(GF))
    v, f, m, c, n = R.sticker_mesh(skin, np.array([0.0, 0.0, 0.0]), "rim_E1")
    sc.add(v, f, m)
    stud = c + n * (R.FOAM_T + R.STUD_H)
    # header block with one pin, at the far end
    pin = np.array([250.0, 0.0, 0.0])
    sc.add(*R.box(pin[0] - 1.27, -1.27, 0, pin[0] + 1.27, 1.27, 2.5), "plastic")
    total, clip = 382.0, 24.0
    j0, j1 = 172.0, 200.0
    top = pin + [0, 0, 2.5 + P3.HOUSING_L]
    path = P3.hang(top, (0, 0, 1), stud, total, n=110, floors=[((0, 0, 1), 0.0)],
                   via=[(250, 40, 3), (190, 70, 2), (110, -50, 2), (40, 40, 2), (10, 10, 6)],
                   rigid=[(j0, j1), (total - clip, total)], heavy=[(j0, j1, 6.0), (total - clip, total, 18.0)])
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]

    def at(s):
        return np.array([np.interp(s, arc, path[:, j]) for j in range(3)])

    def obox(a, b, w, h, mat, off=0.0, up=(0, 0, 1.0)):
        a, b = np.asarray(a, float), np.asarray(b, float)
        axv = (b - a) / np.linalg.norm(b - a)
        side = np.cross(axv, up)
        side /= np.linalg.norm(side)
        nrm = np.cross(side, axv)
        Vb = np.array([cc + side * sx * w / 2 + nrm * (off + sy * h / 2) for cc in (a, b) for sx, sy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])
        Fb = np.array([[0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7], [0, 3, 2], [0, 2, 1], [4, 5, 6], [4, 6, 7]])
        sc.add(Vb, Fb, mat)
    obox(pin + [0, 0, 2.5], top, P3.HOUSING_W, P3.HOUSING_W, "housing", up=(1.0, 0, 0))
    P3.add_cable(sc, np.r_[path[arc < j0], [at(j0)]], "wire_E1")
    P3.add_cable(sc, np.r_[[at(j1)], path[(arc > j1) & (arc < total - clip)], [at(total - clip)]], "wire_E1")
    obox(at(j0), at(j0 + 14), P3.HOUSING_W, P3.HOUSING_W, "housing")
    obox(at(j0 + 14), at(j1), P3.HOUSING_W, P3.HOUSING_W, "housing")
    a, b = at(total - clip), path[-1]
    mid = a + (b - a) * 0.4
    obox(a, mid, 5.0, 5.0, "wire_E1")
    for off in (1.3, -1.3):
        obox(a + (b - a) * 0.36, b + (b - a) / np.linalg.norm(b - a) * 2.0, 4.2, 0.9, "metal", off)
    cam = R.Camera.orbit(-80, 55)
    k = 1.6
    r = R.Render(sc, cam, k, 0, 0, catcher=0.0).move_to(20, 50)
    pg = Page(int(r.image_box()[3] + 140))
    pg.image(r)

    def P(p):
        return r.to_svg(np.atleast_2d(p))[0]
    items = [("STICKER", ["Ø 26 MM, SNAP IN THE MIDDLE"], c, E1C, -1),
             ("CLIP", ["BITES THE SNAP, NOT THE FOAM"], at(total - 12), FG, 1),
             ("JOINT", ["CLIP CABLE ONTO THE JUMPER"], at(j0 + 14), FG, 1),
             ("ONTO THE PIN", ["JUMPER'S FEMALE END"], top, ACCENT, 2)]
    for title, sub, p, col, side in items:
        x, y = P(p)
        if side == 2:      # below and to the right, clear of the arch
            ty = y + 46
            pg.leader([(x, y), (x, ty), (x + 8, ty)], col)
            pg.label(x + 12, ty + 4, title, sub, col, "start")
            continue
        ty = y - 40 if side < 0 else y + 40
        lx = min(max(x, 112), W - 112)
        pg.leader([(x, y), (x, ty), (lx, ty)], col)
        pg.label(lx, ty - 20 if side < 0 else ty + 14, title, sub, col, "middle")
    pg.text(W / 2, pg.h - 10, "ONE LEAD, 40 CM: 20 CM CLIP CABLE + 20 CM JUMPER", MUTED, 10.5, "middle")
    pg.save("electrodes.svg", "One complete lead: electrode sticker with the alligator clip on its snap, 20 cm clip cable, the joint, 20 cm jumper, and its female end on a 2.54 mm pin")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    which = sys.argv[3:] or ["head_map", "forearm", "chest", "powerbank", "shield", "electrodes"]
    for name in which:
        globals()[name]()
