# Power architecture and converter selection

Status: **all three rails are drawn in the schematic; the -2.8 V rail uses an LT8330 (section 6).** Nominal-value calculations only (see CLAUDE.md).
Part status checked against the JLCPCB parts API on 2026-10-03.

## 1. Requirements recap
- Input +3.3 V. Outputs +2.8 V, -2.8 V, +1.4 V (user accepted 2.8 V / 1.4 V instead of 2.75 V / 1.375 V, and -2.8 V; the LT8330 divider gives -2.79 V).
- 5 mA maximum, 1 mA typical per rail. Efficiency above all. Common ground.

## 2. Why nanoamp-Iq switchers, not LDOs
At 1 mA the output power is only 2.8 mW (2.8 V rails) or 1.4 mW (1.4 V rail), so the converter's own consumption matters as much as its conversion efficiency.

| Rail | Ideal LDO efficiency (Vout / Vin) | Result |
|---|---|---|
| +2.8 V | 2.8 / 3.3 = 84.8 % (before LDO Iq) | at best 85 % |
| +1.4 V | 1.4 / 3.3 = 42.4 % | poor |
| -2.8 V | not possible with an LDO from +3.3 V | needs an inverting converter |

A buck converter with ~60 nA Iq does not have this ceiling. Its Iq is tiny against 1 mA: 60 nA x 3.3 V = 0.2 uW versus 2800 uW of output power (0.007 %). The remaining loss is switching and conduction loss in the power stage. Expected efficiency at 1 to 5 mA is roughly 85 to 92 %, but this figure comes from my reading of TI's typical curves and has **not** been verified against the datasheet graphs. Treat it as an estimate.

## 3. Selected parts

| Rail | IC | LCSC | JLCPCB class | Stock (2026-10-03) | Why |
|---|---|---|---|---|---|
| +2.8 V | TPS62840DLC (SON-8) | C2071859 | extended | 3884 | 60 nA Iq, 1.8 to 6.5 V in, 2.8 V is a built-in setting selected by one resistor |
| +1.4 V | TPS62841DLC (SON-8) | C2860681 | extended | 254 | same family, 0.8 to 1.55 V in 50 mV steps, 1.4 V is a built-in setting |

Why this family: it has the lowest quiescent current of any converter I found (60 nA), it needs no feedback divider (the output is set by one RSET resistor, so there is no divider current to waste), 

Rejected: TPS62743 (360 nA Iq, 6x more), TPS62843 (275 nA Iq, needs a feedback divider and is limited to 5.5 V input, which rules it out for the inverting rail). TPS5430 and XL1509 are the only basic DC-DC parts; they need 4.5 V or more input and burn milliamps.

## 4. Output voltage setting (RSET)
The IC reads one resistor from VSET to GND and selects the output voltage (datasheet Table 1, E96 values, 1 % required).

| IC | Output | RSET | LCSC (1 %, 0402) | Class |
|---|---|---|---|---|
| TPS62840 | 2.8 V | 28.7 k | C26972 (0402WGF2872TCE, 16.7k in stock) | extended |
| TPS62841 | 1.4 V | 52.3 k | C26982 (0402WGF5232TCE, 10.4k in stock) | extended |

Both resistors are 1 % (the datasheet requires 1 % and +/-200 ppm/C or better; these are +/-100 ppm/C).

## 5. Buck converters (+2.8 V and +1.4 V): calculations
Common: f_sw = 1.8 MHz nominal (PWM), L = 2.2 uH, Iout max = 5 mA, Vin = 3.3 V.
Duty cycle D = Vout / Vin. Ripple (datasheet Eq. 4): dIL = Vout x (1 - Vout/Vin) / (L x f). Peak current (Eq. 5): ILmax = Iout max + dIL / 2.

| | +2.8 V | +1.4 V |
|---|---|---|
| D | 2.8 / 3.3 = 0.848 | 1.4 / 3.3 = 0.424 |
| dIL | 2.8 x 0.152 / (2.2 uH x 1.8 MHz) = 0.4256 / 3.96 = 107 mA | 1.4 x 0.576 / 3.96 = 204 mA |
| ILmax | 5 mA + 54 mA = 59 mA | 5 mA + 102 mA = 107 mA |

Both are far below the high-side current limit (1.0 A minimum), so the 2.2 uH inductor and the 1.8 MHz design point are safe. At 1 to 5 mA the converter runs in power-save (PFM) mode, so the real switching frequency is much lower than 1.8 MHz and ripple is set by the output capacitor.

- **Inductor:** 2.2 uH, the datasheet's recommended value. DFE201612E-2R2M=P2, **C337893**, extended, 30.4k in stock. 116 mOhm DCR, Isat 1.8 A (above the 1.4 A max current limit, so it never saturates). DCR loss at 5 mA is negligible: 0.005^2 x 0.116 = 3 nW.
- **Input capacitor:** 4.7 uF 10 V X5R 0402, **C23733** (CL05A475MP5NRNC), **basic**.
- **Output capacitor:** 10 uF 6.3 V X5R 0402, **C23692971** (CGA0402X5R106M6R3GT), extended, 367k in stock. The datasheet allows +20 % / -50 % effective capacitance under DC bias. Nominal analysis only, so I keep 10 uF; the datasheet's own tests use this value.
- Capacitor leakage adds to Iq (datasheet note), so capacitors are not oversized.

## 6. Negative rail (-2.8 V): LT8330 inverting converter
The first proposal (a TPS62840 wired as an inverting buck-boost) was rejected by the user. The replacement is an off-the-shelf inverting IC, the **LT8330** (Analog Devices, LCSC C580285, TSOT-23-6, extended, 1228 in stock on 2026-10-03). It is a 3 to 40 V input, 60 V switch, 1 A current-limit part with 6 uA quiescent current in sleep (datasheet: 5.5 uA typical, 10 uA max, VIN = 12 V) and low-ripple Burst Mode, and it supports inverting outputs with a single FBX pin (regulation point -0.8 V). The datasheet's inverting topology uses two inductors and a coupling capacitor (Cuk-type), which is what the schematic draws.

### 6.1 Why this part
| Option | LCSC | Why not / why |
|---|---|---|
| **LT8330** | C580285 | Regulated, adjustable to -2.8 V, 6 uA Iq. Chosen. |
| LM27761 (regulated charge pump) | C129351 | Iq listed at 370 uA. Estimated efficiency |Vout|/Vin x Iout/(Iout+Iq) = 2.79 x 1 / (3.3 x 1.37) = 62 % at 1 mA, 79 % at 5 mA. Worse at the typical load. |
| TPS60402 / TPS60403 / LM2776 / ICL7660 | C10106 / C11338 / C69527 / C7535 | Unregulated charge pumps: output is about -3.3 V, not -2.8 V, and Iq is 65 to 200 uA. |
| LT8335 | C673756 | Same family, 2 A switch, but 5 in stock. |
| TPS63710, TPS65130 | C485552, C54989 | Iq in the mA range. |

### 6.2 Output voltage (datasheet: R3 = R4 x (|VOUT| / 0.80 V - 1))
- R3 (top, rail to FBX) = 1 M, R4 (FBX to GND) = 402 k, both 1 %.
- VOUT = -0.8 V x (1 + 1 M / 402 k) = -0.8 x 3.488 = **-2.790 V**.
- Divider current at -2.79 V: 2.79 V / 1.402 M = 2.0 uA. High-value resistors give the lowest quiescent current (datasheet).
- C8 = 4.7 pF C0G across R3 is the datasheet's phase-lead capacitor (zero near 30 to 60 kHz). I kept the datasheet value for a 1 M divider.

### 6.3 Operating point (nominal, VIN = 3.3 V, VOUT = -2.79 V, Io = 5 mA)
- Assume a Schottky drop VD = 0.3 V (PMEG6010CEJ at low current).
- Duty cycle (continuous conduction): D = (|VOUT| + VD) / (|VOUT| + VD + VIN) = 3.09 / 6.39 = 0.484.
- Output inductor current: IL4 = Io = 5 mA. Input inductor current: IL3 = Io x D / (1 - D) = 5 mA x 0.484 / 0.516 = 4.7 mA.
- Power check: Pin = 3.3 V x 4.7 mA = 15.5 mW. Pout + diode loss = (2.79 + 0.3) x 5 mA = 15.5 mW. OK.
- Voltage stress: switch and diode see VIN + |VOUT| = 6.1 V (limits 60 V). Coupling capacitor C6 sees 6.1 V (50 V part).
- Coupling capacitor RMS current: Io x sqrt(D / (1 - D)) = 5 mA x 0.97 = 4.8 mA.
- Inductor selection: the datasheet's CCM equation gives L = 0.5 x VIN x D / (dI_SW x fOSC). With dI_SW = 0.4 x 9.7 mA = 3.9 mA that is about 100 uH, far above the 0.68 to 10 uH range the IC is specified for. In practice the converter runs in discontinuous / Burst Mode at 1 to 5 mA, so I use 2.2 uH (C337893, the same part as the other rails, Isat 1.8 A above the 1.4 A switch current limit maximum). This keeps the part count down and is a judgement call; the datasheet's own -5 V example uses 2.7 uH.
- Quiescent power: 5.5 uA x 3.3 V = 18 uW, plus divider 2 uA x 2.79 V = 5.6 uW. About 24 uW, which is 0.9 % of the 2.8 mW output power at 1 mA.
- **Efficiency is not verified.** The datasheet's inverting curve is for a -5 V output and starts at 4 V in; I found no curve for 3.3 V in to -2.8 V at 1 mA. My estimate is 65 to 80 % at 1 mA (switching loss dominates), better than the charge-pump alternatives above. It must be measured.

### 6.4 Parts
| Ref | Part | LCSC | Class |
|---|---|---|---|
| U3 | LT8330ES6#TRMPBF | C580285 | extended |
| L3, L4 | DFE201612E-2R2M=P2, 2.2 uH | C337893 | extended |
| C6 (coupling) | 1 uF 25 V X5R 0402 CL05A105KA5NQNC | C52923 | basic |
| C9 (INTVCC, datasheet minimum 1 uF) | same | C52923 | basic |
| C5 (input) | 4.7 uF 10 V X5R 0402 | C23733 | basic |
| C7 (output) | 10 uF 6.3 V X5R 0402 | C23692971 | extended |
| C8 (phase lead) | 4.7 pF 50 V C0G 0402 0402CG4R7C500NT | C1569 | extended |
| D1 | PMEG6010CEJ,115, 60 V Schottky (the datasheet's recommended low-leakage diode) | C406049 | extended |
| R3 | 1 M 1 % 0402 | C26083 | basic |
| R4 | 402 k 1 % 0402 | C25785 | extended |

### 6.5 Risks
0. **1 uF in 0402:** C6 and C9 were changed from 0603 to 0402 (25 V X5R, basic). The 25 V rating keeps the DC-bias loss low, but the datasheet wants at least 1 uF on INTVCC: at about 3 V an 0402 X5R part typically loses roughly 10 to 15 % (not checked against this part's curve), so C9 may sit slightly under 1 uF. Use 2.2 uF (same package) if INTVCC shows ripple or start-up trouble.
1. **Input headroom:** the LT8330 needs VIN of at least 3.0 V. Your 3.3 V input leaves 0.3 V of margin, so the rail will not regulate if the supply sags below 3.0 V.
2. **Diode leakage** appears as extra load on a 1 mA rail (datasheet note). PMEG6010CEJ is specified at 50 uA maximum at 60 V; at 6 V it should be far lower, but I have not seen the curve.
3. **Uncoupled inductors:** the datasheet example uses a coupled pair; I use two separate 2.2 uH parts.
4. **Audible noise:** Burst Mode can excite ceramic capacitors at audio frequencies (datasheet note).
5. **Unverified:** efficiency and the compensation (4.7 pF with a 1 M divider) come from the datasheet's other output voltages; check on the bench.

## 7. Cost and part-count summary
- Extended part types: TPS62840DLC, TPS62841DLC, LT8330, PMEG6010CEJ, inductor C337893, 10 uF cap C23692971, 4.7 pF cap C1569, 1 % resistors 28.7 k / 52.3 k / 402 k, header C2691448 and C492401 (all PZ254V-series pin headers are extended).
- Basic part types: 4.7 uF C23733, 1 uF C52923, 1 M C26083.
- Test points are a footprint only (no purchased part).

## 8. Switching frequency and duty cycle of the integrated rails
Nominal values, VIN = 3.3 V, 2.2 uH, loads 0.1 / 1 / 2 / 5 mA. Reproduce with `python tools/integrated_rails_model.py`. The datasheet figures are the 1.8 MHz and 2 MHz oscillators; the light-load numbers are first-order estimates (see the assumptions below), not datasheet values.

| Rail | IC | Full-load switching | Duty | Light-load operation (0.1 / 1 / 2 / 5 mA) |
|---|---|---|---|---|
| +2.8 V | TPS62840 | 1.8 MHz nominal (PWM) | D = 2.8 / 3.3 = **0.848** (ton 471 ns) | power-save (PFM): about **3.4 / 34 / 67 / 168 kHz**, average on-duty 0.16 / 1.6 / 3.2 / 7.9 % |
| +1.4 V | TPS62841 | 1.8 MHz nominal (PWM) | D = 1.4 / 3.3 = **0.424** (ton 236 ns) | power-save (PFM): about **1.8 / 18 / 35 / 88 kHz**, average on-duty 0.04 / 0.4 / 0.8 / 2.1 % |
| -2.8 V | LT8330 | fixed 2 MHz oscillator (1.85 to 2.15 MHz) | CCM duty D = (2.79 + 0.3) / (2.79 + 0.3 + 3.3) = **0.484** (ton 242 ns) | Burst Mode below about 17 mA: single pulses of about 80 ns (240 mA switch limit) at about **11 / 114 / 229 / 572 kHz**, average on-duty 0.09 / 0.9 / 1.8 / 4.6 % |

Assumptions behind the light-load estimates:
- **TPS6284x:** the datasheet only says the power-save frequency "varies linearly with the load current". I assume every power-save pulse keeps the PWM on-time ton = D / 1.8 MHz, so the pulse carries Q = 0.5 x Ipk x (ton + toff) with Ipk = (VIN - VOUT) x ton / L (107 mA and 204 mA for the 2.8 V and 1.4 V rails) and toff = Ipk x L / VOUT; then f = Iload / Q (Q = 29.8 nC and 56.5 nC). The PWM / power-save boundary sits at half the ripple current (54 mA and 102 mA), far above the 5 mA maximum, so these rails are in power-save at every load.
- **LT8330:** the datasheet says the burst current limit is about 240 mA and that the frequency rises with load up to the fixed 2 MHz (its Figure 1 is for a 48 V boost, not this converter). I take the pulse as 240 mA in the switch split equally between the two 2.2 uH inductors, which stores 0.5 x (2.2 + 2.2) uH x (120 mA)^2 = 31.7 nJ per pulse (24.4 nJ delivered at 77 %). The CCM duty uses an assumed diode drop of 0.3 V.
- The duty and frequency of the controller-driven rails are in [controller-rails.md](controller-rails.md) section 8.
