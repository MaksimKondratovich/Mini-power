#!/usr/bin/env python3
"""Stage 3 of the PCB flow: add the routed tracks and vias, the GND pour, silkscreen, then fill and save.

Run with KiCad's Python after pcb_place.py and pcb_route.py:
    "C:/Program Files/KiCad/9.0/bin/python.exe" tools/pcb_finish.py
"""
import json
import os

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(ROOT, "mini-power", "mini-power.kicad_pcb")
ROUTES = os.path.join(ROOT, "out", "pcb_routes.json")
OX, OY = 100.0, 50.0
BW, BH = 100.0, 100.0
MM = pcbnew.FromMM
V = lambda x, y: pcbnew.VECTOR2I(MM(OX + x), MM(OY + y))


def main():
    board = pcbnew.LoadBoard(PCB)
    routes = json.load(open(ROUTES))
    layer = {0: pcbnew.F_Cu, 1: pcbnew.B_Cu}

    for t in routes["tracks"]:
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(V(t["x0"], t["y0"]))
        tr.SetEnd(V(t["x1"], t["y1"]))
        tr.SetWidth(MM(0.15))
        tr.SetLayer(layer[t["layer"]])
        tr.SetNet(board.FindNet(t["net"]))
        board.Add(tr)
    for v in routes["vias"]:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(V(v["x"], v["y"]))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetDrill(MM(0.3))
        try:
            via.SetWidth(MM(0.5))
        except TypeError:
            via.SetWidth(pcbnew.F_Cu, MM(0.5))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(board.FindNet(v["net"]))
        board.Add(via)

    # ---- GND pour on the bottom layer (shared by both zones)
    z = pcbnew.ZONE(board)
    z.SetLayer(pcbnew.B_Cu)
    z.SetNet(board.FindNet("GND"))
    z.SetMinThickness(MM(0.15))
    z.SetLocalClearance(MM(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)   # through-hole header pins stay hand-solderable
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.4))
    ol = z.Outline()
    ol.NewOutline()
    for (x, y) in ((0.3, 0.3), (BW - 0.3, 0.3), (BW - 0.3, BH - 0.3), (0.3, BH - 0.3)):
        ol.Append(MM(OX + x), MM(OY + y))
    board.Add(z)

    # ---- silkscreen: zone outlines, divider and labels
    def sline(x0, y0, x1, y1, w=0.2):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(x0, y0))
        s.SetEnd(V(x1, y1))
        s.SetLayer(pcbnew.F_SilkS)
        s.SetWidth(MM(w))
        board.Add(s)

    def text(s, x, y, size=1.0, bold=False, layer=pcbnew.F_SilkS):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetPosition(V(x, y))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
        t.SetTextThickness(MM(0.2 if bold else 0.15))
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        board.Add(t)

    sline(50, 1.5, 50, BH - 1.5, 0.4)   # divider between the two sections
    text("STANDALONE", 3.0, 2.2, 1.6, True)
    text("+3.3 V in (J1)", 3.0, 4.2, 0.9)
    text("CONTROLLER-DRIVEN", 52.5, 2.2, 1.6, True)
    text("A", 2.5, 22.0, 1.4, True)
    text("B", 2.5, 48.0, 1.4, True)
    text("C", 2.5, 60.0, 1.4, True)
    text("D", 52.0, 23.0, 1.4, True)
    text("E-A", 52.0, 33.0, 1.4, True)
    text("E-B", 52.0, 60.0, 1.4, True)
    text("+3.3 V in J1, out J2", 3.0, 98.0, 0.8)
    text("+2.75 V in J3, STM32 J5, out J4", 52.5, 98.0, 0.8)

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    board.Save(PCB)
    print("finished:", len(routes["tracks"]), "tracks,", len(routes["vias"]), "vias, zone filled")


if __name__ == "__main__":
    main()
