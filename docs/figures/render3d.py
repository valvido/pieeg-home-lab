"""
A small software renderer for the figures. Meshes in mm (the head, boards, stickers, cables) are
seen through an orthographic camera and shaded like a studio photograph of a plaster cast: a key
light with soft shadows, sky and floor fill, ambient occlusion from the depth buffer and a thin
darker line where one surface passes in front of another. The SVG figures place the PNG it makes
and draw labels on top with the same projection, so every label points at the right millimeter.

World coordinates: mm, x to her right ear, y to the nose, z up (the head's frame, see
extract_reference_data.head_model). Needs numpy, scipy and numba.
"""

import io
import math
from pathlib import Path

import numpy as np
from numba import njit

DATA = Path(__file__).resolve().parent / "data"


# ---------------------------------------------------------------- cameras
class Camera:
    """Orthographic camera. `look` is the viewing direction (from the camera into the scene),
    `up` the world direction shown as screen up."""

    def __init__(self, look, up=(0, 0, 1)):
        d = np.asarray(look, float)
        self.d = d / np.linalg.norm(d)
        r = np.cross(self.d, np.asarray(up, float))
        self.r = r / np.linalg.norm(r)
        self.u = np.cross(self.r, self.d)

    def project(self, P):
        """World mm -> (screen x mm, screen y mm downward, depth toward the camera)."""
        P = np.atleast_2d(np.asarray(P, float))
        return np.c_[P @ self.r, -(P @ self.u), -(P @ self.d)]

    @staticmethod
    def orbit(azimuth, elevation):
        """Camera looking at the origin from azimuth (degrees, 0 = from her left, 90 = from the front)
        and elevation (degrees above the horizon)."""
        a, e = math.radians(azimuth), math.radians(elevation)
        eye = np.array([-math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)])
        return Camera(-eye)


LEFT = Camera((1, 0, 0))                # from her left: nose to the left of the image
FRONT = Camera((0, -1, 0))              # from the front: her left on the viewer's right
TOP = Camera((0, 0, -1), up=(0, 1, 0))  # from above, nose up


# ---------------------------------------------------------------- rasterizer
@njit(cache=True)
def _raster(px, py, pz, F, W, H, zbuf, fid, b0, b1):
    for t in range(F.shape[0]):
        i0, i1, i2 = F[t, 0], F[t, 1], F[t, 2]
        ax, ay, bx, by, cx, cy = px[i0], py[i0], px[i1], py[i1], px[i2], py[i2]
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-12:
            continue
        x0 = max(int(math.floor(min(ax, bx, cx))), 0)
        x1 = min(int(math.ceil(max(ax, bx, cx))), W - 1)
        y0 = max(int(math.floor(min(ay, by, cy))), 0)
        y1 = min(int(math.ceil(max(ay, by, cy))), H - 1)
        for y in range(y0, y1 + 1):
            gy = y + 0.5
            for x in range(x0, x1 + 1):
                gx = x + 0.5
                w0 = ((bx - gx) * (cy - gy) - (by - gy) * (cx - gx)) / area
                w1 = ((cx - gx) * (ay - gy) - (cy - gy) * (ax - gx)) / area
                w2 = 1.0 - w0 - w1
                if w0 < -1e-7 or w1 < -1e-7 or w2 < -1e-7:
                    continue
                z = w0 * pz[i0] + w1 * pz[i1] + w2 * pz[i2]
                if z > zbuf[y, x]:
                    zbuf[y, x] = z
                    fid[y, x] = t
                    b0[y, x] = w0
                    b1[y, x] = w1


def rasterize(px, py, depth, F, W, H):
    zbuf = np.full((H, W), -np.inf)
    fid = np.full((H, W), -1, np.int64)
    b0 = np.zeros((H, W))
    b1 = np.zeros((H, W))
    _raster(px.astype(np.float64), py.astype(np.float64), depth.astype(np.float64),
            F.astype(np.int64), W, H, zbuf, fid, b0, b1)
    return zbuf, fid, b0, b1


# ---------------------------------------------------------------- meshes
def hex_rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


def vertex_normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for i in range(3):
        np.add.at(vn, F[:, i], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)


class Scene:
    """Triangle meshes with one material per face. smooth meshes interpolate vertex normals,
    hard surface parts (boards, housings) keep flat faces."""

    def __init__(self):
        self.V, self.F, self.M, self.N = [], [], [], []
        self.n = 0
        self.cut = None

    def add(self, V, F, mat, smooth=False):
        V, F = np.asarray(V, float), np.asarray(F, np.int64)
        mats = np.full(len(F), mat, object) if isinstance(mat, str) else np.asarray(mat, object)
        if smooth:
            vn = vertex_normals(V, F)
            N = vn[F]
        else:
            fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
            fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
            N = np.repeat(fn[:, None, :], 3, axis=1)
        self.V.append(V)
        self.F.append(F + self.n)
        self.M.append(mats)
        self.N.append(N)
        self.n += len(V)
        return self

    def arrays(self):
        return np.concatenate(self.V), np.concatenate(self.F), np.concatenate(self.M), np.concatenate(self.N)


def box(x0, y0, z0, x1, y1, z1):
    V = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    F = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                  [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    return V, F


def prism(poly, z0, z1, holes=()):
    """Extrude a 2D polygon (with optional holes) from z0 to z1."""
    import shapely
    import trimesh
    shape = shapely.Polygon(poly, holes)
    m = trimesh.creation.extrude_polygon(shape, z1 - z0)
    V = np.array(m.vertices)
    V[:, 2] += z0
    return V, np.array(m.faces)


def cylinder(p0, p1, r, n=16, caps=True):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    a = p1 - p0
    a /= np.linalg.norm(a)
    e1 = np.cross(a, [0, 0, 1.0] if abs(a[2]) < 0.9 else [1.0, 0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    ring = np.outer(np.cos(t), e1) + np.outer(np.sin(t), e2)
    V = np.r_[p0 + r * ring, p1 + r * ring, [p0, p1]]
    F = []
    for i in range(n):
        j = (i + 1) % n
        F += [[i, j, n + j], [i, n + j, n + i]]
        if caps:
            F += [[2 * n, j, i], [2 * n + 1, n + i, n + j]]
    return V, np.array(F)


def tube(path, r, n=10):
    """A round cable of radius r along a 3D polyline (parallel transport frames, no twisting)."""
    P = np.asarray(path, float)
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    ref = np.array([0, 0, 1.0]) if abs(T[0, 2]) < 0.9 else np.array([1.0, 0, 0])
    e1 = np.cross(T[0], ref)
    e1 /= np.linalg.norm(e1)
    frames = []
    for i in range(len(P)):
        if i:
            e1 = e1 - (e1 @ T[i]) * T[i]
            e1 /= np.linalg.norm(e1)
        frames.append((e1, np.cross(T[i], e1)))
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    V = np.array([P[i] + r * (np.cos(a) * frames[i][0] + np.sin(a) * frames[i][1]) for i in range(len(P)) for a in t])
    F = []
    for i in range(len(P) - 1):
        for k in range(n):
            a, b = i * n + k, i * n + (k + 1) % n
            F += [[a, b, b + n], [a, b + n, a + n]]
    V = np.r_[V, [P[0], P[-1]]]
    c0, c1 = len(V) - 2, len(V) - 1
    for k in range(n):
        F += [[c0, (k + 1) % n, k], [c1, (len(P) - 1) * n + k, (len(P) - 1) * n + (k + 1) % n]]
    return V, np.array(F)


# ---------------------------------------------------------------- the head
def load_head():
    d = np.load(DATA / "head_makehuman.npz")
    return d["V"].astype(float), d["F"].astype(np.int64)


def load_electrodes():
    import json
    return json.loads((DATA / "head_electrodes.json").read_text())


class Skin:
    """Closest point queries on the head (nearest vertex, then onto its tangent plane)."""

    def __init__(self, V, F):
        from scipy.spatial import cKDTree
        used = np.unique(F)
        self.V, self.F = V[used], F
        self.vn = vertex_normals(V, F)[used]
        self.tree = cKDTree(self.V)

    def project(self, P):
        P = np.atleast_2d(np.asarray(P, float))
        _, i = self.tree.query(P, k=6)
        w = 1.0 / (np.linalg.norm(self.V[i] - P[:, None], axis=2) + 1e-3)
        w /= w.sum(1, keepdims=True)
        q = (self.V[i] * w[..., None]).sum(1)
        n = (self.vn[i] * w[..., None]).sum(1)
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        return P - ((P - q) * n).sum(1, keepdims=True) * n, n

    def signed_distance(self, P):
        q, n = self.project(P)
        return ((np.atleast_2d(P) - q) * n).sum(1), q, n


def tangent_frame(n):
    n = np.asarray(n, float) / np.linalg.norm(n)
    a1 = np.cross(n, [0, 0, 1.0])
    if np.linalg.norm(a1) < 1e-6:
        a1 = np.cross(n, [0, 1.0, 0])
    a1 /= np.linalg.norm(a1)
    return a1, np.cross(n, a1)


STICKER_R, FOAM_T, STUD_R, STUD_H = 13.0, 1.4, 2.6, 2.6   # Somnomedics SEN010C: 26 mm foam, snap stud


def sticker_mesh(skin, center, rim_mat, nr=10, nt=72, rim=1.6):
    """A 26 mm foam sticker lying on the skin (true size, 1.4 mm thick) with its snap stud.
    The outer 1.6 mm of the foam carries the lead's color, as in every figure."""
    c, n = skin.project(center)
    c, n = c[0], n[0]
    a1, a2 = tangent_frame(n)
    rs = np.r_[0, np.linspace(STUD_R, STICKER_R - rim, nr - 2), STICKER_R]
    th = np.linspace(0, 2 * math.pi, nt, endpoint=False)
    P = np.array([c + r * (math.cos(t) * a1 + math.sin(t) * a2) for r in rs for t in th])
    q, qn = skin.project(P)
    top = q + qn * FOAM_T
    bottom = q + qn * 0.15
    V = np.r_[top, bottom[-nt:]]
    F, M = [], []
    for i in range(len(rs) - 1):
        for k in range(nt):
            a, b = i * nt + k, i * nt + (k + 1) % nt
            F += [[a, b + nt, b], [a, a + nt, b + nt]]
            M += [rim_mat if i == len(rs) - 2 else "foam"] * 2
    o, s = (len(rs) - 1) * nt, len(rs) * nt         # edge wall from the top ring to the bottom ring
    for k in range(nt):
        a, b = o + k, o + (k + 1) % nt
        F += [[a, s + (k + 1) % nt, b], [a, s + k, s + (k + 1) % nt]]
        M += ["foam_edge"] * 2
    Vs, Fs = cylinder(c + n * (FOAM_T - 0.2), c + n * (FOAM_T + STUD_H), STUD_R, 24)
    Vc, Fc = cylinder(c + n * (FOAM_T + STUD_H - 0.6), c + n * (FOAM_T + STUD_H + 0.5), 1.5, 24)
    V2 = np.r_[V, Vs, Vc]
    F2 = np.r_[np.array(F), Fs + len(V), Fc + len(V) + len(Vs)]
    M2 = M + ["stud"] * len(Fs) + ["stud"] * len(Fc)
    return V2, F2, np.array(M2, object), c, n


# ---------------------------------------------------------------- shading
MATERIALS = {   # base color (sRGB), diffuse, specular, shininess, outline darkening
    "skin": ("#ddd5c5", 0.84, 0.035, 14, 0.62),
    "foam": ("#fdfdfb", 0.95, 0.0, 8, 0.70),
    "foam_edge": ("#e2e0da", 0.90, 0.0, 8, 0.60),
    "stud": ("#c9ccd6", 0.55, 0.85, 60, 0.55),
}


SECTION = {}      # material: color of its cut faces


def material(name, color=None, diffuse=0.85, spec=0.1, shine=20, line=0.6, emit=0.0):
    MATERIALS[name] = (color, diffuse, spec, shine, line, emit)


class Render:
    """One view of a scene. SVG mapping: X = ox + sx * k, Y = oy + sy * k, with (sx, sy) the
    camera's screen mm. The raster is computed at `ss` pixels per SVG px."""

    def __init__(self, scene, cam, k, ox, oy, ss=4, pad=6.0, bounds=None, light=(-0.55, 0.70, 0.45),
                 shadows=True, ao=True, cut=None, catcher=None, cut_only=None):
        V, F, M, N = scene.arrays()
        self.cam, self.k, self.ox, self.oy, self.ss = cam, k, ox, oy, ss
        single = cut is not None and len(cut) == 2 and np.isscalar(cut[1])
        planes = [] if cut is None else ([cut] if single else list(cut))
        planes = [(np.asarray(n, float), float(d)) for n, d in planes]
        cuttable = np.ones(len(F), bool) if cut_only is None else np.isin(M, list(cut_only))
        if planes:                                # cut planes: keep points with X . n >= d for every plane
            out = np.zeros(len(F), bool)
            for n, d in planes:
                out |= ((V[F] @ n) < d).all(axis=1)
            out &= cuttable
            F, M, N, cuttable = F[~out], M[~out], N[~out], cuttable[~out]
        P = cam.project(V)
        if bounds is None:
            used = np.unique(F)
            bounds = (P[used, 0].min(), P[used, 1].min(), P[used, 0].max(), P[used, 1].max())
        self.x0, self.y0 = bounds[0] - pad, bounds[1] - pad
        self.W = int((bounds[2] - bounds[0] + 2 * pad) * k * ss) + 1
        self.H = int((bounds[3] - bounds[1] + 2 * pad) * k * ss) + 1
        px = (P[:, 0] - self.x0) * k * ss
        py = (P[:, 1] - self.y0) * k * ss
        self.zbuf, self.fid, b0, b1 = rasterize(px, py, P[:, 2], F, self.W, self.H)
        mask = self.fid >= 0
        f = np.maximum(self.fid, 0)
        w = np.stack([b0, b1, 1 - b0 - b1], -1)
        X = (V[F[f]] * w[..., None]).sum(2)
        cut_px = cuttable[f]
        for n, d in planes:
            mask &= ((X @ n) >= d) | ~cut_px
        Nn = (N[f] * w[..., None]).sum(2)
        Nn /= np.maximum(np.linalg.norm(Nn, axis=-1, keepdims=True), 1e-12)
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        self.back = mask & ((fn[f] @ (-cam.d)) < 0)          # looking at the inside of a cut shell
        self.mask, self.X, self.N, self.mat = mask, X, Nn, M[f]
        self.zbuf = np.where(mask, self.zbuf, -np.inf)
        # light in camera terms: from the upper left, in front of the subject
        Lw = light[0] * cam.r + light[1] * cam.u + light[2] * (-cam.d)
        self.L = Lw / np.linalg.norm(Lw)
        self.shadow = np.ones(mask.shape)
        if shadows:
            self.shadow = self._shadows(V, F, cut)
        self.occl = self._ssao() if ao else np.ones(mask.shape)
        self.img = self._shade()
        if catcher is not None and shadows:
            a = self._catcher(catcher)
            self.img[..., :3] = np.where(a[..., None] > 0, hex_rgb("#03041a") * 255, self.img[..., :3])
            self.img[..., 3] = np.where(self.mask, 255, a * 255)

    def move_to(self, X, Y):
        """Shift the view so its image's top left corner lands on SVG (X, Y)."""
        self.ox, self.oy = X - self.x0 * self.k, Y - self.y0 * self.k
        return self

    # mapping for vector overlays
    def to_svg(self, P):
        p = self.cam.project(P)
        return np.c_[self.ox + p[:, 0] * self.k, self.oy + p[:, 1] * self.k]

    def image_box(self):
        return self.ox + self.x0 * self.k, self.oy + self.y0 * self.k, self.W / self.ss, self.H / self.ss

    def visible(self, P, tol=1.5):
        p = self.cam.project(P)
        X = ((p[:, 0] - self.x0) * self.k * self.ss).astype(int)
        Y = ((p[:, 1] - self.y0) * self.k * self.ss).astype(int)
        ok = (X >= 0) & (X < self.W) & (Y >= 0) & (Y < self.H)
        vis = np.ones(len(p), bool)
        vis[ok] = p[ok, 2] >= self.zbuf[Y[ok], X[ok]] - tol
        return vis

    def _shadows(self, V, F, cut):
        lc = Camera(-self.L, up=(0, 0, 1) if abs(self.L[2]) < 0.95 else (0, 1, 0))
        P = lc.project(V[np.unique(F)])
        span = max(np.ptp(P[:, 0]), np.ptp(P[:, 1]))
        res = max(0.35, span / 2400)                          # mm per shadow map pixel
        x0, y0 = P[:, 0].min() - 2, P[:, 1].min() - 2
        Ws, Hs = int((P[:, 0].max() - x0 + 2) / res) + 1, int((P[:, 1].max() - y0 + 2) / res) + 1
        Pa = lc.project(V)
        zb, _, _, _ = rasterize((Pa[:, 0] - x0) / res, (Pa[:, 1] - y0) / res, Pa[:, 2], F, Ws, Hs)
        self._smap = (lc, zb, x0, y0, res, Ws, Hs)
        ndl = np.clip(np.abs(self.N.reshape(-1, 3) @ self.L), 0.15, 1)
        bias = 0.6 + 1.6 * np.sqrt(1 - ndl ** 2) / ndl          # slope scaled, against shadow acne
        return self._lit(self.X.reshape(-1, 3), bias).reshape(self.mask.shape)

    def _lit(self, X, bias):
        lc, zb, x0, y0, res, Ws, Hs = self._smap
        Q = lc.project(X)
        sx, sy = (Q[:, 0] - x0) / res, (Q[:, 1] - y0) / res
        inside = (sx >= 0) & (sx < Ws) & (sy >= 0) & (sy < Hs)
        lit = np.zeros(len(Q))
        offs = [(dx, dy) for dx in (-2, 0, 2) for dy in (-2, 0, 2)]
        for dx, dy in offs:                                 # percentage closer filtering: soft edges
            ix = np.clip((sx + dx).astype(int), 0, Ws - 1)
            iy = np.clip((sy + dy).astype(int), 0, Hs - 1)
            lit += Q[:, 2] >= zb[iy, ix] - bias
        lit /= len(offs)
        lit[~inside] = 1.0
        return lit

    def _catcher(self, h, strength=0.5):
        """Shadow on an invisible floor at height h: alpha for the empty pixels."""
        H, W = self.mask.shape
        xs = self.x0 + (np.arange(W) + 0.5) / (self.k * self.ss)
        ys = self.y0 + (np.arange(H) + 0.5) / (self.k * self.ss)
        SX, SY = np.meshgrid(xs, ys)
        base = SX[..., None] * self.cam.r - SY[..., None] * self.cam.u
        t = (h - base[..., 2]) / self.cam.d[2]
        Pw = base + t[..., None] * self.cam.d
        lit = self._lit(Pw.reshape(-1, 3), 0.8).reshape(H, W)
        return strength * (1 - lit) * (~self.mask)

    def _ssao(self):
        z = np.where(self.mask, self.zbuf, np.nan)
        occ = np.zeros(z.shape)
        cnt = np.zeros(z.shape)
        mm = self.k * self.ss                              # pixels per mm
        for rmm in (1.5, 4.0, 9.0):
            r = max(int(rmm * mm), 1)
            for a in np.linspace(0, 2 * math.pi, 8, endpoint=False):
                dx, dy = int(round(r * math.cos(a))), int(round(r * math.sin(a)))
                sh = np.roll(np.roll(z, dy, 0), dx, 1)
                dz = sh - z
                o = np.clip((dz - 0.2 * rmm) / (1.2 * rmm), 0, 1) * (dz < 3.5 * rmm)
                occ += np.nan_to_num(o)
                cnt += 1
        return 1 - 0.55 * np.clip(occ / cnt * 2.2, 0, 1)

    def _shade(self):
        H, W = self.mask.shape
        rgb = np.zeros((H, W, 3))
        names = np.unique(self.mat[self.mask])
        view = -self.cam.d
        Hv = (self.L + view) / np.linalg.norm(self.L + view)
        for nm in names:
            col, kd, ks, sh = MATERIALS[nm][:4]
            sel = self.mask & (self.mat == nm)
            Nn = self.N[sel]
            ndl = Nn @ self.L
            diff = np.clip((ndl + 0.15) / 1.15, 0, 1) * self.shadow[sel]
            sky = 0.5 + 0.5 * Nn[:, 2]                     # light from above, darker from below
            amb = (0.30 + 0.16 * sky) * self.occl[sel]
            spec = ks * np.clip(Nn @ Hv, 0, 1) ** sh * self.shadow[sel]
            base = hex_rgb(col)
            c = base * (amb + kd * diff)[:, None] + spec[:, None]
            emit = MATERIALS[nm][5] if len(MATERIALS[nm]) > 5 else 0.0   # keeps signal colors true
            rgb[sel] = c * (1 - emit) + base * emit
        for nm, col in SECTION.items():                    # inside of a cut shell: flat section color
            sel = self.back & (self.mat == nm)
            rgb[sel] = hex_rgb(col) * (0.75 + 0.25 * self.occl[sel])[:, None]
        rgb = np.clip(rgb, 0, 1)
        # contour lines where a surface passes in front of another, darker shade of the front surface
        z = np.where(self.mask, self.zbuf, -1e9)
        edge = np.zeros(self.mask.shape, bool)
        step = 4.0
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]:
            sh = np.roll(np.roll(z, dy, 0), dx, 1)
            edge |= self.mask & (sh < z - step) & (sh > -1e8)
        edge = edge | (np.roll(edge, 1, 0) & self.mask & (np.roll(z, 1, 0) > -1e8))
        dark = np.array([MATERIALS[m][4] for m in names])
        for nm, dk in zip(names, dark):
            sel = edge & (self.mat == nm)
            rgb[sel] *= dk
        img = np.zeros((H, W, 4))
        img[..., :3] = rgb * 255
        img[..., 3] = self.mask * 255
        return img

    def png(self, scale_down=2):
        from PIL import Image
        a = self.img[..., 3:4] / 255.0
        pm = np.concatenate([self.img[..., :3] * a, self.img[..., 3:4]], -1)
        im = Image.fromarray(np.uint8(np.clip(np.round(pm), 0, 255)), "RGBA")
        im = im.resize((im.width // scale_down, im.height // scale_down), Image.LANCZOS)
        arr = np.asarray(im).astype(float)
        al = arr[..., 3:4] / 255.0
        arr[..., :3] = np.where(al > 0, arr[..., :3] / np.maximum(al, 1e-6), 0)
        buf = io.BytesIO()
        Image.fromarray(np.uint8(np.clip(arr, 0, 255)), "RGBA").save(buf, "PNG", optimize=True)
        return buf.getvalue()


def disc_points(center, normal, radius, n=72):
    a1, a2 = tangent_frame(normal)
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.asarray(center) + radius * (np.outer(np.cos(t), a1) + np.outer(np.sin(t), a2))
