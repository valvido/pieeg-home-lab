"""
3D parts for the figures, in mm: the Raspberry Pi 3 Model B (outline, holes and part footprints from
Raspberry Pi's official DXF drawing; part heights are typical, see raspberry_pi_3b.json), the PiEEG-8
(parts measured on the top view photo in PiEEG's docs, about 1 mm; the passive parts next to the
electrode header are approximate), Dupont housings, alligator clips, and cables that hang under
gravity (a chain of short segments with bending stiffness, settled by relaxation).

Board frame: x along the Pi's long side (0 at the microSD end), y across it (0 at the HDMI edge),
z up from the bottom of the Pi's circuit board.
"""

import json
import math
from pathlib import Path

import numpy as np

import render3d as R

DATA = Path(__file__).resolve().parent / "data"
PI = json.loads((DATA / "raspberry_pi_3b.json").read_text())

# stack heights (mm)
PI_T = 1.4                       # Pi circuit board
HDR_BASE = 2.5                   # plastic base of a 2.54 mm pin header
PIN_UP = 6.0                     # male pin above its base
SOCKET_H = 8.5                   # female 2x20 socket under the PiEEG-8
PE_Z0 = PI_T + HDR_BASE + SOCKET_H          # PiEEG-8 board bottom, 12.4
PE_T = 1.6
PE_TOP = PE_Z0 + PE_T                       # 14.0
EL_BASE = PE_TOP + HDR_BASE                 # top of the electrode header's plastic, 16.5
EL_PIN_TOP = EL_BASE + PIN_UP               # 22.5
HOUSING_L, HOUSING_W = 14.0, 2.54           # female Dupont housing
WIRE_R = 0.7                                # jumper wire, about 1.4 mm across

PIEEG = {"w": 65.0, "h": 56.0, "r": 3.0, "holes": [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)],
         "header_x": 10.2, "header_top": 38.0, "ads1299": (28.2, 18.0), "led": (42.0, 18.7),
         "jumpers": [(56.6, 42.5), (56.6, 37.6), (56.6, 32.7)], "cap": (37.0, 7.0, 4.6, 7.6),
         # small ICs: centre and footprint with leads, measured as dark parts on the photo
         "ics": [(22.4, 40.4, 4.1, 3.0), (35.6, 39.0, 3.9, 3.0), (15.0, 34.8, 4.6, 3.0), (38.6, 32.9, 3.9, 4.2)]}
HEADER = ["Ref", "Biasout", "E8", "E7", "E6", "E5", "E4", "E3", "E2", "E1"]     # printed top to bottom


def pin_xy(name):
    i = HEADER.index(name)
    return PIEEG["header_x"], PIEEG["header_top"] - i * 2.54


for _name, _args in {
    "pi_pcb": ("#2d6a55", 0.80, 0.10, 30, 0.6),
    "pieeg_pcb": ("#d8a843", 0.82, 0.14, 30, 0.6),
    "metal": ("#c3c6cf", 0.55, 0.65, 40, 0.55),
    "gold": ("#e3c46f", 0.60, 0.70, 40, 0.55),
    "plastic": ("#1d1e2c", 0.80, 0.18, 30, 0.45),
    "housing": ("#34364a", 0.80, 0.35, 40, 0.40),
    "ic": ("#22232f", 0.80, 0.25, 40, 0.45),
    "tantalum": ("#d38f2a", 0.80, 0.20, 30, 0.6),
    "led": ("#f2efe2", 0.80, 0.30, 30, 0.6),
    "passive_r": ("#2a2a30", 0.80, 0.20, 30, 0.5),
    "passive_c": ("#b08d63", 0.80, 0.15, 30, 0.5),
    "white_plastic": ("#e6e3da", 0.85, 0.10, 20, 0.6),
}.items():
    R.material(_name, *_args)


def rounded_rect(w, h, r, n=8):
    pts = []
    for cx, cy, a0 in [(w - r, r, -90), (w - r, h - r, 0), (r, h - r, 90), (r, r, 180)]:
        for t in np.linspace(0, 90, n):
            a = math.radians(a0 + t)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def circle(cx, cy, r, n=20):
    return [(cx + r * math.cos(t), cy + r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, n, endpoint=False)][::-1]


def add_box(sc, b, z0, z1, mat):
    V, F = R.box(b[0], b[1], z0, b[2], b[3], z1)
    sc.add(V, F, mat)


def add_pin(sc, x, y, z0, z1, mat="gold", w=0.64):
    add_box(sc, (x - w / 2, y - w / 2, x + w / 2, y + w / 2), z0, z1, mat)


# ---------------------------------------------------------------- Raspberry Pi 3 Model B
PI_BOXES = {  # footprint from the DXF (mm), height (typical), material
    "ethernet": ((65.65, 2.5, 87.0, 18.0), 13.5, "metal"), "usb_top": ((69.3, 39.65, 87.0, 53.57), 16.0, "metal"),
    "usb_bottom": ((69.3, 21.65, 87.0, 35.57), 16.0, "metal"), "soc": ((19.98, 24.52, 33.98, 38.52), 1.2, "ic"),
    "hdmi": ((24.75, -1.5, 39.25, 10.65), 6.5, "metal"), "csi": ((43.55, 0.3, 47.5, 22.7), 5.5, "white_plastic"),
    "dsi": ((1.5, 16.8, 5.45, 39.2), 5.5, "white_plastic"), "audio": ((50.0, 0.0, 57.0, 12.5), 6.0, "plastic"),
    "lan": ((55.4, 29.2, 64.4, 38.2), 1.0, "ic"), "micro_usb": ((6.85, -0.6, 14.35, 4.71), 2.6, "metal")}


def raspberry_pi(sc, gpio_pins=True):
    holes = [circle(cx, cy, PI["mounting_holes"]["diameter"] / 2) for cx, cy in PI["mounting_holes"]["centers"]]
    V, F = R.prism([tuple(p) for p in PI["outline"]], 0, PI_T, holes)
    sc.add(V, F, "pi_pcb")
    for name, (b, h, mat) in PI_BOXES.items():
        add_box(sc, b, PI_T, PI_T + h, mat)
    add_box(sc, (7.1, 50.0, 57.9, 55.0), PI_T, PI_T + HDR_BASE, "plastic")
    if gpio_pins:
        for x, y in PI["gpio_pins"]:
            add_pin(sc, x, y, PI_T, PI_T + HDR_BASE + PIN_UP)
    card = PI["parts_bottom_boxes"][1]                      # microSD card, under the board
    add_box(sc, card, -1.3, -0.3, "plastic")
    return sc


# ---------------------------------------------------------------- PiEEG-8
def tqfp(sc, cx, cy, z, body=10.0, n=16, pitch=0.5, lead=1.0, h=1.0):
    add_box(sc, (cx - body / 2, cy - body / 2, cx + body / 2, cy + body / 2), z, z + h, "ic")
    off = (np.arange(n) - (n - 1) / 2) * pitch
    for o in off:
        for (x0, y0, x1, y1) in [(cx + o - 0.11, cy + body / 2, cx + o + 0.11, cy + body / 2 + lead),
                                 (cx + o - 0.11, cy - body / 2 - lead, cx + o + 0.11, cy - body / 2),
                                 (cx + body / 2, cy + o - 0.11, cx + body / 2 + lead, cy + o + 0.11),
                                 (cx - body / 2 - lead, cy + o - 0.11, cx - body / 2, cy + o + 0.11)]:
            add_box(sc, (x0, y0, x1, y1), z, z + 0.25, "metal")


def small_ic(sc, cx, cy, w, h, z):
    """A small IC: body with gull wing leads on its long sides (w x h is the footprint with leads)."""
    horiz = w >= h
    L, S = (w, h) if horiz else (h, w)
    body_s = S - 1.2
    nl = 3 if L < 4.5 else 4
    if horiz:
        add_box(sc, (cx - L / 2, cy - body_s / 2, cx + L / 2, cy + body_s / 2), z, z + 1.0, "ic")
    else:
        add_box(sc, (cx - body_s / 2, cy - L / 2, cx + body_s / 2, cy + L / 2), z, z + 1.0, "ic")
    for o in (np.arange(nl) - (nl - 1) / 2) * (L / nl):
        for sgn in (-1, 1):
            if horiz:
                add_box(sc, (cx + o - 0.2, cy + sgn * body_s / 2 - (0.6 if sgn < 0 else 0),
                             cx + o + 0.2, cy + sgn * body_s / 2 + (0.6 if sgn > 0 else 0)), z, z + 0.25, "metal")
            else:
                add_box(sc, (cx + sgn * body_s / 2 - (0.6 if sgn < 0 else 0), cy + o - 0.2,
                             cx + sgn * body_s / 2 + (0.6 if sgn > 0 else 0), cy + o + 0.2), z, z + 0.25, "metal")


def pieeg(sc, used=()):
    holes = [circle(cx, cy, 1.375) for cx, cy in PIEEG["holes"]]
    V, F = R.prism(rounded_rect(PIEEG["w"], PIEEG["h"], PIEEG["r"]), PE_Z0, PE_TOP, holes)
    sc.add(V, F, "pieeg_pcb")
    add_box(sc, (7.1, 50.0, 57.9, 55.0), PI_T + HDR_BASE, PE_Z0, "plastic")      # the 2x20 socket underneath
    for x, y in PI["gpio_pins"]:                                                    # its pins through the board
        add_pin(sc, x, y, PE_TOP, PE_TOP + 1.2, "metal", 0.9)
    hx, top = PIEEG["header_x"], PIEEG["header_top"]
    add_box(sc, (hx - 1.27, top - 9 * 2.54 - 1.27, hx + 1.27, top + 1.27), PE_TOP, EL_BASE, "plastic")
    for name in HEADER:
        x, y = pin_xy(name)
        add_pin(sc, x, y, PE_TOP, EL_PIN_TOP)
    for jx, jy in PIEEG["jumpers"]:
        add_box(sc, (jx - 2.54, jy - 1.27, jx + 2.54, jy + 1.27), PE_TOP, EL_BASE, "plastic")
        add_box(sc, (jx - 2.4, jy - 1.2, jx + 2.4, jy + 1.2), EL_BASE, EL_BASE + 6.0, "plastic")
    tqfp(sc, *PIEEG["ads1299"], PE_TOP)
    for cx, cy, w, h in PIEEG["ics"]:
        small_ic(sc, cx, cy, w, h, PE_TOP)
    cx, cy, cw, ch = PIEEG["cap"]
    add_box(sc, (cx - cw / 2, cy - ch / 2 + 1.1, cx + cw / 2, cy + ch / 2 - 1.1), PE_TOP, PE_TOP + 2.8, "tantalum")
    for sgn in (-1, 1):
        y0 = cy + sgn * (ch / 2 - 0.55)
        add_box(sc, (cx - cw / 2 + 0.6, y0 - 0.55, cx + cw / 2 - 0.6, y0 + 0.55), PE_TOP, PE_TOP + 1.6, "metal")
    lx, ly = PIEEG["led"]
    add_box(sc, (lx - 0.8, ly - 0.4, lx + 0.8, ly + 0.4), PE_TOP, PE_TOP + 0.6, "led")
    for i in range(8):                      # input filter parts next to the header (approximate)
        y = 13.4 + i * 1.6
        add_box(sc, (14.0, y - 0.4, 15.6, y + 0.4), PE_TOP, PE_TOP + 0.45, "passive_r")
        add_box(sc, (18.2, y - 0.4, 19.8, y + 0.4), PE_TOP, PE_TOP + 0.6, "passive_c")
    for name in used:
        x, y = pin_xy(name)
        dupont_female(sc, x, y, EL_BASE)
    return sc


def dupont_female(sc, x, y, z0, axis=(0, 0, 1)):
    """Female Dupont housing, 2.54 mm square, 14 mm long, standing on the header's plastic."""
    w = HOUSING_W / 2 - 0.07                 # neighbours touch with a hairline gap
    add_box(sc, (x - w, y - w, x + w, y + w), z0, z0 + HOUSING_L, "housing")
    add_box(sc, (x - 0.55, y - w - 0.02, x + 0.55, y - w + 0.3), z0 + 4.5, z0 + 9.0, "metal")   # latch window
    return np.array([x, y, z0 + HOUSING_L])


def housing_top(name):
    x, y = pin_xy(name)
    return np.array([x, y, EL_BASE + HOUSING_L])


# ---------------------------------------------------------------- cables
def _relax(p0, d0, p1, length, n=70, d1=None, gravity=(0, 0, -1), stiff=0.35, floors=(), boxes=(), skin=None,
           steps=1500, radius=WIRE_R):
    """First guess for hang(): position based relaxation (inextensible links, a little bending)."""
    p0, p1, d0 = np.asarray(p0, float), np.asarray(p1, float), np.asarray(d0, float) / np.linalg.norm(d0)
    seg = length / (n - 1)
    # start: a sagging curve between the ends with the right length
    t = np.linspace(0, 1, n)[:, None]
    mid = (p0 + p1) / 2 + np.array(gravity) * 0.3 * length
    P = (1 - t) ** 2 * p0 + 2 * t * (1 - t) * mid + t ** 2 * p1
    P[1] = p0 + d0 * seg
    fixed = {0: p0, 1: p0 + d0 * seg, n - 1: p1}
    if d1 is not None:
        d1 = np.asarray(d1, float) / np.linalg.norm(d1)
        fixed[n - 2] = p1 - d1 * seg
    prev = P.copy()
    g = np.asarray(gravity, float) * 0.02 * seg
    free = np.ones(n, bool)
    free[list(fixed)] = False
    for it in range(steps):
        vel = (P - prev) * 0.96
        prev = P.copy()
        P[free] += vel[free] + g
        for _ in range(4):
            for parity in (0, 1):                       # stretch: keep each segment at its length
                i = np.arange(parity, n - 1, 2)
                d = P[i + 1] - P[i]
                L = np.linalg.norm(d, axis=1, keepdims=True)
                corr = (L - seg) / np.maximum(L, 1e-9) * d * 0.5
                wa, wb = free[i][:, None], free[i + 1][:, None]
                tot = np.maximum(wa + wb, 1)
                P[i] += corr * wa * 2 / tot
                P[i + 1] -= corr * wb * 2 / tot
            i = np.arange(0, n - 2)                     # bending: pull i+1 toward the middle of i and i+2
            m = (P[i] + P[i + 2]) / 2
            P[i + 1] += (m - P[i + 1]) * stiff * free[i + 1][:, None]
            for k, v in fixed.items():
                P[k] = v
        for (nrm, d) in floors:                         # floors: keep X . n >= d + radius
            nrm = np.asarray(nrm, float)
            s = P @ nrm - (d + radius)
            bad = (s < 0) & free
            P[bad] -= np.outer(s[bad], nrm)
        for b in boxes:                                 # boxes (x0, y0, z0, x1, y1, z1): push out the short way
            lo, hi = np.asarray(b[:3]) - radius, np.asarray(b[3:]) + radius
            inside = np.all((P > lo) & (P < hi), axis=1) & free
            if inside.any():
                Q = P[inside]
                dl, dh = Q - lo, hi - Q
                dist = np.c_[dl, dh]
                k = dist.argmin(1)
                for j, kk in enumerate(k):
                    ax = kk % 3
                    Q[j, ax] = lo[ax] if kk < 3 else hi[ax]
                P[inside] = Q
        if skin is not None:
            sd, q, nn = skin.signed_distance(P)
            bad = (sd < radius) & free
            P[bad] = q[bad] + nn[bad] * radius
    return P


def _first_guess(p0, d0, p1, length, n, g, d1=None):
    """A smooth curve of the right length: leaves along d0, sags with gravity, ends at p1."""
    D = np.linalg.norm(p1 - p0)
    t = np.linspace(0, 1, 400)[:, None]

    def curve(s):
        c1 = p0 + d0 * s * D * 0.6
        c2 = p1 + (g * s * D * 0.6 if d1 is None else -d1 * s * D * 0.6)
        return (1 - t) ** 3 * p0 + 3 * t * (1 - t) ** 2 * c1 + 3 * t ** 2 * (1 - t) * c2 + t ** 3 * p1

    def L(s):
        return np.linalg.norm(np.diff(curve(s), axis=0), axis=1).sum()
    lo, hi = 0.0, 1.0
    while L(hi) < length and hi < 64:
        hi *= 2
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if L(mid) < length else (lo, mid)
    C = curve((lo + hi) / 2)
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]
    want = np.linspace(0, arc[-1], n)
    return np.array([np.interp(want, arc, C[:, j]) for j in range(3)]).T


LAMBDA = 45.0     # bending length (EI / weight per length) ** (1/3) of a 26 AWG jumper wire, mm


def _via_guess(points, length, n, g):
    """A polyline through the waypoints, given extra sag so it has the cable's length."""
    W = np.asarray(points, float)
    seg_l = np.linalg.norm(np.diff(W, axis=0), axis=1)
    arc = np.r_[0, np.cumsum(seg_l)]
    t = np.linspace(0, arc[-1], 600)
    C = np.array([np.interp(t, arc, W[:, j]) for j in range(3)]).T
    u = t / arc[-1]

    def curve(a):
        return C + np.outer(np.sin(np.pi * u) * a, g)

    def L(a):
        return np.linalg.norm(np.diff(curve(a), axis=0), axis=1).sum()
    if L(0) < length:
        lo, hi = 0.0, 1.0
        while L(hi) < length:
            hi *= 2
        for _ in range(50):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if L(mid) < length else (lo, mid)
        C = curve((lo + hi) / 2)
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]
    want = np.linspace(0, arc[-1], n)
    return np.array([np.interp(want, arc, C[:, j]) for j in range(3)]).T


def hang(p0, d0, p1, length, n=64, d1=None, lam=LAMBDA, gravity=(0, 0, -1), floors=(), boxes=(), skin=None,
         radius=WIRE_R, via=None, rigid=(), heavy=()):
    """A cable at rest: length from p0 (leaving along d0 if given: clamped in a housing; else free to
    turn, like a clip on a snap) to p1 (arriving along d1 if given). Static equilibrium of an elastic
    rod under its own weight: bending stiffness EI = lam**3 per unit weight per mm, nearly
    inextensible, kept out of floors, boxes and the skin. rigid: arc ranges (mm from p0) that do not
    bend (a clip, two housings plugged together); heavy: (start, end, factor) ranges weighing more
    per mm. via: waypoints for the first guess, so a cable can start on the right side of the head.
    The rest shape is the minimum of the energy, found with L-BFGS."""
    from scipy.optimize import minimize
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    g = np.asarray(gravity, float)
    seg = length / (n - 1)
    if via is not None:
        start = [p0] if d0 is None else [p0, p0 + np.asarray(d0, float) / np.linalg.norm(d0) * 2 * seg]
        P = _via_guess(start + [np.asarray(v, float) for v in via] + [p1], length, n, g)
    else:
        P = _first_guess(p0, np.asarray(d0 if d0 is not None else -g, float) / np.linalg.norm(d0 if d0 is not None else -g),
                         p1, length, n, g, d1)
    fixed = {0: p0, n - 1: p1}
    if d0 is not None:
        d0 = np.asarray(d0, float) / np.linalg.norm(d0)
        fixed[1] = p0 + d0 * seg
    if d1 is not None:
        d1 = np.asarray(d1, float) / np.linalg.norm(d1)
        fixed[n - 2] = p1 - d1 * seg
    free = np.array([i not in fixed for i in range(n)])
    s_node = np.arange(n) * seg
    EI = lam ** 3
    mult = np.ones(n)
    for a_, b_ in rigid:
        mult[(s_node >= a_ - 1e-6) & (s_node <= b_ + 1e-6)] = 400.0
    wgt = np.ones(n)
    for a_, b_, f_ in heavy:
        wgt[(s_node >= a_ - 1e-6) & (s_node <= b_ + 1e-6)] = f_
    kb = (EI / seg) * mult[1:-1]
    K = 200.0 * EI / seg ** 2                    # stretch penalty: links stay within a fraction of a percent
    Kc = K

    def energy(x):
        Q = P.copy()
        Q[free] = x.reshape(-1, 3)
        for k_, v in fixed.items():
            Q[k_] = v
        G = np.zeros_like(Q)
        E = -seg * (wgt * (Q @ g)).sum()
        G += -seg * wgt[:, None] * g
        e = Q[1:] - Q[:-1]
        L = np.linalg.norm(e, axis=1)
        u = e / L[:, None]
        dl = L - seg
        E += 0.5 * K * (dl ** 2).sum()
        ge = (K * dl)[:, None] * u
        c = (u[:-1] * u[1:]).sum(1)
        E += (kb * (1 - c)).sum()
        ge[:-1] += -(u[1:] - c[:, None] * u[:-1]) / L[:-1, None] * kb[:, None]
        ge[1:] += -(u[:-1] - c[:, None] * u[1:]) / L[1:, None] * kb[:, None]
        G[1:] += ge
        G[:-1] -= ge
        for nrm, d in floors:
            nrm = np.asarray(nrm, float)
            pen = np.minimum(Q @ nrm - (d + radius), 0)
            E += 0.5 * Kc * (pen ** 2).sum()
            G += Kc * pen[:, None] * nrm
        for b in boxes:
            lo, hi = np.asarray(b[:3], float) - radius, np.asarray(b[3:], float) + radius
            inside = np.all((Q > lo) & (Q < hi), axis=1)
            if inside.any():
                dist = np.c_[Q[inside] - lo, hi - Q[inside]]
                kk = dist.argmin(1)
                pen = dist[np.arange(len(kk)), kk]
                nrm = np.zeros((len(kk), 3))
                nrm[np.arange(len(kk)), kk % 3] = np.where(kk < 3, -1.0, 1.0)
                E += 0.5 * Kc * (pen ** 2).sum()
                G[inside] += -Kc * pen[:, None] * nrm
        if skin is not None:
            sd, q, nn = skin.signed_distance(Q)
            pen = np.minimum(sd - radius, 0)
            E += 0.5 * Kc * (pen ** 2).sum()
            G += Kc * pen[:, None] * nn
        return E, G[free].ravel()
    res = minimize(energy, P[free].ravel(), jac=True, method="L-BFGS-B", options={"maxiter": 30000, "maxfun": 60000})
    P[free] = res.x.reshape(-1, 3)
    for k_, v in fixed.items():
        P[k_] = v
    return P


def cut_path(P, s):
    """The first s mm of a cable."""
    P = np.asarray(P, float)
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    i = int(np.searchsorted(arc, s))
    if i >= len(P):
        return P
    t = (s - arc[i - 1]) / (arc[i] - arc[i - 1])
    return np.r_[P[:i], [P[i - 1] + t * (P[i] - P[i - 1])]]


def smooth_path(P, k=4):
    """Catmull-Rom resampling of the node chain, so the tube is round and smooth."""
    P = np.asarray(P, float)
    Q = np.r_[[2 * P[0] - P[1]], P, [2 * P[-1] - P[-2]]]
    out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        for t in np.linspace(0, 1, k, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-1])
    return np.array(out)


def add_cable(sc, P, mat, r=WIRE_R):
    V, F = R.tube(smooth_path(P), r, 12)
    sc.add(V, F, mat, smooth=True)
