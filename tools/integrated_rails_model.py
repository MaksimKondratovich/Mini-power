#!/usr/bin/env python3
"""Duty cycle and switching frequency of the integrated-converter rails (nominal, first order).

TPS62840/41 (DCS-Control): nominal 1.8 MHz in PWM; in power-save mode the switching frequency varies linearly with the
load (datasheet). The light-load numbers below ASSUME that each power-save pulse keeps the PWM on-time
ton = D / 1.8 MHz, so one pulse transfers Q = 0.5 x Ipk x (ton + toff) with Ipk = (Vin - Vout) x ton / L,
toff = Ipk x L / Vout (discontinuous conduction), and f = Iload / Q. This is an estimate, not a datasheet figure.

LT8330 (inverting): fixed 2 MHz oscillator (1.85 to 2.15 MHz) at higher load; at light load it runs in low-ripple Burst
Mode with a switch current limit of about 240 mA (datasheet). Estimate: each burst pulse stores 0.5 x (L3 + L4) x (Ipk / 2)^2
(the switch current is the sum of both inductor currents, Ipk = 240 mA) and 77 % of it reaches the output.

Run:  python tools/integrated_rails_model.py
"""
import math

VIN = 3.3
L = 2.2e-6
F_PWM = 1.8e6
LOADS = [0.1e-3, 1e-3, 2e-3, 5e-3]


def tps(vout):
    d = vout / VIN
    ton = d / F_PWM
    ipk = (VIN - vout) * ton / L
    toff = ipk * L / vout
    q = 0.5 * ipk * (ton + toff)
    return d, ton, ipk, toff, q


def lt8330(vout=2.79, vd=0.3, ipk_sw=0.24, eta=0.77):
    d = (vout + vd) / (vout + vd + VIN)
    ton_ccm = d / 2e6
    e = 0.5 * (L + L) * (ipk_sw / 2) ** 2
    ton_burst = (ipk_sw / 2) / (VIN / L)
    return d, ton_ccm, e, ton_burst, eta


def main():
    for name, vout in (("TPS62840 +2.8 V (rail A)", 2.8), ("TPS62841 +1.4 V (rail B)", 1.4)):
        d, ton, ipk, toff, q = tps(vout)
        print("%s: PWM %.1f MHz, D = %.3f, ton = %.0f ns; power-save pulse: Ipk = %.0f mA, toff = %.0f ns, Q = %.1f nC"
              % (name, F_PWM / 1e6, d, ton * 1e9, ipk * 1e3, toff * 1e9, q * 1e9))
        print("   load [mA]      " + "  ".join("%7.1f" % (i * 1e3) for i in LOADS))
        print("   f_pfm [kHz]    " + "  ".join("%7.1f" % (i / q / 1e3) for i in LOADS))
        print("   avg on-duty [%] " + "  ".join("%6.2f" % (100 * ton * i / q) for i in LOADS))
        print("   PWM/PFM boundary at I = dI/2 = %.0f mA (above the 5 mA maximum, so the rail is always in power-save)" % (ipk * 1e3 / 2))
    d, ton_ccm, e, ton_b, eta = lt8330()
    print("\nLT8330 -2.79 V: CCM duty D = (|Vo| + Vd) / (|Vo| + Vd + Vin) = %.3f (ton = %.0f ns at 2 MHz)" % (d, ton_ccm * 1e9))
    print("   burst pulse: ton = %.0f ns, energy %.1f nJ stored, %.1f nJ delivered" % (ton_b * 1e9, e * 1e9, e * eta * 1e9))
    print("   load [mA]      " + "  ".join("%7.1f" % (i * 1e3) for i in LOADS))
    rates = [2.79 * i / (e * eta) for i in LOADS]
    print("   burst f [kHz]  " + "  ".join("%7.1f" % (r / 1e3) for r in rates))
    print("   avg on-duty [%] " + "  ".join("%6.2f" % (100 * ton_b * r) for r in rates))
    print("   load at which the burst rate reaches the 2 MHz oscillator: %.0f mA" % (2e6 * e * eta / 2.79 * 1e3))


if __name__ == "__main__":
    main()
