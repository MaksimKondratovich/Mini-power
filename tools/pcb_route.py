#!/usr/bin/env python3
"""Stage 2 of the PCB flow: a small grid router (A*, two layers, vias).

Run with KiCad's Python (it has numpy):
    "C:/Program Files/KiCad/9.0/bin/python.exe" tools/pcb_route.py
Reads out/pcb_geom.json, writes out/pcb_routes.json.

Rules (match pcb_place.py): clearance 0.10 mm, track 0.15 mm, via 0.5/0.3 mm.
GND is not routed on the top layer: every SMD GND pad gets a short stub to a via, and the bottom
layer is a GND pour (added in stage 3). Through-hole GND pads connect to the pour directly.
"""
import heapq
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOM = os.path.join(ROOT, "out", "pcb_geom.json")
OUT = os.path.join(ROOT, "out", "pcb_routes.json")

G = 0.05  # grid pitch (mm)
TRACK_W = 0.15
VIA_D = 0.5
# margins (mm): distance from a foreign object's edge/centre to the centre of the new object
M_PAD_TRK = 0.20      # track centre to pad edge
M_TRK_TRK = 0.30      # track centre to track centre
M_VIA_TRK = 0.45      # track centre to via centre
M_EDGE_TRK = 0.40
M_VIA_PAD = 0.40      # via centre to pad edge
M_VIA_TRK2 = 0.45     # via centre to track centre
M_VIA_VIA = 0.60
M_EDGE_VIA = 0.60
STEP = (10, 18)       # cost per cell on top / bottom
VIA_COST = 500
TURN = 8
GND = "GND"


class Grid:
    def __init__(self, w, h):
        self.nx = int(round(w / G)) + 1
        self.ny = int(round(h / G)) + 1
        self.trk = [np.zeros((self.ny, self.nx), np.int16) for _ in range(2)]  # owner map for track centres
        self.via = np.zeros((self.ny, self.nx), np.int16)                       # owner map for via centres (both layers)

    def rng(self, x0, y0, x1, y1, m):
        ix0 = max(0, int(math.ceil((x0 - m) / G - 1e-6)))
        ix1 = min(self.nx - 1, int(math.floor((x1 + m) / G + 1e-6)))
        iy0 = max(0, int(math.ceil((y0 - m) / G - 1e-6)))
        iy1 = min(self.ny - 1, int(math.floor((y1 + m) / G + 1e-6)))
        return ix0, ix1, iy0, iy1

    @staticmethod
    def paint(arr, ix0, ix1, iy0, iy1, net):
        if ix1 < ix0 or iy1 < iy0:
            return
        sub = arr[iy0:iy1 + 1, ix0:ix1 + 1]
        new = np.where(sub == 0, net, np.where((sub == net) | (sub == -1), sub, -1)).astype(np.int16)
        arr[iy0:iy1 + 1, ix0:ix1 + 1] = new

    def paint_box(self, layers, x0, y0, x1, y1, m_trk, m_via, net):
        ix0, ix1, iy0, iy1 = self.rng(x0, y0, x1, y1, m_trk)
        for l in layers:
            self.paint(self.trk[l], ix0, ix1, iy0, iy1, net)
        if m_via is not None:
            vx0, vx1, vy0, vy1 = self.rng(x0, y0, x1, y1, m_via)
            self.paint(self.via, vx0, vx1, vy0, vy1, net)

    def force_pad(self, layers, p, net):
        for (iy, ix) in self.pad_cells(p):
            for l in layers:
                self.trk[l][iy, ix] = net
        # via centres stay blocked inside pads (no via-in-pad), whatever the net
        vx0, vx1, vy0, vy1 = self.rng(p["x0"], p["y0"], p["x1"], p["y1"], 0.0)
        self.via[vy0:vy1 + 1, vx0:vx1 + 1] = -1

    def pad_cells(self, p, shrink=0.0):
        """Grid cells whose centre lies inside the pad copper (rectangle or circle), shrunk by `shrink`."""
        x0, y0, x1, y1 = p["x0"] + shrink, p["y0"] + shrink, p["x1"] - shrink, p["y1"] - shrink
        ix0, ix1, iy0, iy1 = self.rng(x0, y0, x1, y1, 0.0)
        out = []
        cx, cy, r = p["cx"], p["cy"], (p["x1"] - p["x0"]) / 2 - shrink
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                if p.get("round") and (ix * G - cx) ** 2 + (iy * G - cy) ** 2 > r * r:
                    continue
                out.append((iy, ix))
        return out


def main():
    geom = json.load(open(GEOM))
    W, H = geom["size"]
    grid = Grid(W, H)
    nets = sorted({p["net"] for p in geom["pads"] if p["net"]})
    nid = {n: i + 1 for i, n in enumerate(nets)}
    pads_by_net = {}
    for p in geom["pads"]:
        if p["net"]:
            pads_by_net.setdefault(p["net"], []).append(p)

    # ---- static obstacles: board edge, pads
    e = 1.0
    for l in (0, 1):
        t = grid.trk[l]
        for (sl) in ((slice(0, int(M_EDGE_TRK / G)), slice(None)), (slice(None), slice(0, int(M_EDGE_TRK / G))),
                     (slice(grid.ny - int(M_EDGE_TRK / G) - 1, None), slice(None)), (slice(None), slice(grid.nx - int(M_EDGE_TRK / G) - 1, None))):
            t[sl] = -1
    for sl in ((slice(0, int(M_EDGE_VIA / G)), slice(None)), (slice(None), slice(0, int(M_EDGE_VIA / G))),
               (slice(grid.ny - int(M_EDGE_VIA / G) - 1, None), slice(None)), (slice(None), slice(grid.nx - int(M_EDGE_VIA / G) - 1, None))):
        grid.via[sl] = -1

    for p in geom["pads"]:
        net = nid.get(p["net"], -1)  # pads without a net are plain obstacles
        layers = (0, 1) if p["thru"] else (0,)
        grid.paint_box(layers, p["x0"], p["y0"], p["x1"], p["y1"], M_PAD_TRK, M_VIA_PAD, net)
    for p in geom["pads"]:
        net = nid.get(p["net"], -1)
        layers = (0, 1) if p["thru"] else (0,)
        grid.force_pad(layers, p, net)

    nx, ny = grid.nx, grid.ny
    tracks, vias = [], []
    net_cells = {n: [] for n in nets}  # routed copper cells per net: (layer, iy, ix)

    def node(l, iy, ix):
        return (l * ny + iy) * nx + ix

    def unnode(v):
        ix = v % nx
        v //= nx
        return v // ny, v % ny, ix

    def pad_nodes(p):
        ls = (0, 1) if p["thru"] else (0,)
        cells = grid.pad_cells(p, shrink=0.03)
        if not cells:
            cells = grid.pad_cells(p)
        return [node(l, iy, ix) for l in ls for (iy, ix) in cells]

    def search(net_id, sources, goal_fn, goal_bytes, hx, hy, gnd_mode=False, limit=3_000_000):
        passb = [((grid.trk[l] == 0) | (grid.trk[l] == net_id)) for l in (0, 1)]
        viaok = ((grid.via == 0) | (grid.via == net_id)) & passb[0] & passb[1]
        pb = [passb[0].tobytes(), passb[1].tobytes()]
        vb = viaok.tobytes()
        best = {}
        heap = []
        for s in sources:
            key = s * 5 + 4
            best[key] = 0
            heapq.heappush(heap, (0, 0, key))
        parent = {}
        n_exp = 0
        found = None
        while heap:
            f, gcost, key = heapq.heappop(heap)
            if best.get(key, 1 << 60) < gcost:
                continue
            v, d = divmod(key, 5)
            l, iy, ix = unnode(v)
            if goal_bytes[v] and (not gnd_mode or l == 1):
                found = key
                break
            n_exp += 1
            if n_exp > limit:
                break
            # same-layer moves
            for nd, (dx, dy) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
                jx, jy = ix + dx, iy + dy
                if jx < 0 or jy < 0 or jx >= nx or jy >= ny:
                    continue
                if not pb[l][jy * nx + jx]:
                    continue
                c = gcost + STEP[l] + (TURN if (d != 4 and d != nd) else 0)
                v2 = node(l, jy, jx)
                k2 = v2 * 5 + nd
                if c < best.get(k2, 1 << 60):
                    best[k2] = c
                    parent[k2] = key
                    h = (abs(jx - hx) + abs(jy - hy)) * STEP[0] if not gnd_mode else 0
                    heapq.heappush(heap, (c + h, c, k2))
            # via move
            if vb[iy * nx + ix]:
                l2 = 1 - l
                if pb[l2][iy * nx + ix]:
                    c = gcost + VIA_COST
                    v2 = node(l2, iy, ix)
                    k2 = v2 * 5 + 4
                    if c < best.get(k2, 1 << 60):
                        best[k2] = c
                        parent[k2] = key
                        h = (abs(ix - hx) + abs(iy - hy)) * STEP[0] if not gnd_mode else 0
                        heapq.heappush(heap, (c + h, c, k2))
        if found is None:
            return None
        path = []
        k = found
        while True:
            path.append(k // 5)
            if k not in parent:
                break
            k = parent[k]
        path.reverse()
        return path

    def commit(net, path):
        """Record the path as tracks/vias and paint it into the obstacle maps."""
        nid_ = nid[net]
        pts = [unnode(v) for v in path]
        for a, b in zip(pts, pts[1:]):
            if a[0] != b[0]:
                vias.append({"net": net, "x": a[2] * G, "y": a[1] * G})
                vx, vy = a[2] * G, a[1] * G
                grid.paint_box((0, 1), vx, vy, vx, vy, M_VIA_TRK, M_VIA_VIA, nid_)
                vx0, vx1, vy0, vy1 = grid.rng(vx, vy, vx, vy, M_VIA_VIA)
                grid.via[vy0:vy1 + 1, vx0:vx1 + 1] = -1   # no second via within hole-to-hole distance, even on the same net
                continue
            tracks.append({"net": net, "layer": a[0], "x0": a[2] * G, "y0": a[1] * G, "x1": b[2] * G, "y1": b[1] * G})
        for l, iy, ix in pts:
            net_cells[net].append((l, iy, ix))
            x, y = ix * G, iy * G
            grid.paint_box((l,), x, y, x, y, M_TRK_TRK, M_VIA_TRK2, nid_)

    def merge_tracks():
        out = []
        for t in tracks:
            if out:
                u = out[-1]
                if (u["net"] == t["net"] and u["layer"] == t["layer"] and abs(u["x1"] - t["x0"]) < 1e-9 and abs(u["y1"] - t["y0"]) < 1e-9):
                    dx1, dy1 = u["x1"] - u["x0"], u["y1"] - u["y0"]
                    dx2, dy2 = t["x1"] - t["x0"], t["y1"] - t["y0"]
                    if abs(dx1 * dy2 - dy1 * dx2) < 1e-9 and (dx1 * dx2 + dy1 * dy2) > 0:
                        u["x1"], u["y1"] = t["x1"], t["y1"]
                        continue
            out.append(dict(t))
        return out

    t0 = time.time()
    failures = []

    # ---- 1. GND: every SMD pad gets a stub to a via (through-hole pads touch the pour)
    gnd_id = nid.get(GND)
    bottom_goal = _all_bottom(grid)
    gnd_pads = pads_by_net.get(GND, [])
    smd_gnd = [p for p in gnd_pads if not p["thru"]]
    for p in sorted(smd_gnd, key=lambda q: (q["ref"], q["pin"])):
        src = pad_nodes(p)
        path = search(gnd_id, src, None, bottom_goal, 0, 0, gnd_mode=True, limit=400000)
        if path is None:
            failures.append(("GND", p["ref"], p["pin"]))
            continue
        commit(GND, path)

    # ---- 2. signal nets: power buses first, then short nets before long ones
    def span(n):
        ps = pads_by_net[n]
        xs = [q["cx"] for q in ps]
        ys = [q["cy"] for q in ps]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    order = [n for n in nets if n != GND]
    big = [n for n in order if len(pads_by_net[n]) >= 6]
    rest = sorted([n for n in order if n not in big], key=span)
    order = sorted(big, key=span, reverse=True) + rest
    for n in order:
        ps = pads_by_net[n]
        pending = list(ps)
        first = pending.pop(0)
        tree_src = pad_nodes(first)
        tree_nodes = set(tree_src)
        for _ in range(len(ps) - 1):
            # nearest remaining pad to the tree (by centre distance to the pads already connected)
            conn = [first] + [q for q in ps if q not in pending and q is not first]
            def dist(q):
                return min(abs(q["cx"] - c["cx"]) + abs(q["cy"] - c["cy"]) for c in conn)
            pending.sort(key=dist)
            tgt = pending.pop(0)
            goal_nodes = pad_nodes(tgt)
            gb = bytearray(grid.nx * grid.ny * 2)
            for v in goal_nodes:
                gb[v] = 1
            hx = int(round(tgt["cx"] / G))
            hy = int(round(tgt["cy"] / G))
            sources = list(tree_nodes)
            path = search(nid[n], sources, None, bytes(gb), hx, hy)
            if path is None:
                failures.append((n, tgt["ref"], tgt["pin"]))
                continue
            commit(n, path)
            tree_nodes.update(path)
            tree_nodes.update(goal_nodes)
        print("routed %-12s (%d pads)  %.0fs" % (n, len(ps), time.time() - t0), flush=True)

    out = {"tracks": merge_tracks(), "vias": vias, "failures": failures}
    json.dump(out, open(OUT, "w"))
    print("tracks %d, vias %d, failures %d" % (len(out["tracks"]), len(vias), len(failures)))
    for f in failures:
        print("  FAILED:", f)


def _all_bottom(grid):
    b = bytearray(grid.nx * grid.ny * 2)
    for i in range(grid.nx * grid.ny, grid.nx * grid.ny * 2):
        b[i] = 1
    return bytes(b)


if __name__ == "__main__":
    main()
