#!/usr/bin/env python3
"""Nominal model of the controller-driven (GPIO) rails, powered from +2.75 V.

All GPIO numbers are ASSUMPTIONS for a generic low-power STM32 (no exact part chosen):
  Ron of a push-pull pin at 2.75 V: 40 ohm (high side and low side), pin + wiring capacitance 10 pF,
  MCU run current with the timer clocked: 20 uA (reported separately, not charged to the converter).
Run:  python tools/controller_rails_model.py
"""
import math

VDD = 2.75
RON = 40.0       # ohm, assumed GPIO output resistance (each side)
CPIN = 10e-12    # F, pin + inductor winding + layout capacitance switched every cycle
I_MCU = 20e-6    # A, assumed MCU current while the timer runs (not part of the converter loss)
LOADS = [0.1e-3, 1e-3, 2e-3]   # 10 %, 100 %, 200 % of the 1 mA typical load


# ---------------------------------------------------------------- forced-CCM buck driven from one pin
def buck_period(vo, d, f, l, dcr):
    """Periodic steady state of the inductor current with constant output voltage vo.
    Returns (mean current, ripple pk-pk, rms^2)."""
    t = 1.0 / f
    ron = RON + dcr
    # ON: i' = (vdd - vo - i*ron)/l   OFF: i' = (-vo - i*ron)/l
    a_on = (VDD - vo) / ron
    a_off = (-vo) / ron
    tau = l / ron
    e1 = math.exp(-d * t / tau)
    e2 = math.exp(-(1 - d) * t / tau)
    # i0 -> after ON: a_on + (i0-a_on) e1 -> after OFF: a_off + (that - a_off) e2 = i0
    i0 = (a_off * (1 - e2) + (a_on * (1 - e1)) * e2) / (1 - e1 * e2)
    n = 400
    pts = []
    for k in range(n):
        tt = (k + 0.5) / n * t
        if tt < d * t:
            i = a_on + (i0 - a_on) * math.exp(-tt / tau)
        else:
            i_on_end = a_on + (i0 - a_on) * e1
            i = a_off + (i_on_end - a_off) * math.exp(-(tt - d * t) / tau)
        pts.append(i)
    mean = sum(pts) / n
    ripple = max(pts) - min(pts)
    rms2 = sum(p * p for p in pts) / n
    return mean, ripple, rms2, min(pts), max(pts)


def buck_vout(d, i_load, f, l, dcr):
    lo, hi = 0.0, VDD
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        mean = buck_period(mid, d, f, l, dcr)[0]
        if mean > i_load:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def buck_case(l, f, dcr, target=1.375, i_cal=1e-3):
    lo, hi = 0.3, 0.8
    for _ in range(50):
        d = 0.5 * (lo + hi)
        if buck_vout(d, i_cal, f, l, dcr) < target:
            lo = d
        else:
            hi = d
    rows = []
    for il in LOADS:
        vo = buck_vout(d, il, f, l, dcr)
        mean, rip, rms2, imin, imax = buck_period(vo, d, f, l, dcr)
        # conduction loss: the same RMS current flows through the active switch and the DCR
        p_cond = rms2 * ((d * RON) + ((1 - d) * RON) + dcr)
        p_cap = CPIN * VDD ** 2 * f
        p_out = vo * il
        eta = p_out / (p_out + p_cond + p_cap)
        eta_sys = p_out / (p_out + p_cond + p_cap + I_MCU * VDD)
        rows.append((il, vo, rip, imin, imax, p_cond, p_cap, eta, eta_sys))
    return d, rows


# ---------------------------------------------------------------- inverting rail candidates
def schottky_vf(i):
    """Assumed low-leakage 60 V Schottky: 0.20 V at 1 mA, 63 mV per decade."""
    return 0.20 + 0.063 * math.log10(max(i, 1e-9) / 1e-3)


def charge_pump(i_load):
    """Pin-driven inverting charge pump (flying cap + 2 Schottky + output cap), no inductor.
    Diode currents are pulses of about 2x the load current (50 % duty)."""
    vf = schottky_vf(2 * i_load)
    rout = 2 * RON          # assumed: both pin resistances in the charge path
    vo = -(VDD - 2 * vf - i_load * rout)
    return vo


def dcm_constant_power(i_load, i_nom=1e-3, v_nom=2.75):
    """Fixed-frequency, fixed-on-time inverting buck-boost in DCM is a constant-power source."""
    p = v_nom * i_nom
    return -p / i_load


def main():
    print("Assumptions: Vdd %.2f V, GPIO Ron %.0f ohm each side, Cpin %.0f pF, MCU %.0f uA" % (VDD, RON, CPIN * 1e12, I_MCU * 1e6))
    cases = [
        ("47 uH  3.7 ohm (C223254)", 47e-6, 3.7, 1e6),
        ("100 uH 4.0 ohm (C223273)", 100e-6, 4.0, 1e6),
        ("100 uH 4.0 ohm (C223273)", 100e-6, 4.0, 500e3),
        ("100 uH 4.0 ohm (C223273)", 100e-6, 4.0, 2e6),
        ("47 uH  3.7 ohm (C223254)", 47e-6, 3.7, 2e6),
    ]
    for name, l, dcr, f in cases:
        d, rows = buck_case(l, f, dcr)
        print("\nBuck 2.75 V -> 1.375 V, %s, f = %.0f kHz, duty set at 1 mA: D = %.3f" % (name, f / 1e3, d))
        print("  load[mA]  Vout[V]  ripple[mA]  Imin..Imax[mA]  Pcond[uW]  Pcap[uW]  eta  eta_with_MCU")
        for il, vo, rip, imin, imax, pc, pcap, eta, esys in rows:
            print("  %7.2f  %7.4f  %9.2f  %6.1f..%-6.1f  %9.1f  %8.1f  %4.0f%%  %4.0f%%" % (
                il * 1e3, vo, rip * 1e3, imin * 1e3, imax * 1e3, pc * 1e6, pcap * 1e6, eta * 100, esys * 100))
    print("\nInverting candidates, load 0.1 / 1 / 2 mA")
    print("  charge pump (no inductor):", ["%.3f V" % charge_pump(i) for i in LOADS])
    print("  fixed-ton DCM buck-boost, unregulated:", ["%.2f V" % dcm_constant_power(i) for i in LOADS])


if __name__ == "__main__":
    main()
