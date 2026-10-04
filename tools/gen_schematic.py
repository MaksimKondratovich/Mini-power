#!/usr/bin/env python3
"""Generate mini-power/mini-power.kicad_sch.

The schematic is generated so that part values, nets and layout are reproducible.
Run:  python tools/gen_schematic.py
Then: kicad-cli sch erc ...
Close the project in KiCad first, or KiCad may overwrite the result.
"""
import math
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "mini-power"
LIBS = {"mp": ROOT / "lib" / "mp.kicad_sym", "mpx": ROOT / "lib" / "mpx.kicad_sym"}
OUT = ROOT / "mini-power.kicad_sch"
SHEET_UUID = "1d7b6a88-85a7-4876-8779-6fe68a207d3b"


def uid():
    return str(uuid.uuid4())


def fmt(v):
    s = ("%.3f" % v).rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


# ---------------------------------------------------------------- s-expr utils
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


def find_symbols(libname):
    text = LIBS[libname].read_text(encoding="utf-8")
    tree = parse(text)
    syms = {}
    for item in tree:
        if isinstance(item, list) and item and item[0] == "symbol":
            syms[item[1]] = item
    return text, syms


def raw_symbol_block(text, name):
    """Return the raw text of the top-level (symbol "name" ...) from the library."""
    i = text.index('(symbol "%s"' % name)
    depth = 0
    j = i
    in_str = False
    while True:
        c = text[j]
        if c == '"' and text[j - 1] != "\\":
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return text[i : j + 1]
        j += 1


def symbol_pins(sym):
    """pin number -> (name, x, y, angle) in symbol coordinates."""
    pins = {}

    def walk(n):
        if isinstance(n, list):
            if n and n[0] == "pin" and len(n) > 3:
                at = next(c for c in n if isinstance(c, list) and c[0] == "at")
                name = next(c for c in n if isinstance(c, list) and c[0] == "name")[1]
                num = next(c for c in n if isinstance(c, list) and c[0] == "number")[1]
                pins[num] = (name, float(at[1]), float(at[2]), float(at[3]))
            else:
                for c in n:
                    walk(c)

    walk(sym)
    return pins


def sym_prop(sym, key):
    for c in sym:
        if isinstance(c, list) and c[0] == "property" and c[1] == key:
            return c[2]
    return ""


# ---------------------------------------------------------------- schematic model
class Sch:
    def __init__(self):
        self.libsyms = {}
        self.items = []
        self.symdata = {}
        self._cache = {}

    def lib(self, lib, name):
        key = "%s:%s" % (lib, name)
        if key not in self.symdata:
            if lib not in self._cache:
                self._cache[lib] = find_symbols(lib)
            text, syms = self._cache[lib]
            raw = raw_symbol_block(text, name)
            raw = raw.replace('(symbol "%s"' % name, '(symbol "%s"' % key, 1)
            self.libsyms[key] = raw
            self.symdata[key] = syms[name]
        return key

    def pin_xy(self, key, X, Y, rot, num, mirror=False):
        _, x, y, _ = symbol_pins(self.symdata[key])[num]
        if mirror:
            x = -x
        th = math.radians(rot)
        xr = x * math.cos(th) - y * math.sin(th)
        yr = x * math.sin(th) + y * math.cos(th)
        return (round(X + xr, 3), round(Y - yr, 3))

    def place(self, lib, name, ref, value, X, Y, rot=0, ref_at=None, val_at=None, hide_val=False, mirror=False):
        key = self.lib(lib, name)
        sym = self.symdata[key]
        fp = sym_prop(sym, "Footprint")
        ds = sym_prop(sym, "Datasheet")
        extra = {k: sym_prop(sym, k) for k in ("Manufacturer", "MPN", "LCSC Part")}
        ra = ref_at or (X, Y - 3.81)
        va = val_at or (X, Y + 3.81)
        eff = "(effects (font (size 1.27 1.27)))"
        effh = "(effects (font (size 1.27 1.27)) (hide yes))"
        hidden = ref.startswith("#")
        L = []
        L.append("\t(symbol")
        L.append('\t\t(lib_id "%s")' % key)
        L.append("\t\t(at %s %s %d)" % (fmt(X), fmt(Y), rot))
        if mirror:
            L.append("\t\t(mirror y)")
        L.append("\t\t(unit 1)")
        L.append("\t\t(exclude_from_sim no)")
        L.append("\t\t(in_bom %s)" % ("no" if (hidden or ref.startswith("TP")) else "yes"))
        L.append("\t\t(on_board yes)")
        L.append("\t\t(dnp no)")
        L.append('\t\t(uuid "%s")' % uid())
        fa = 90 if rot in (90, 270) else 0
        L.append('\t\t(property "Reference" "%s" (at %s %s %d) %s)' % (ref, fmt(ra[0]), fmt(ra[1]), fa, effh if hidden else eff))
        L.append('\t\t(property "Value" "%s" (at %s %s %d) %s)' % (value, fmt(va[0]), fmt(va[1]), fa, effh if (hide_val or hidden) else eff))
        L.append('\t\t(property "Footprint" "%s" (at %s %s 0) %s)' % (fp, fmt(X), fmt(Y), effh))
        L.append('\t\t(property "Datasheet" "%s" (at %s %s 0) %s)' % (ds, fmt(X), fmt(Y), effh))
        for k, v in extra.items():
            if v:
                L.append('\t\t(property "%s" "%s" (at %s %s 0) %s)' % (k, v, fmt(X), fmt(Y), effh))
        for num in symbol_pins(sym):
            L.append('\t\t(pin "%s" (uuid "%s"))' % (num, uid()))
        L.append('\t\t(instances (project "mini-power" (path "/%s" (reference "%s") (unit 1))))' % (SHEET_UUID, ref))
        L.append("\t)")
        self.items.append("\n".join(L))
        return {num: self.pin_xy(key, X, Y, rot, num, mirror) for num in symbol_pins(sym)}

    def wire(self, *pts):
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            self.items.append(
                '\t(wire (pts (xy %s %s) (xy %s %s)) (stroke (width 0) (type default)) (uuid "%s"))'
                % (fmt(a[0]), fmt(a[1]), fmt(b[0]), fmt(b[1]), uid())
            )

    def junction(self, p):
        self.items.append(
            '\t(junction (at %s %s) (diameter 0) (color 0 0 0 0) (uuid "%s"))' % (fmt(p[0]), fmt(p[1]), uid())
        )

    def label(self, name, p, just="left"):
        j = "left bottom" if just == "left" else "right bottom"
        self.items.append(
            '\t(label "%s" (at %s %s 0) (effects (font (size 1.27 1.27)) (justify %s)) (uuid "%s"))'
            % (name, fmt(p[0]), fmt(p[1]), j, uid())
        )

    def text(self, s, p, size=1.27, bold=False):
        s = s.replace('"', "'").replace("\n", "\\n")
        self.items.append(
            '\t(text "%s" (exclude_from_sim no) (at %s %s 0) (effects (font (size %s %s)%s) (justify left top)) (uuid "%s"))'
            % (s, fmt(p[0]), fmt(p[1]), size, size, " bold" if bold else "", uid())
        )

    def stub_label(self, p, name, direction):
        """2.54 mm wire stub from pin point p to the left or right, with a net label at its end."""
        dx = -2.54 if direction == "left" else 2.54
        e = (round(p[0] + dx, 3), p[1])
        self.wire(p, e)
        self.label(name, e, just="right" if direction == "left" else "left")
        return e

    def write(self):
        body = "\n".join(self.items)
        libs = "\n".join("\t\t" + l for l in "\n".join(self.libsyms.values()).split("\n"))
        out = (
            '(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t(generator_version "9.0")\n'
            '\t(uuid "%s")\n\t(paper "A2")\n'
            '\t(title_block (title "Mini-power") (date "2026-10-03") (rev "A")\n'
            '\t\t(comment 1 "3.3 V in; +2.8 V, -2.8 V, +1.4 V out, 5 mA max each")\n'
            '\t\t(comment 2 "Design notes and calculations: docs/power-architecture.md"))\n'
            "\t(lib_symbols\n%s\n\t)\n%s\n"
            '\t(sheet_instances (path "/" (page "1")))\n\t(embedded_fonts no)\n)\n' % (SHEET_UUID, libs, body)
        )
        OUT.write_text(out, encoding="utf-8")


# ---------------------------------------------------------------- the design
s = Sch()
IC840 = "TPS62840DLCR"
IC841 = "TPS62841DLCR"
IND = "DFE201612E-2R2M=P2"
C47 = "CL05A475MP5NRNC"
C10 = "CGA0402X5R106M6R3GT"
R287 = "0402WGF2872TCE"
R523 = "0402WGF5232TCE"
HDR2 = "PZ254V-11-02P"
HDR4 = "PZ254V-11-04P_C2691448"
IC8330 = "LT8330ES6#TRMPBF"
DIODE = "PMEG6010CEJ,115"
C1U = "CL05A105KA5NQNC"
C4P7 = "0402CG4R7C500NT"
R1M = "0402WGF1004TCE"
R402K = "0402WGF4023TCE"

counters = {"C": 0, "R": 0, "L": 0, "U": 0, "D": 0, "PWR": 0, "TP": 0}


def nxt(p):
    counters[p] += 1
    return "%s%d" % (p, counters[p])


def gnd_symbol(p):
    counters["PWR"] += 1
    s.place("mpx", "GND", "#PWR%02d" % counters["PWR"], "GND", p[0], p[1])


def test_point(net, x, y, direction="up", ref_side="right"):
    """Test point hanging on an existing wire at (x, y).

    The TP pin sits 2.54 mm away from the wire (up or down) and is joined to it by a short wire
    with a junction, so the pad is physically on that net's wire. The caller must split the host wire
    at (x, y): KiCad does not connect the far end of a wire through a mid-wire T junction.
    """
    ref = nxt("TP")
    if direction == "up":
        pin = (x, round(y - 2.54, 3))
        rot = 0
    elif direction == "down":
        pin = (x, round(y + 2.54, 3))
        rot = 180
    else:  # "left": pad to the left of a vertical wire
        pin = (round(x - 2.54, 3), y)
        rot = 90
    if direction == "left":
        ref_at = (pin[0] - 2.0, pin[1] - 3.0)
    else:
        dx = 4.5 if ref_side == "right" else -4.5
        ref_at = (pin[0] + dx, pin[1] + (-1.27 if direction == "up" else 1.27))
    s.place("mpx", "TestPoint", ref, net, pin[0], pin[1], rot=rot, ref_at=ref_at,
            val_at=(pin[0], pin[1]), hide_val=True)
    s.wire((x, y), pin)
    s.junction((x, y))
    TP_NETS.append(net)


TP_NETS = []


def cap_v(name, value, p_top):
    """Vertical capacitor whose top pin is at p_top. Returns (ref, top pin, bottom pin)."""
    ref = nxt("C")
    X, Y = p_top[0], p_top[1] + 5.08
    pins = s.place("mp", name, ref, value, X, Y, rot=90, ref_at=(X + 8.89, Y - 1.27), val_at=(X + 8.89, Y + 1.27))
    top = min(pins.values(), key=lambda q: q[1])
    bot = max(pins.values(), key=lambda q: q[1])
    return ref, top, bot


def buck(tag, X, Y, ic, rset_part, rset_val, jp_ref, raw_net, out_net, title, notes, timing=""):
    u = nxt("U")
    pins = s.place("mp", ic, u, ic.replace("DLCR", "DLC"), X, Y, ref_at=(X, Y - 9.5), val_at=(X, Y + 8.5))
    s.text(title, (X - 30.48, Y - 30.48), size=2.0, bold=True)
    s.text(notes, (X - 30.48, Y - 25.4))
    if timing:
        s.text(timing, (X - 30.48, Y - 21.59))

    # --- control pins: short stubs with labels
    s.stub_label(pins["1"], "GND", "left")
    s.stub_label(pins["3"], "GND", "left")
    s.stub_label(pins["4"], "+3V3", "left")
    s.stub_label(pins["6"], "GND", "right")

    # --- input: VIN wire to the +3V3 node, input capacitor hangs below it
    vin = pins["2"]
    nvin = (X - 30.48, vin[1])
    s.wire(vin, nvin)
    s.label("+3V3", nvin)
    _, top, bot = cap_v(C47, "4.7uF/10V", (nvin[0], nvin[1] + 10.16))
    s.wire(nvin, top)
    gnd_symbol(bot)

    # --- switch node: SW pin -> inductor, with TP above the wire
    sw = pins["7"]
    ind_x = X + 38.1
    lref = nxt("L")
    lp = s.place("mp", IND, lref, "2.2uH", ind_x, sw[1], ref_at=(ind_x, sw[1] - 3.81), val_at=(ind_x, sw[1] + 3.81))
    s.wire(sw, (X + 27.94, sw[1]), lp["1"])
    s.label("SW_" + tag, (X + 15.24, sw[1]))
    test_point("SW_" + tag, X + 27.94, sw[1], "up", "left")

    # --- output node: inductor -> node, VOS feedback wire routed above, output cap below
    onode = (X + 53.34, sw[1])
    s.wire(lp["2"], onode)
    vos = pins["8"]
    vtop = vos[1] - 5.08
    s.wire(vos, (X + 13.97, vos[1]), (X + 13.97, vtop), (onode[0], vtop), onode)
    s.junction(onode)
    _, top2, bot2 = cap_v(C10, "10uF/6.3V", (onode[0], onode[1] + 7.62))
    s.wire(onode, top2)
    gnd_symbol(bot2)

    # --- VSET resistor: wire to the right, resistor hangs below, TP below the wire
    vs = pins["5"]
    rx = vs[0] + 15.24
    rref = nxt("R")
    rp = s.place("mp", rset_part, rref, rset_val, rx, vs[1] + 5.08, rot=90,
                 ref_at=(rx + 8.89, vs[1] + 3.81), val_at=(rx + 8.89, vs[1] + 6.35))
    rt = min(rp.values(), key=lambda q: q[1])
    rb = max(rp.values(), key=lambda q: q[1])
    s.wire(vs, (vs[0] + 10.16, vs[1]), rt)
    s.label("VSET_" + tag, (vs[0] + 2.54, vs[1]))
    test_point("VSET_" + tag, vs[0] + 10.16, vs[1], "down", "left")
    gnd_symbol(rb)

    # --- series header: pin 1 = converter side, pin 2 = measured output
    jx, jy = onode[0] + 38.1, onode[1] + 1.27
    jp = s.place("mp", HDR2, jp_ref, "Current jumper", jx, jy, ref_at=(jx, jy - 7.0), val_at=(jx, jy + 6.0))
    s.wire(onode, (onode[0] + 22.86, onode[1]), (jp["1"][0], onode[1]))
    s.label(raw_net, (onode[0] + 3.81, onode[1]))
    test_point(raw_net, onode[0] + 22.86, onode[1], "up", "right")
    e = (jp["2"][0] - 15.24, jp["2"][1])
    s.wire(jp["2"], (jp["2"][0] - 7.62, jp["2"][1]), e)
    s.label(out_net, e, just="right")
    test_point(out_net, jp["2"][0] - 7.62, jp["2"][1], "down", "left")


# Block A: +2.8 V
buck("A", 114.3, 63.5, IC840, R287, "28.7k 1%", "JP1", "+2V8_IC", "+2V8",
     "Block A: +2.8 V buck (U1 TPS62840, RSET 28.7k selects 2.8 V)",
     "3.3 V -> 2.8 V, 5 mA max. MODE = GND: auto PFM, 60 nA Iq. Output passes JP1 (jumper or ammeter).",
     "Switching: 1.8 MHz nominal (PWM), duty D = 2.8 / 3.3 = 0.848 (ton 471 ns). At 0.1 / 1 / 5 mA it runs in power-save (PFM) at about 3 / 34 / 168 kHz (estimate).")
# Block B: +1.4 V
buck("B", 114.3, 139.7, IC841, R523, "52.3k 1%", "JP2", "+1V4_IC", "+1V4",
     "Block B: +1.4 V buck (U2 TPS62841, RSET 52.3k selects 1.4 V)",
     "3.3 V -> 1.4 V, 5 mA max. MODE = GND: auto PFM, 60 nA Iq. Output passes JP2 (jumper or ammeter).",
     "Switching: 1.8 MHz nominal (PWM), duty D = 1.4 / 3.3 = 0.424 (ton 236 ns). At 0.1 / 1 / 5 mA it runs in power-save (PFM) at about 2 / 18 / 88 kHz (estimate).")

# Block C: -2.8 V inverting converter (LT8330, dual-inductor topology)
def passive_h(part, value, cx, cy, ref_prefix, ref_at=None, val_at=None):
    ref = nxt(ref_prefix)
    pins = s.place("mp", part, ref, value, cx, cy, ref_at=ref_at or (cx, cy - 3.81), val_at=val_at or (cx, cy + 3.81))
    left = min(pins.values(), key=lambda q: q[0])
    right = max(pins.values(), key=lambda q: q[0])
    return ref, left, right


def passive_v(part, value, cx, cy, ref_prefix):
    """Vertical passive centred at (cx, cy); returns (top pin, bottom pin)."""
    ref = nxt(ref_prefix)
    pins = s.place("mp", part, ref, value, cx, cy, rot=90, ref_at=(cx + 8.89, cy - 1.27), val_at=(cx + 8.89, cy + 1.27))
    top = min(pins.values(), key=lambda q: q[1])
    bot = max(pins.values(), key=lambda q: q[1])
    return top, bot


CX, CY = 114.3, 241.3
YR = CY - 25.4  # power row
NEG = "-2V8_IC"
s.text("Block C: -2.8 V inverting converter (U3 LT8330, dual-inductor topology)", (CX - 40.64, YR - 24.13), size=2.0, bold=True)
s.text("L3/L4, CDC and D1 form the inverting stage. The divider R3/R4 sets VOUT = -0.8 V x (1 + R3/R4) = -2.79 V. EN/UVLO is tied to +3V3.",
       (CX - 40.64, YR - 19.05))
s.text("VIN must stay above 3.0 V (LT8330 minimum). SW swings between 0 V and VIN + |VOUT| = 6.1 V. Output passes JP3.",
       (CX - 40.64, YR - 15.24))
s.text("Switching: fixed 2 MHz oscillator (CCM duty D = (2.79 + 0.3) / (2.79 + 0.3 + 3.3) = 0.484, ton 242 ns); below about 17 mA it runs in Burst Mode:",
       (CX - 40.64, YR - 11.43))
s.text("single pulses (ton about 80 ns, 240 mA switch limit) at about 11 / 114 / 572 kHz for 0.1 / 1 / 5 mA (estimate).",
       (CX - 40.64, YR - 7.62))
u3 = nxt("U")
pins = s.place("mp", IC8330, u3, "LT8330", CX, CY, ref_at=(CX, CY - 9.0), val_at=(CX, CY + 8.0), mirror=True)
# mirrored pins: left VIN(6) INTVCC(5) EN(4); right SW(1) GND(2) FBX(3)

# input rail and input cap
nvin = (CX - 40.64, YR)
s.label("+3V3", nvin)
_, ct, cb = cap_v(C47, "4.7uF/10V", (nvin[0], nvin[1] + 5.08))
s.wire(nvin, ct)
gnd_symbol(cb)

# VIN pin up to the rail (T junction at tj)
vin = pins["6"]
tj = (CX - 20.32, YR)
s.wire(vin, (tj[0], vin[1]), tj)

# L3: +3V3 -> SW node
_, l1a, l1b = passive_h(IND, "2.2uH", CX, YR, "L")
swn = (CX + 12.7, YR)
s.wire(nvin, tj, l1a)
s.junction(tj)
s.wire(l1b, (CX + 8.89, YR), swn)
test_point("SW_C", CX + 8.89, YR, "up", "left")
sw = pins["1"]
s.wire(sw, swn)
s.label("SW_C", (sw[0], sw[1] - 5.08))

# CDC: SW node -> node A
_, cda, cdb = passive_h(C1U, "1uF/25V", CX + 25.4, YR, "C")
anode = (CX + 38.1, YR)
s.wire(swn, cda)
s.wire(cdb, anode)

# D1: anode on node A, cathode to GND
dref = nxt("D")
dp = s.place("mp", DIODE, dref, "PMEG6010CEJ", anode[0], YR + 10.16, rot=90,
             ref_at=(anode[0] + 8.89, YR + 8.89), val_at=(anode[0] + 8.89, YR + 11.43))
dtop = min(dp.values(), key=lambda q: q[1])
dbot = max(dp.values(), key=lambda q: q[1])
s.wire(anode, dtop)
s.label("CPL_C", (anode[0], YR + 2.54))
gnd_symbol(dbot)

# L4: node A -> output node
_, l2a, l2b = passive_h(IND, "2.2uH", CX + 50.8, YR, "L")
s.wire(anode, (CX + 41.91, YR), l2a)
s.junction(anode)
test_point("CPL_C", CX + 41.91, YR, "up", "left")
vout = (CX + 63.5, YR)
s.wire(l2b, vout)
s.label(NEG, (vout[0] + 2.54, vout[1]))
_, cot, cob = cap_v(C10, "10uF/6.3V", (vout[0], vout[1] + 5.08))
s.wire(vout, cot)
gnd_symbol(cob)

# feedback divider: R4 (1M) rail -> FBX node, R5 (402k) FBX node -> GND, phase-lead C across R4
rx = CX + 88.9
cx2 = CX + 109.22
rail_r4 = (rx, YR)
s.wire(vout, (CX + 76.2, YR), rail_r4)
s.junction(vout)
r4t, r4b = passive_v(R1M, "1M 1%", rx, YR + 10.16, "R")
s.wire(rail_r4, r4t)
fbx_n = (rx, YR + 17.78)
s.wire(r4b, fbx_n)
r5t, r5b = passive_v(R402K, "402k 1%", rx, YR + 25.4, "R")
s.wire(fbx_n, r5t)
gnd_symbol(r5b)
c4t, c4b = passive_v(C4P7, "4.7pF", cx2, YR + 10.16, "C")
s.wire(rail_r4, (cx2, YR))
s.wire((cx2, YR), c4t)
s.wire(c4b, (cx2, fbx_n[1]), fbx_n)
s.junction(rail_r4)
s.junction((cx2, YR))
s.junction(fbx_n)

# FBX pin routed to the divider middle node
fbx = pins["3"]
vx = CX + 82.55
s.wire(fbx, (CX + 50.8, fbx[1]), (vx, fbx[1]), (vx, fbx_n[1]), fbx_n)
s.label("FBX_C", (fbx[0] + 2.54, fbx[1]))
test_point("FBX_C", CX + 50.8, fbx[1], "down", "right")

# GND pin
s.stub_label(pins["2"], "GND", "right")

# left side: EN to +3V3, INTVCC bypass capacitor with TP
s.stub_label(pins["4"], "+3V3", "left")
iv = pins["5"]
ivx = CX - 22.86
s.wire(iv, (ivx, iv[1]))
ct2, cb2 = passive_v(C1U, "1uF/25V", ivx, iv[1] + 12.7, "C")
s.wire((ivx, iv[1]), (ivx, iv[1] + 3.81), ct2)
gnd_symbol(cb2)
s.label("INTVCC_C", (ivx, iv[1] + 7.62))
test_point("INTVCC_C", ivx, iv[1] + 3.81, "left", "left")

# output rail to JP3 with TP
jx, jy = CX + 134.62, YR + 1.27
jp = s.place("mp", HDR2, "JP3", "Current jumper", jx, jy, ref_at=(jx, jy - 7.0), val_at=(jx, jy + 6.0))
s.wire((cx2, YR), (CX + 124.46, YR), (jp["1"][0], YR))
test_point(NEG, CX + 124.46, YR, "up", "right")
e = (jp["2"][0] - 15.24, jp["2"][1])
s.wire(jp["2"], (jp["2"][0] - 7.62, jp["2"][1]), e)
s.label("-2V8", e, just="right")
test_point("-2V8", jp["2"][0] - 7.62, jp["2"][1], "down", "left")

# Input connector J1 (+3V3 and GND test points sit on its wires)
J1X, J1Y = 38.1, 127.0
j1 = s.place("mp", HDR2, "J1", "Power in", J1X, J1Y, ref_at=(J1X, J1Y - 7.0), val_at=(J1X, J1Y + 6.0))
s.text("Input", (J1X - 10, J1Y - 21), size=2.0, bold=True)
s.text("Pin 1: +3.3 V\nPin 2: GND", (J1X - 10, J1Y - 16))
p1 = j1["1"]
e1 = (p1[0] - 15.24, p1[1])
s.wire(p1, (p1[0] - 7.62, p1[1]), e1)
s.label("+3V3", e1, just="right")
test_point("+3V3", p1[0] - 7.62, p1[1], "up", "left")
s.wire(e1, (e1[0], e1[1] - 2.54))
s.place("mpx", "PWR_FLAG", "#FLG01", "PWR_FLAG", e1[0], e1[1] - 2.54)
p2 = j1["2"]
e2 = (p2[0] - 15.24, p2[1])
s.wire(p2, (p2[0] - 7.62, p2[1]), e2)
s.label("GND", e2, just="right")
test_point("GND", p2[0] - 7.62, p2[1], "down", "left")
s.wire(e2, (e2[0], e2[1] + 2.54))
s.place("mpx", "PWR_FLAG", "#FLG02", "PWR_FLAG", e2[0], e2[1] + 2.54, rot=180)

# Output connector J2
J2X, J2Y = 300.99, 127.0
j2 = s.place("mp", HDR4, "J2", "Power out", J2X, J2Y, ref_at=(J2X, J2Y - 10.0), val_at=(J2X, J2Y + 9.0))
s.text("Outputs", (J2X - 22, J2Y - 24), size=2.0, bold=True)
s.text("Pin 1: GND\nPin 2: +2.8 V\nPin 3: -2.8 V\nPin 4: +1.4 V", (J2X - 22, J2Y - 19))
for num, net in (("1", "GND"), ("2", "+2V8"), ("3", "-2V8"), ("4", "+1V4")):
    e = (j2[num][0] - 15.24, j2[num][1])
    s.wire(j2[num], e)
    s.label(net, e, just="right")

# ================================================================ controller-driven rails
# Separate +2.75 V supply; the (generic, low-power STM32) controller sits on header J5.
SX = 391.16  # start x of the three rows


def end_wire_label(pin, name, direction="left", length=15.24, tp=None):
    """Wire from a header pin with a label at the end; optional (direction, ref_side) test point at mid-length."""
    sign = -1 if direction == "left" else 1
    e = (round(pin[0] + sign * length, 3), pin[1])
    if tp:
        mid = (round(pin[0] + sign * length / 2, 3), pin[1])
        s.wire(pin, mid, e)
        test_point(name, mid[0], mid[1], tp[0], tp[1])
    else:
        s.wire(pin, e)
    s.label(name, e, just="right" if direction == "left" else "left")
    return e


L100 = "LBR2012T101M"
L47 = "LB2012T470M"
HDR6 = "PZ254V-11-06P"
HDR3 = "PZ254V-11-03P_C2937625"
PFET = "SI2301CDS-T1-GE3"
R845K = "RMS04FT8453"
R215M = "RC0402FR-072M15L"

s.text("Controller-driven rails (separate +2.75 V supply, generic low-power STM32 on J5)", (SX - 45.72, 20.32), size=2.5, bold=True)
s.text("Design notes, assumptions and the unregulated load swing: docs/controller-rails.md", (SX - 45.72, 26.67))

# ---- J3: +2.75 V input
J3X, J3Y = 345.44, 63.5
j3 = s.place("mp", HDR2, "J3", "+2.75 V in", J3X, J3Y, ref_at=(J3X, J3Y - 7.0), val_at=(J3X, J3Y + 6.0))
s.text("Input +2.75 V", (J3X - 10, J3Y - 21), size=2.0, bold=True)
s.text("Pin 1: +2.75 V\nPin 2: GND", (J3X - 10, J3Y - 16))
e = end_wire_label(j3["1"], "+2V75", length=22.86, tp=("up", "left"))
s.wire(e, (e[0], e[1] - 2.54))
s.place("mpx", "PWR_FLAG", "#FLG03", "PWR_FLAG", e[0], e[1] - 2.54)
end_wire_label(j3["2"], "GND")

# ---- J5: controller interface
J5X, J5Y = 345.44, 152.4
j5 = s.place("mp", HDR6, "J5", "Controller", J5X, J5Y, ref_at=(J5X, J5Y - 11.0), val_at=(J5X, J5Y + 10.0))
s.text("Controller interface", (J5X - 10, J5Y - 28), size=2.0, bold=True)
s.text("Generic low-power STM32. Pin 1 powers it from +2.75 V.\nPins 3 to 5: timer outputs. Pin 6: analog input (sense).",
       (J5X - 10, J5Y - 23))
for num, net in (("1", "+2V75"), ("2", "GND"), ("3", "BUCK_DRV"), ("4", "A_DRV"), ("5", "B_DRV"), ("6", "SENSE")):
    end_wire_label(j5[num], net)

# ---- Block D: +1.375 V buck, inductor driven directly from a pin
yD = 63.5
s.text("Block D: +1.375 V buck, inductor driven directly from a controller pin", (SX, yD - 25.4), size=2.0, bold=True)
s.text("BUCK_DRV is a push-pull timer output (about 2 MHz, duty 0.516). L5 and the output capacitor filter it; the pin sinks current too,",
       (SX, yD - 20.32))
s.text("so the stage stays in continuous conduction at any load and the unregulated output follows the load only by the pin resistance.",
       (SX, yD - 16.51))
s.text("BUCK_DRV: f = 2 MHz, duty D = 0.516 for 1.375 V at 1 mA (0.5016 at 0.1 mA, 0.532 at 2 mA; ideal 1.375 / 2.75 = 0.500). Needs a timer clock of 64 MHz or more for steps below 90 mV.",
       (SX, yD - 12.7))
start = (SX, yD)
s.label("BUCK_DRV", start)
_, l5a, l5b = passive_h(L100, "100uH", SX + 25.4, yD, "L")
s.wire(start, (SX + 8.89, yD), l5a)
test_point("BUCK_DRV", SX + 8.89, yD, "up", "right")
nd = (SX + 43.18, yD)
s.wire(l5b, (SX + 36.83, yD), nd)
test_point("+1V375_IC", SX + 36.83, yD, "up", "right")
_, cdt, cdb = cap_v(C47, "4.7uF/10V", (nd[0], nd[1] + 5.08))
s.wire(nd, cdt)
gnd_symbol(cdb)
s.label("+1V375_IC", (nd[0] + 3.81, nd[1]))
jx4 = SX + 95.25
jp4 = s.place("mp", HDR2, "JP4", "Current jumper", jx4, yD + 1.27, ref_at=(jx4, yD - 5.7), val_at=(jx4, yD + 7.27))
s.wire(nd, (jp4["1"][0], yD))
end_wire_label(jp4["2"], "+1V375", tp=("down", "left"))

# ---- Block E-A: pin-driven charge pump
yA = 129.54
s.text("Block E-A: -2.75 V inverter, option A (pin-driven charge pump, no inductor)", (SX, yA - 25.4), size=2.0, bold=True)
s.text("A_DRV swings the flying capacitor 0 to 2.75 V; D2 and D3 steer the charge. Unregulated output about -2.1 to -2.4 V (cannot reach -2.75 V).",
       (SX, yA - 20.32))
s.text("A_DRV: f = 500 kHz (100 kHz to 1 MHz works), duty D = 0.50 (symmetric square wave).", (SX, yA - 16.51))
start = (SX, yA)
s.label("A_DRV", start)
_, cfa, cfb = passive_h(C1U, "1uF/25V", SX + 25.4, yA, "C")
s.wire(start, (SX + 8.89, yA), cfa)
test_point("A_DRV", SX + 8.89, yA, "up", "right")
na = (SX + 38.1, yA)
dref = nxt("D")
dp = s.place("mp", DIODE, dref, "PMEG6010CEJ", na[0], yA + 10.16, rot=90,
             ref_at=(na[0] + 8.89, yA + 8.89), val_at=(na[0] + 8.89, yA + 11.43))
dtop = min(dp.values(), key=lambda q: q[1])
dbot = max(dp.values(), key=lambda q: q[1])
s.wire(cfb, na)
s.wire(na, dtop)
s.junction(na)
gnd_symbol(dbot)
dref2 = nxt("D")
dp2 = s.place("mp", DIODE, dref2, "PMEG6010CEJ", SX + 50.8, yA, ref_at=(SX + 50.8, yA - 3.81), val_at=(SX + 50.8, yA + 3.81))
d2c = min(dp2.values(), key=lambda q: q[0])  # cathode (pin 1) on the left
d2a = max(dp2.values(), key=lambda q: q[0])  # anode (pin 2) on the right
s.wire(na, (SX + 41.91, yA), d2c)
test_point("N_A", SX + 41.91, yA, "up", "left")
s.label("N_A", (na[0], yA + 2.54))
noa = (SX + 63.5, yA)
s.wire(d2a, (SX + 59.69, yA), noa)
test_point("-2V75_A", SX + 59.69, yA, "up", "right")
_, coat, coab = cap_v(C47, "4.7uF/10V", (noa[0], noa[1] + 5.08))
s.wire(noa, coat)
gnd_symbol(coab)
s.label("-2V75_A", noa)

# ---- Block E-B: P-FET + inductor + Schottky, regulated by the controller in burst mode
yB = 214.63
ys = yB - 5.08  # drain level
s.text("Block E-B: -2.75 V inverter, option B (P-FET + inductor, regulated by the controller in burst mode)", (SX, yB - 40.64), size=2.0, bold=True)
s.text("B_DRV gates Q1 (low = on). While Q1 is on, L6 charges from +2.75 V; when it turns off the stored energy flows through D4 into the negative rail.",
       (SX, yB - 35.56))
s.text("U4 (LPV521, 0.35 uA) inverts the rail into SENSE = 0.499 x |VRAIL| (1.37 V at -2.75 V); the controller skips pulses once SENSE reaches the target.",
       (SX, yB - 31.75))
s.text("B_DRV: fixed ton = 0.855 us (Ipk 50 mA in L6), toff 0.80 us; burst rate 6 / 61 / 122 kHz = average duty 0.5 / 5.2 / 10.4 % for 0.1 / 1 / 2 mA.",
       (SX, yB - 27.94))
start = (SX, yB)
s.label("B_DRV", start)
qx = SX + 31.75
pg = (SX + 17.78, yB)  # gate pull-up junction
q1 = s.place("mp", PFET, "Q1", "Si2301CDS", qx, yB, ref_at=(qx - 1.27, yB + 11.43), val_at=(qx - 1.27, yB + 14.0))
s.wire(start, (SX + 8.89, yB), pg, q1["1"])
s.junction(pg)
test_point("B_DRV", SX + 8.89, yB, "up", "right")
rpt, rpb = passive_v(R1M, "1M 1%", pg[0], yB - 10.16, "R")
s.wire(pg, rpb)
s.wire(rpt, (rpt[0], rpt[1] - 2.54))
s.label("+2V75", (rpt[0], rpt[1] - 2.54))
src_end = (q1["2"][0], q1["2"][1] + 2.54)
s.wire(q1["2"], src_end)
s.label("+2V75", src_end)
nsw = (qx + 11.43, ys)
s.wire(q1["3"], (qx + 6.35, ys), nsw)
test_point("SW_PB", qx + 6.35, ys, "up", "left")
s.label("SW_PB", (nsw[0], nsw[1] + 2.54))
lt, lb = passive_v(L47, "47uH", nsw[0], ys + 10.16, "L")
s.wire(nsw, lt)
gnd_symbol(lb)
dref3 = nxt("D")
dp3 = s.place("mp", DIODE, dref3, "PMEG6010CEJ", nsw[0] + 10.16, ys, ref_at=(nsw[0] + 10.16, ys - 3.81), val_at=(nsw[0] + 10.16, ys + 3.81))
d3c = min(dp3.values(), key=lambda q: q[0])
d3a = max(dp3.values(), key=lambda q: q[0])
s.wire(nsw, d3c)
nob = (nsw[0] + 25.4, ys)
s.wire(d3a, (nsw[0] + 20.32, ys), nob)
test_point("-2V75_B", nsw[0] + 20.32, ys, "up", "right")
_, cobt, cobb = cap_v(C47, "4.7uF/10V", (nob[0], nob[1] + 5.08))
s.wire(nob, cobt)
gnd_symbol(cobb)
s.label("-2V75_B", nob)
# sense amplifier: ultra-low-power inverting amplifier (LPV521) turns the negative rail into a positive SENSE voltage
OPA = "LPV521MGX_NOPB"
R4M99 = "RC0402FR-074M99L"
R2M49 = "FRC0402F2494TS"
C10P = "CC0402JRNPO9BN100"
C100N = "CL05B104KO5NNNC"
s.wire(nob, (nob[0] + 8.89, ys))
_, rina, rinb = passive_h(R4M99, "4.99M 1%", nob[0] + 22.86, ys, "R", ref_at=(nob[0] + 22.86, ys + 3.81), val_at=(nob[0] + 22.86, ys + 6.35))
s.wire((nob[0] + 8.89, ys), rina)
inn = (nob[0] + 33.02, ys)
s.wire(rinb, (nob[0] + 30.48, ys), inn)
test_point("SNS_IN", nob[0] + 30.48, ys, "up", "left")
s.label("SNS_IN", inn)
ux, uy = nob[0] + 53.34, ys + 2.54
u4 = nxt("U")
op = s.place("mp", OPA, u4, "LPV521", ux, uy, ref_at=(ux + 3.0, uy - 5.0), val_at=(ux + 3.0, uy + 5.0))
s.wire(inn, op["4"])
s.junction(inn)
gnd_in = (op["3"][0] - 2.54, op["3"][1])
s.wire(op["3"], gnd_in)
gnd_symbol(gnd_in)
# supply: V+ to +2V75 with a bypass capacitor, V- to GND
vp = (op["5"][0], op["5"][1] - 5.08)
s.wire(op["5"], vp)
s.label("+2V75", vp)
byp = (vp[0] + 7.62, vp[1])
s.wire(vp, byp)
bt, bb = passive_v(C100N, "100nF", byp[0], byp[1] + 5.08, "C")
s.wire(byp, bt)
gnd_symbol(bb)
vm = (op["2"][0], op["2"][1] + 2.54)
s.wire(op["2"], vm)
gnd_symbol(vm)
# output = SENSE, feedback Rf with Cf in parallel
outn = (op["1"][0] + 5.08, op["1"][1])
s.wire(op["1"], (op["1"][0] + 2.54, op["1"][1]), outn)
test_point("SENSE", op["1"][0] + 2.54, op["1"][1], "up", "right")
s.label("SENSE", outn)
yf = ys + 20.32
s.wire(outn, (outn[0], yf))
_, rfa, rfb = passive_h(R2M49, "2.49M 1%", ux, yf, "R", ref_at=(ux, yf + 3.81), val_at=(ux, yf + 6.35))
jr = (ux + 10.16, yf)
s.wire((outn[0], yf), jr, rfb)
s.junction(jr)
jl = (ux - 10.16, yf)
s.wire(rfa, jl, (inn[0], yf), inn)
s.junction(jl)
yc = yf + 12.7
_, cfa2, cfb2 = passive_h(C10P, "10pF", ux, yc, "C", ref_at=(ux, yc + 3.81), val_at=(ux, yc + 6.35))
s.wire(jr, (jr[0], yc), cfb2)
s.wire(cfa2, (jl[0], yc), jl)

# ---- separate series current jumpers for option A and option B; both feed the -2V75 output net
JAX, JAY = 548.64, 274.32
jpa = s.place("mp", HDR2, "JP5", "Current jumper A", JAX, JAY, ref_at=(JAX, JAY - 6.0), val_at=(JAX, JAY + 6.0))
s.text("-2.75 V output jumpers (fit only ONE)", (JAX - 35, JAY - 20), size=2.0, bold=True)
s.text("JP5: charge pump (option A)\nJP6: inductor stage (option B)", (JAX - 35, JAY - 15))
end_wire_label(jpa["1"], "-2V75_A")
end_wire_label(jpa["2"], "-2V75", tp=("down", "left"))
JBX, JBY = 548.64, 299.72
jpb = s.place("mp", HDR2, "JP6", "Current jumper B", JBX, JBY, ref_at=(JBX, JBY - 6.0), val_at=(JBX, JBY + 6.0))
end_wire_label(jpb["1"], "-2V75_B")
end_wire_label(jpb["2"], "-2V75")
J4X, J4Y = 571.5, 133.35
j4 = s.place("mp", HDR3, "J4", "Controller rails out", J4X, J4Y, ref_at=(J4X, J4Y - 9.0), val_at=(J4X, J4Y + 8.0))
s.text("Outputs (controller rails)", (J4X - 30, J4Y - 21), size=2.0, bold=True)
s.text("Pin 1: GND\nPin 2: +1.375 V\nPin 3: -2.75 V", (J4X - 30, J4Y - 16))
for num, net in (("1", "GND"), ("2", "+1V375"), ("3", "-2V75")):
    s.stub_label(j4[num], net, "left")

s.write()
print("wrote", OUT)
print("test points:", len(TP_NETS), TP_NETS)
