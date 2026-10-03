#!/usr/bin/env python3
"""Stage 1 of the PCB flow: create the board, place the footprints, assign nets.

Run with KiCad's Python:
    "C:/Program Files/KiCad/9.0/bin/python.exe" tools/pcb_place.py
Needs out/net.net (kicad-cli sch export netlist --format kicadsexpr).
Writes mini-power/mini-power.kicad_pcb (unrouted) and out/pcb_geom.json for the router.

Layout: two clearly separated zones on one 100 x 100 mm board
  STANDALONE  (x   2 ..  49 mm): +3.3 V input, TPS6284x / LT8330 rails
  CONTROLLER  (x  51 .. 98 mm): +2.75 V input, STM32 header, pin-driven rails
They share only the GND plane.
"""
import json
import os
import re
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "mini-power", "lib", "mp.pretty")
NETLIST = os.path.join(ROOT, "out", "net.net")
PCB = os.path.join(ROOT, "mini-power", "mini-power.kicad_pcb")
GEOM = os.path.join(ROOT, "out", "pcb_geom.json")

OX, OY = 100.0, 50.0  # board origin on the KiCad page (mm)
BW, BH = 100.0, 100.0
MM = pcbnew.FromMM


# ---------------------------------------------------------------- netlist
def tokenize(s):
    return re.findall(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()"]+', s)


def parse(s):
    toks = tokenize(s)
    pos = 0

    def rec():
        nonlocal pos
        out = []
        while pos < len(toks):
            t = toks[pos]
            pos += 1
            if t == "(":
                out.append(rec())
            elif t == ")":
                return out
            else:
                out.append(t[1:-1] if t.startswith('"') else t)
        return out

    return rec()[0]


def find(node, key):
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def read_netlist():
    tree = parse(open(NETLIST, encoding="utf-8").read())
    comps = {}
    for c in find(tree, "components")[1:]:
        ref = find(c, "ref")[1]
        comps[ref] = {
            "value": find(c, "value")[1],
            "footprint": find(c, "footprint")[1],
            "uuid": find(c, "tstamps")[1] if find(c, "tstamps") else "",
        }
    nets = {}
    for n in find(tree, "nets")[1:]:
        name = find(n, "name")[1]
        nodes = []
        for nd in n:
            if isinstance(nd, list) and nd and nd[0] == "node":
                nodes.append((find(nd, "ref")[1], find(nd, "pin")[1]))
        nets[name] = nodes
    return comps, nets


# ---------------------------------------------------------------- placement (board-local mm, y down)
# (x, y, rotation in degrees)
PLACE = {
    # ---------------- STANDALONE zone
    # block A: +2.8 V (U1)
    "U1": (14, 14, 0), "C1": (10, 18.5, 90), "L1": (20, 9, 0), "C2": (25, 14, 90), "R1": (18.5, 17, 90), "JP1": (32, 9, 0),
    # block B: +1.4 V (U2)
    "U2": (14, 40, 0), "C3": (10, 44.5, 90), "L2": (20, 35, 0), "C4": (25, 40, 90), "R2": (18.5, 43, 90), "JP2": (32, 35, 0),
    # block C: -2.8 V (U3)
    "U3": (14, 78, 0), "C5": (6, 70, 90), "L3": (17, 68, 0), "C6": (24, 68, 0), "D1": (29.5, 72, 90), "L4": (35, 68, 0),
    "C7": (41, 72, 90), "R3": (27, 83, 0), "R4": (32.5, 83, 0), "C8": (38, 83, 0), "C9": (7, 79, 90), "JP3": (43, 62, 0),
    # connectors
    "J1": (8, 93, 0), "J2": (45, 22, 90),
    # ---------------- CONTROLLER zone
    "J3": (57, 8, 0), "J5": (73, 8, 0), "J4": (91, 8, 0),
    # block D: +1.375 V buck
    "L5": (66, 15, 0), "C10": (72, 19, 90), "JP4": (82, 14, 0),
    # block E-A: charge pump
    "C11": (62, 35, 0), "D2": (68, 40, 90), "D3": (72, 35, 0), "C12": (78, 38, 90), "JP5": (86, 34, 0),
    # block E-B: P-FET stage and sense amplifier
    "R5": (58, 62, 90), "Q1": (64, 66, 180), "L6": (70, 73, 90), "D4": (76, 66, 0), "C13": (81, 70, 90),
    "R6": (76, 80, 0), "R7": (85, 87, 0), "C15": (85, 93, 0), "U4": (85, 80, 0), "C14": (91, 72, 90), "JP6": (88, 62, 0),
}
ZONE_OF = lambda ref: "controller" if PLACE.get(ref, (0,))[0] > 50 else "standalone"


def tp_candidates(cx, cy, step=1.0, rmax=14):
    pts = []
    r = 0.0
    while r <= rmax:
        n = max(1, int(8 * r / step)) if r else 1
        import math

        for k in range(n):
            a = 2 * math.pi * k / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        r += step
    return pts


def main():
    comps, nets = read_netlist()
    board = pcbnew.BOARD()

    # ---- design rules (JLCPCB-friendly, 2 layers)
    ds = board.GetDesignSettings()
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(MM(0.1))
    nc.SetTrackWidth(MM(0.15))
    nc.SetViaDiameter(MM(0.5))
    nc.SetViaDrill(MM(0.3))
    ds.m_MinClearance = MM(0.1)
    ds.m_TrackMinWidth = MM(0.15)
    ds.m_ViasMinSize = MM(0.5)
    ds.m_MinThroughDrill = MM(0.3)
    ds.m_CopperEdgeClearance = MM(0.3)
    board.SetCopperLayerCount(2)

    # ---- nets
    netinfo = {}
    for name in nets:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netinfo[name] = ni
    pin_net = {}
    for name, nodes in nets.items():
        for ref, pin in nodes:
            pin_net[(ref, pin)] = name

    # ---- footprints
    fps = {}
    tp_refs = []
    for ref, c in sorted(comps.items()):
        libname = c["footprint"].split(":")[1]
        fp = pcbnew.FootprintLoad(LIB, libname)
        if fp is None:
            sys.exit("cannot load footprint " + libname)
        fp.SetFPID(pcbnew.LIB_ID("mp", libname))   # library nickname must match the symbol's footprint field
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        if c["uuid"]:
            fp.SetPath(pcbnew.KIID_PATH("/" + c["uuid"]))
        if ref.startswith("TP"):
            fp.Reference().SetLayer(pcbnew.F_Fab)   # 0.5 mm pads have no room for silkscreen names
        if ref in PLACE:
            x, y, rot = PLACE[ref]
            fp.SetPosition(pcbnew.VECTOR2I(MM(OX + x), MM(OY + y)))
            fp.SetOrientationDegrees(rot)
        elif ref.startswith("TP"):
            tp_refs.append(ref)
        else:
            sys.exit("no placement for " + ref)
        # EasyEDA pin-1 dots sit on top of the pads; drop the silkscreen circles (pin 1 stays on the fab layer)
        if ref in ("R7", "C15"):
            x, y, _ = PLACE[ref]
            fp.Reference().SetPosition(pcbnew.VECTOR2I(MM(OX + x + 3.0), MM(OY + y)))
        for pad in fp.Pads():
            n = pin_net.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(netinfo[n])
        board.Add(fp)
        fps[ref] = fp

    # ---- test points: next to the pads of their net, inside the same zone, clear of everything
    def bbox_mm(fp):
        b = fp.GetBoundingBox(False)
        return (pcbnew.ToMM(b.GetLeft()) - OX, pcbnew.ToMM(b.GetTop()) - OY, pcbnew.ToMM(b.GetRight()) - OX, pcbnew.ToMM(b.GetBottom()) - OY)

    placed_boxes = [(r, bbox_mm(f)) for r, f in fps.items() if r in PLACE]
    tp_boxes = []

    def free(x, y, zone):
        if zone == "standalone" and not (3 < x < 48):
            return False
        if zone == "controller" and not (52 < x < 97):
            return False
        if not (3 < y < 97):
            return False
        m = 1.2  # keep TPs 1.2 mm away from every other part and from other TPs
        for r, (x0, y0, x1, y1) in placed_boxes:
            if x0 - m < x < x1 + m and y0 - m < y < y1 + m:
                return False
        for (tx, ty) in tp_boxes:
            if (tx - x) ** 2 + (ty - y) ** 2 < 2.2 ** 2:
                return False
        return True

    for ref in sorted(tp_refs, key=lambda r: int(r[2:])):
        net = pin_net[(ref, "1")]
        pads = [(r, p) for (r, p), n in pin_net.items() if n == net and not r.startswith("TP")]
        xs, ys = [], []
        for r, p in pads:
            b = fps[r].FindPadByNumber(p).GetPosition()
            xs.append(pcbnew.ToMM(b.x) - OX)
            ys.append(pcbnew.ToMM(b.y) - OY)
        zone = ZONE_OF(pads[0][0])
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        # start from the pad closest to the centroid so the TP sits next to the net's own copper
        best = min(range(len(xs)), key=lambda i: (xs[i] - cx) ** 2 + (ys[i] - cy) ** 2)
        for (x, y) in tp_candidates(xs[best], ys[best]):
            if free(x, y, zone):
                fps[ref].SetPosition(pcbnew.VECTOR2I(MM(OX + x), MM(OY + y)))
                tp_boxes.append((x, y))
                break
        else:
            sys.exit("no room for " + ref)

    # ---- board outline
    def line(x0, y0, x1, y1, layer, w=0.1):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(MM(OX + x0), MM(OY + y0)))
        s.SetEnd(pcbnew.VECTOR2I(MM(OX + x1), MM(OY + y1)))
        s.SetLayer(layer)
        s.SetWidth(MM(w))
        board.Add(s)

    for (a, b, c, d) in ((0, 0, BW, 0), (BW, 0, BW, BH), (BW, BH, 0, BH), (0, BH, 0, 0)):
        line(a, b, c, d, pcbnew.Edge_Cuts)

    # ---- geometry for the router
    geom = {"origin": [OX, OY], "size": [BW, BH], "pads": [], "keepout": []}
    for ref, fp in fps.items():
        for pad in fp.Pads():
            b = pad.GetBoundingBox()
            geom["pads"].append({
                "ref": ref,
                "pin": pad.GetNumber(),
                "net": pad.GetNetname(),
                "x0": pcbnew.ToMM(b.GetLeft()) - OX, "y0": pcbnew.ToMM(b.GetTop()) - OY,
                "x1": pcbnew.ToMM(b.GetRight()) - OX, "y1": pcbnew.ToMM(b.GetBottom()) - OY,
                "cx": pcbnew.ToMM(pad.GetPosition().x) - OX, "cy": pcbnew.ToMM(pad.GetPosition().y) - OY,
                "thru": pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH),
                "round": pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE,
            })
    os.makedirs(os.path.dirname(GEOM), exist_ok=True)
    json.dump(geom, open(GEOM, "w"))
    board.Save(PCB)
    # the project file overrides the board's own rules: keep it in step (0.10 mm / 0.15 mm / 0.5 mm via)
    pro = PCB.replace(".kicad_pcb", ".kicad_pro")
    d = json.load(open(pro))
    for c in d["net_settings"]["classes"]:
        if c["name"] == "Default":
            c.update({"clearance": 0.1, "track_width": 0.15, "via_diameter": 0.5, "via_drill": 0.3})
    r = d["board"]["design_settings"]["rules"]
    r.update({"min_clearance": 0.1, "min_track_width": 0.15, "min_copper_edge_clearance": 0.3})
    json.dump(d, open(pro, "w"), indent=2)
    print("placed %d footprints (%d test points), wrote %s" % (len(fps), len(tp_refs), PCB))


if __name__ == "__main__":
    main()
