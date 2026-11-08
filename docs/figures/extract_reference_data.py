"""
Extract the reference data the figures are drawn from, so every coordinate in them
has a published source. Run once; make_figures.py only reads the JSON files it writes.

    pip install mne ezdxf pandas openpyxl scipy trimesh
    python extract_reference_data.py

1. Electrode positions: MNE-Python's standard 10-20 montage (head coordinates, mm).
2. Raspberry Pi 3 Model B top view: Raspberry Pi Ltd's official mechanical drawing
   (DXF, RPI-3B-V1_2), board outline, component outlines and the 40 pin header.
3. The EEG trace in the README banner: 6 s of PiEEG's published example recording
   output3.xlsx, channel 8, 1 to 40 Hz, where it shows a clear alpha rhythm.
4. The head: the MakeHuman base mesh (CC0, github.com/makehumancommunity/makehuman), head and
   neck only, smoothed, with the 10-20 electrodes registered onto it from the montage in 1.
"""

import json
import math
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DXF_URL = ("https://pip-assets.raspberrypi.com/categories/520-raspberry-pi-3-model-b/documents/"
           "RP-008334-DS-1-raspberry-pi-3-b-mechanical-drawing.dxf")

CHANNELS = ["Fp1", "Fpz", "Fp2", "AFz", "F7", "F3", "Fz", "F4", "F8", "FCz", "T7", "C3", "Cz", "C4", "T8", "CPz", "POz",
            "P7", "P3", "Pz", "P4", "P8", "O1", "Oz", "O2", "Iz", "M1", "M2", "A1", "A2", "TP9", "TP10"]


def electrodes():
    import mne
    name = "colin27_1020" if "colin27_1020" in mne.channels.get_builtin_montages() else "standard_1020"
    montage = mne.channels.make_standard_montage(name)
    pos = montage.get_positions()
    out = {"source": f"MNE-Python {mne.__version__}, make_standard_montage('{name}')",
           "units": "mm, the montage's MRI frame (fsaverage surface RAS): x to the right ear, y to the nose, z up",
           "fiducials": {k: [round(float(v) * 1000, 2) for v in pos[k]] for k in ("nasion", "lpa", "rpa")},
           "channels": {c: [round(float(v) * 1000, 2) for v in pos["ch_pos"][c]] for c in CHANNELS}}
    (DATA / "electrodes_1020.json").write_text(json.dumps(out, indent=1))


def bulge_points(p0, p1, bulge, n=8):
    """Points along a DXF polyline arc segment (bulge = tan(angle / 4))."""
    if abs(bulge) < 1e-9:
        return [p1]
    (x0, y0), (x1, y1) = p0, p1
    ang = 4 * math.atan(bulge)
    chord = math.hypot(x1 - x0, y1 - y0)
    r = chord / (2 * math.sin(ang / 2))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    d = math.sqrt(max(r * r - (chord / 2) ** 2, 0)) * (1 if bulge > 0 else -1)
    cx, cy = mx - d * (y1 - y0) / chord, my + d * (x1 - x0) / chord
    a0 = math.atan2(y0 - cy, x0 - cx)
    return [(cx + abs(r) * math.cos(a0 + ang * k / n), cy + abs(r) * math.sin(a0 + ang * k / n)) for k in range(1, n + 1)]


def raspberry_pi():
    import ezdxf
    path = DATA / "raspberry-pi-3-b-mechanical-drawing.dxf"
    if not path.exists():
        urllib.request.urlretrieve(DXF_URL, path)
    msp = ezdxf.readfile(path).modelspace()

    def poly(e):
        vs = list(e.vertices)
        pts = [(vs[0].dxf.location.x, vs[0].dxf.location.y)]
        for a, b in zip(vs, vs[1:] + ([vs[0]] if e.is_closed else [])):
            pts += bulge_points((a.dxf.location.x, a.dxf.location.y), (b.dxf.location.x, b.dxf.location.y), a.dxf.bulge)
        return [[round(x, 3), round(y, 3)] for x, y in pts]

    outline = [poly(e) for e in msp if e.dxf.layer == "BOARD_OUTLINE"][0]
    parts = [poly(e) for e in msp if e.dxftype() == "POLYLINE" and e.dxf.layer == "PARTS_TOP"]
    pins = [[round(e.dxf.center.x, 3), round(e.dxf.center.y, 3)] for e in msp
            if e.dxftype() == "CIRCLE" and e.dxf.layer == "PINS_TOP" and abs(e.dxf.radius - 0.8) < 1e-6
            and 7 < e.dxf.center.x < 58 and 49.5 < e.dxf.center.y < 55.5]
    pins.append([8.37, 51.23])  # pin 1 is drawn as a square pad (7.57..9.17, 50.43..52.03)
    bottom = []
    for e in msp:
        if e.dxftype() == "POLYLINE" and e.dxf.layer == "PARTS_BOTTOM":
            q = poly(e)
            xs, ys = [a for a, b in q], [b for a, b in q]
            if (max(xs) - min(xs)) * (max(ys) - min(ys)) > 40:
                bottom.append([round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)])
    out = {"source": "Raspberry Pi Ltd, Raspberry Pi 3 Model B mechanical drawing RPI-3B-V1_2 (DXF), " + DXF_URL,
           "parts_bottom_boxes": bottom,
           "units": "mm, origin at the board's bottom left corner, y up, top view",
           "outline": outline, "parts_top": parts, "gpio_pins": sorted(pins), "gpio_pin1": [8.37, 51.23],
           "mounting_holes": {"centers": [[3.5, 3.5], [61.5, 3.5], [3.5, 52.5], [61.5, 52.5]], "diameter": 2.75},
           "heights_mm": {"gpio_header": 8.5, "usb": 16.0, "ethernet": 13.5, "hdmi": 6.5, "audio": 6.0}}
    (DATA / "raspberry_pi_3b.json").write_text(json.dumps(out, separators=(",", ":")))


def hero_trace():
    import io
    import numpy as np
    import pandas as pd
    from scipy import signal
    url = "https://raw.githubusercontent.com/pieeg-club/PiEEG-8/main/1.GUI/dataset/output3.xlsx"
    raw = pd.read_excel(io.BytesIO(urllib.request.urlopen(url, timeout=60).read())).iloc[:, :8].to_numpy(float)
    fs, ch, t0, t1 = 250, 8, 30.0, 36.0
    x = raw[:, ch - 1] - raw[:, ch - 1].mean()
    y = signal.sosfiltfilt(signal.butter(4, [1, 40], btype="band", fs=fs, output="sos"), x)
    seg = y[int(t0 * fs):int(t1 * fs)]
    f, p = signal.welch(seg, fs=fs, nperseg=2 * fs)
    band = (f >= 8) & (f <= 13)
    out = {"source": url, "channel": ch, "start_s": t0, "end_s": t1, "sample_rate_hz": fs,
           "filter": "Butterworth bandpass 1 to 40 Hz, order 4, zero phase (sosfiltfilt)",
           "alpha_peak_hz": round(float(f[band][np.argmax(p[band])]), 1),
           "microvolts": [round(float(v), 2) for v in seg]}
    (DATA / "hero_trace.json").write_text(json.dumps(out, separators=(",", ":")))


MAKEHUMAN_URL = "https://raw.githubusercontent.com/makehumancommunity/makehuman/master/makehuman/data/3dobjs/base.obj"


def head_model():
    """MakeHuman's CC0 base mesh: head and neck, in mm, oriented like the montage (x to the right
    ear, y to the nose, z up), smoothed by two Loop subdivisions. Landmarks are picked by rule
    (nasion: deepest midline point between brow and nose; preauricular points: skin in front of
    the tragus; inion: back of the skull where the neck begins; Cz: half way along the nasion to
    inion arc over the scalp). The montage's electrodes are mapped onto this head by the affine
    transform that best matches these five landmarks, then moved to the nearest skin point:
    the same idea as fitting a template montage to a subject's head in MNE."""
    import collections
    import numpy as np
    import trimesh
    from scipy.spatial import cKDTree
    path = DATA / "makehuman_base.obj"
    if not path.exists():
        urllib.request.urlretrieve(MAKEHUMAN_URL, path)
    verts, groups, g = [], collections.defaultdict(list), None
    for line in path.read_text().splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("g "):
            g = line.split()[1]
        elif line.startswith("f "):
            groups[g].append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
    v = np.array(verts)
    V = np.c_[-v[:, 0], v[:, 2], v[:, 1]] * 100            # MakeHuman: x = her left, y up, z forward, dm
    tris = [[f[0], f[i], f[i + 1]] for name in ("body", "helper-l-eye", "helper-r-eye")
            for f in groups[name] for i in range(1, len(f) - 1)]
    F = np.array(tris)
    pupils = {}                                              # front of each eye helper: the pupil
    for side, name in (("pupil_l", "helper-l-eye"), ("pupil_r", "helper-r-eye")):
        P = V[sorted({i for f in groups[name] for i in f})]
        c = P.mean(0)
        pupils[side] = [round(float(c[0]), 2), round(float(P[:, 1].max()), 2), round(float(c[2]), 2)]
    F = F[V[F].min(axis=1)[:, 2] > 560]
    m = trimesh.Trimesh(V, F, process=True)
    m.remove_unreferenced_vertices()
    for _ in range(2):
        vv, ff = trimesh.remesh.subdivide_loop(m.vertices, m.faces, iterations=1)
        m = trimesh.Trimesh(vv, ff, process=True)
    keep = m.vertices[m.faces].min(axis=1)[:, 2] > 600
    m = trimesh.Trimesh(m.vertices, m.faces[keep], process=True)
    m.remove_unreferenced_vertices()
    V, F = m.vertices, m.faces
    # landmarks
    mid = V[np.abs(V[:, 0]) < 0.8]

    def band(z, pts):
        return pts[np.abs(pts[:, 2] - z) < 1.5]
    prof = [(z, band(z, mid[mid[:, 1] > 100])[:, 1].max()) for z in np.arange(725, 746, 1.0)]
    zn = min(prof, key=lambda t: t[1])[0]
    nasion = band(zn, mid[mid[:, 1] > 100])[np.argmax(band(zn, mid[mid[:, 1] > 100])[:, 1])]

    def lateral(y, z, side):
        s = V[(np.abs(V[:, 1] - y) < 1.5) & (np.abs(V[:, 2] - z) < 1.5) & (V[:, 0] * side > 0)]
        return s[np.argmax(s[:, 0] * side)]
    ear_z = 707.5                                            # ear canal height, from the auricle
    lpa, rpa = lateral(62.5, ear_z, -1), lateral(62.5, ear_z, 1)
    back = mid[mid[:, 1] < 40]
    inion = band(717, back)[np.argmin(band(717, back)[:, 1])]
    # midline arc nasion -> vertex -> inion, ordered by angle around the head's centre
    c = np.array([0, (nasion[1] + inion[1]) / 2, (nasion[2] + inion[2]) / 2])
    arc = mid[(mid[:, 2] >= min(nasion[2], inion[2]) - 2)]
    ang = np.arctan2(arc[:, 2] - c[2], arc[:, 1] - c[1])
    a0, a1 = np.arctan2(nasion[2] - c[2], nasion[1] - c[1]), np.arctan2(inion[2] - c[2], inion[1] - c[1]) % (2 * np.pi)
    arc, ang = arc[(ang >= a0) & ((ang % (2 * np.pi)) <= a1)], ang[(ang >= a0) & ((ang % (2 * np.pi)) <= a1)]
    bins = np.linspace(a0, a1, 400)
    line = [nasion] + [arc[np.abs(ang - b) < 0.012].mean(0) for b in bins[1:-1] if (np.abs(ang - b) < 0.012).any()] + [inion]
    line = np.array(line)
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
    at = lambda f: line[np.searchsorted(seg, f * seg[-1])]
    marks = {name: at(f) for name, f in [("Fpz", .1), ("Fz", .3), ("Cz", .5), ("Pz", .7), ("Oz", .9)]}
    # affine fit montage -> this head
    mont = json.loads((DATA / "electrodes_1020.json").read_text())
    src = np.array([mont["fiducials"]["nasion"], mont["fiducials"]["lpa"], mont["fiducials"]["rpa"],
                    mont["channels"]["Iz"], mont["channels"]["Cz"]])
    dst = np.array([nasion, lpa, rpa, inion, marks["Cz"]])
    A, *_ = np.linalg.lstsq(np.c_[src, np.ones(len(src))], dst, rcond=None)
    tree = cKDTree(V)
    vn = m.vertex_normals
    chans = {}
    for name, p in mont["channels"].items():
        q = np.r_[p, 1] @ A
        _, i = tree.query(q)
        chans[name] = {"pos": [round(float(x), 2) for x in V[i]], "normal": [round(float(x), 4) for x in vn[i]]}
    # Mastoids: the template's M1 and M2 land under the earlobes on this head, so they are set by
    # anatomy instead: the skin over the mastoid bone, right behind the lower half of the ear
    # (the auricle's back edge is at y = 36 mm here; a 26 mm sticker centred at y = 24 mm touches it).
    for name, side in (("M1", -1), ("M2", 1)):
        _, i = tree.query(lateral(24.0, 697.0, side))
        chans[name] = {"pos": [round(float(x), 2) for x in V[i]], "normal": [round(float(x), 4) for x in vn[i]]}
    residual = float(np.sqrt(((np.c_[src, np.ones(len(src))] @ A - dst) ** 2).sum(1).mean()))
    out = {"source": "MakeHuman base mesh (CC0), " + MAKEHUMAN_URL,
           "units": "mm, x to the right ear, y to the nose, z up (origin from the MakeHuman mesh)",
           "registration": f"affine fit of the montage in electrodes_1020.json to 5 landmarks, rms residual {residual:.1f} mm, then nearest skin point; M1 and M2 set on the mastoid bone behind the lower half of the ear",
           "landmarks": {"nasion": nasion.round(2).tolist(), "lpa": lpa.round(2).tolist(), "rpa": rpa.round(2).tolist(),
                         "inion": inion.round(2).tolist(), **pupils},
           "midline_arc": {"points": line[::4].round(2).tolist(), "length_mm": round(float(seg[-1]), 1),
                           "marks": {k: v.round(2).tolist() for k, v in marks.items()}},
           "channels": chans}
    (DATA / "head_electrodes.json").write_text(json.dumps(out, indent=1))
    np.savez_compressed(DATA / "head_makehuman.npz", V=V.astype(np.float32), F=F.astype(np.int32))
    print("head:", len(V), "vertices,", len(F), "faces, landmark fit rms", round(residual, 1), "mm")


BUST_CUT = [((0, 0, 1), 480.0), ((1.571, 0, 1), 269.3), ((-1.571, 0, 1), 269.3)]   # chest, and up over each arm


def bust_model():
    """The same MakeHuman mesh with neck and shoulders, cut like a classical bust (chest flat, the arms
    cut by a plane rising toward each shoulder, every cut closed), for the scene in FIG. 01. One Loop
    subdivision. Needs trimesh with networkx and mapbox_earcut for the caps."""
    import collections
    import numpy as np
    import trimesh
    path = DATA / "makehuman_base.obj"
    if not path.exists():
        urllib.request.urlretrieve(MAKEHUMAN_URL, path)
    verts, groups, g = [], collections.defaultdict(list), None
    for line in path.read_text().splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("g "):
            g = line.split()[1]
        elif line.startswith("f "):
            groups[g].append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
    v = np.array(verts)
    V = np.c_[-v[:, 0], v[:, 2], v[:, 1]] * 100
    tris = np.array([[f[0], f[i], f[i + 1]] for name in ("body", "helper-l-eye", "helper-r-eye")
                     for f in groups[name] for i in range(1, len(f) - 1)])
    m = trimesh.Trimesh(V, tris[V[tris].min(axis=1)[:, 2] > 360], process=True)
    m.remove_unreferenced_vertices()
    vv, ff = trimesh.remesh.subdivide_loop(m.vertices, m.faces, iterations=1)
    m = trimesh.Trimesh(vv, ff, process=True)
    cap = []
    for n, d in BUST_CUT:                       # cut and close each cut with a flat face, like stone
        n = np.array(n, float)
        k = np.linalg.norm(n)
        m = m.slice_plane(n / k * d / k, n / k, cap=True)
    C, fn = m.triangles_center, m.face_normals
    cap = np.zeros(len(m.faces), bool)
    for n, d in BUST_CUT:
        n = np.array(n, float)
        k = np.linalg.norm(n)
        cap |= (np.abs(C @ (n / k) - d / k) < 0.05) & (fn @ (n / k) < -0.99)
    np.savez_compressed(DATA / "bust_makehuman.npz", V=m.vertices.astype(np.float32), F=m.faces.astype(np.int32),
                        cap=cap)
    print(f"bust: {len(m.vertices)} vertices, {len(m.faces)} faces, {cap.sum()} on the cuts")


if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    electrodes()
    raspberry_pi()
    hero_trace()
    head_model()
    bust_model()
    print("wrote", *sorted(p.name for p in DATA.glob("*.json")))
