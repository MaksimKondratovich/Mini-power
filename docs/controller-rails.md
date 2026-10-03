# Controller-driven rails (+1.375 V and -2.75 V) from +2.75 V

Status: **drawn in the schematic (blocks D, E-A, E-B on the right-hand side); the controller itself is an interface header (J5).** Nominal values only.
Model: [tools/controller_rails_model.py](../tools/controller_rails_model.py) (run it to reproduce every number below).

## 1. What was asked (and how I read it)
- A second set of the +1.4 V and -2.8 V rails, produced with the help of a low-power STM32 (exact part not chosen).
- The controller and the power stages are powered from a **+2.75 V input that is provided separately** (my reading: a new input header, not the on-board +2.8 V rail). Output targets follow the 2.75 V supply: **+1.375 V** and **-2.75 V**.
- Buck: drive the inductor directly from a pin. Inverting rail: propose something based on an inductor.
- Each output has its own header with a series jumper. Efficiency and compactness come first.
- Outputs left unregulated: calculate the swing for 10 % to 200 % of the 1 mA typical load (0.1 mA, 1 mA, 2 mA).

## 2. Assumptions (the controller is abstract, so these are parameters)
| Parameter | Value | Note |
|---|---|---|
| Supply | 2.75 V | separate input |
| GPIO output resistance | 40 ohm high side, 40 ohm low side | assumed; real STM32 families range roughly 25 to 60 ohm at 2.75 V |
| Capacitance switched every cycle | 10 pF per pin | pad, inductor winding, wiring |
| MCU current with the timer running | 20 uA | assumed; reported separately because the controller exists in your system anyway |
| Pin current | keep within +/-8 mA | typical sustained STM32 pin limit; check the chosen part |
| Inductor loss | DCR only | core loss ignored (ripple is small) |

## 3. +1.375 V buck, one pin drives the inductor
Topology: a single push-pull pin drives the inductor (pin high = supply, pin low = ground); the other inductor end is the output with a capacitor to GND.
The pin both sources and sinks current, so the inductor current can reverse. The converter therefore stays in **forced continuous conduction at any load**, and the output is stiff: Vout = D x Vdd minus the pin and DCR drops. This is what keeps an unregulated output usable.

Why not a diode as the low side? Without the low-side pin the stage drops into discontinuous mode at light load, and with fixed duty the output rises toward the supply voltage as the load falls (it behaves as a constant-power source). Forced continuous conduction with the second pin state avoids that.

### 3.1 Design equations (nominal)
- Duty for the target: D x 2.75 V - Iload x (R_pin + DCR) = 1.375 V. At 1 mA with R_pin = 40 ohm and DCR = 4 ohm the drop is 44 mV, so **D = 0.516** (not 0.5).
- Ripple: dI(p-p) = Vdd x D x (1 - D) / (L x f) = 0.6875 V / (L x f) (the model uses the exact RL solution).
- Loss: conduction = (I_load^2 + dI^2 / 12) x (R_pin + DCR); pin capacitance = Cpin x Vdd^2 x f. Core loss ignored.
- The ripple term does not depend on load, so it dominates at light load. Only L x f can reduce it, so the inductance and frequency must both be large.

### 3.2 Inductor choice (compact 0805, all extended)
| Candidate | LCSC | Value | DCR | Rated current |
|---|---|---|---|---|
| LBR2012T101M | C223273 | 100 uH | 4 ohm | 50 mA |
| LB2012T470M | C223254 | 47 uH | 3.7 ohm | 60 mA |
The 2.2 uH inductor used by the IC rails cannot be used here: its time constant (2.2 uH / 44 ohm = 50 ns) is far shorter than a 1 MHz period, so the current would only be limited by the pin resistance, 1.375 V / 44 ohm = 31 mA, far beyond a pin's limit.

### 3.3 Results, D fixed at 0.516, loads 0.1 / 1 / 2 mA
| L, f | Vout at 0.1 / 1 / 2 mA | ripple p-p | pin current range at 2 mA | efficiency at 0.1 / 1 / 2 mA (converter only) |
|---|---|---|---|---|
| 47 uH, 1 MHz | 1.414 / 1.375 / 1.331 V | 14.3 mA | -5.2 to 9.1 mA | 14 / 61 / 72 % |
| 100 uH, 500 kHz | 1.415 / 1.375 / 1.331 V | 13.5 mA | -4.8 to 8.7 mA | 16 / 64 / 75 % |
| 100 uH, 1 MHz | 1.415 / 1.375 / 1.331 V | 6.8 mA | -1.4 to 5.4 mA | 36 / 82 / 86 % |
| **100 uH, 2 MHz** | **1.415 / 1.375 / 1.331 V** | **3.4 mA** | **0.3 to 3.7 mA** | **42 / 85 / 88 %** |
| 47 uH, 2 MHz | 1.414 / 1.375 / 1.331 V | 7.3 mA | -1.6 to 5.6 mA | 29 / 78 / 84 % |

Recommended: **100 uH (C223273) at 2 MHz**.
- **Unregulated swing:** 1.415 V at 0.1 mA, 1.375 V at 1 mA, 1.331 V at 2 mA. That is +2.9 % / -3.2 % around nominal, and it is purely the pin-resistance drop (about 44 ohm x load current).
- **Efficiency:** 85 % at the 1 mA typical load, 88 % at 2 mA, but only 42 % at 0.1 mA, where the fixed loss (ripple current and pin capacitance, about 190 uW) swamps the 0.14 mW output. Including the assumed 20 uA MCU current the figures drop by 2 to 6 points.
- **Comparison:** the IC buck (TPS62841) should be around 90 % at 1 mA and keeps its efficiency at 0.1 mA (low-Iq Burst Mode). The controller-driven stage is the compact, parts-light option, not the most efficient one.
- **Duty resolution:** the duty step is 1 / (timer clock / f). At 2 MHz output from a 32 MHz timer there are only 16 counts, 6.25 % per step, which is 172 mV on the output. Use a faster timer clock or a lower frequency, or dither the duty. This must be solved in the firmware.

## 4. -2.75 V inverting rail: options
A pin can swing only 0 to 2.75 V, so the pin can never touch the negative node or the inductor end that goes negative. Everything below respects that.

| Option | Output at 0.1 / 1 / 2 mA, unregulated | Comment |
|---|---|---|
| **A. Pin-driven charge pump** (flying capacitor, 2 Schottky, output capacitor; no inductor) | -2.43 / -2.23 / -2.11 V | Compact and simple. Efficiency about |Vout| / Vdd = 81 % at 1 mA before pin loss. **Cannot reach -2.75 V**: the best it can do is Vdd - 2 x Vf, about -2.3 V. Swing of 0.32 V (about 14 %) over the load range. |
| **B. Inverting buck-boost: pin gate-drives a P-channel MOSFET (source on the 2.75 V supply), inductor from the switch node to GND, Schottky from the switch node to the -rail** | **unusable open loop** (see below) | This is the inductor-based proposal. The pin only drives the gate, so it never sees a negative voltage or high current. The drain swings to about -2.95 V while the gate stays at 0 to 2.75 V. |
| C. 1:n coupled inductor (your hand-wound 0805 transformer) driven by two pins as a bridge, rectified on the secondary | stiff output, set by the turns ratio and Schottky drop | Reaches -2.75 V with n of about 1.1. Needs a large magnetizing inductance: at a 40 ohm bridge and 1 MHz the magnetizing current loss alone is comparable to the load power. Not recommended unless you can measure the winding. |

### 4.1 Option B unregulated: the problem
With a fixed on-time and fixed frequency the stage runs in discontinuous mode and delivers a fixed power, so it behaves as a constant-power source: Vout = P / Iload. Calibrated to -2.75 V at 1 mA (P = 2.75 mW):
- 0.1 mA load: -27.5 V (the output runs away until something clamps it).
- 1 mA load: -2.75 V.
- 2 mA load: -1.38 V.

So option B **needs the controller to regulate it**: measure the rail (a divider from the -rail to a positive reference gives a positive sense voltage for an ADC or comparator pin) and gate pulses on and off (hysteretic burst control). Estimated cost of that sensing: a few uA.

### 4.2 Option B sizing (first-order, nominal)
- Use the 47 uH inductor (C223254) so the peak current stays under its 60 mA rating: Ipk = 50 mA gives ton = Ipk x L / Vdd = 50 mA x 47 uH / 2.75 V = 0.85 us.
- Energy per pulse: 0.5 x L x Ipk^2 = 59 nJ. At 1 mA and 2.75 V (2.75 mW) that is about 58 kHz average pulse rate, rising to 117 kHz at 2 mA.
- Switch: **Si2301CDS-T1-GE3** (C10487, basic part, 20 V, Vth about 1 V, 142 mohm at Vgs = -2.5 V, Ciss 405 pF, Crss 55 pF). I rejected the AO3401A (Ciss 645 pF) as heavier, and tiny parts such as the BSS84 (about 5 to 10 ohm at 2.75 V) as too resistive for a 50 mA peak.
- Gate charge per pulse: Q = Ciss x Vgs + Crss x Vds_swing = 405 pF x 2.75 V + 55 pF x 5.7 V = 1.4 nC, so the gate energy is 1.4 nC x 2.75 V = 3.9 nJ per pulse, 6.6 % of the 59 nJ pulse.
- Diode loss: 0.2 V / 2.95 V = 7 %. Conduction: (Ipk^2 / 3) x (0.14 + 3.7 ohm) x (ton + toff) = (0.05^2 / 3) x 3.84 x 1.65 us = 5.3 nJ, 9 % of the pulse. Sense amplifier: about 0.9 uA, 2.5 uW (0.09 % of the 2.75 mW at 1 mA).
- Estimated efficiency: about 77 % at 1 mA (100 % - 7 - 6.6 - 9 - 0.1) **if** the burst loop works; core loss is ignored. This is a first-order estimate, not a measured or datasheet figure.

## 5. Recommendation
1. **+1.375 V:** pin-driven buck with the 100 uH inductor at 2 MHz (section 3.3). Swing +2.9 % / -3.2 % unregulated.
2. **-2.75 V:** option B (P-FET + inductor + Schottky) regulated by the controller in burst mode. If you prefer no regulation and accept -2.1 to -2.4 V, option A is the simplest.
3. Optionally close the loop on the buck too (the controller reads the output and skips pulses): that would lift the 0.1 mA efficiency a lot.

## 6. Open points (need your decision)
1. Is the +2.75 V a new, separate input header (J3: +2.75 V and GND)?
2. Option A and option B are both on the board, each with its own series jumper (JP5 = A, JP6 = B; fit only one).
3. Are the assumed GPIO resistance (40 ohm), the 20 uA MCU current and the 10 pF pin capacitance acceptable until a part is chosen?
4. Output headers: the new -2.75 V and +1.375 V need their own header with series jumpers (two more outputs).

## 7. What is in the schematic
- **J3** (+2.75 V in), **J5** (6-pin controller interface: +2.75 V, GND, BUCK_DRV, A_DRV, B_DRV, SENSE), **J4** (outputs: GND, +1.375 V, -2.75 V).
- **Block D:** L5 100 uH (C223273), C10 4.7 uF (output ripple 3.4 mA / (8 x 2 MHz x 4.7 uF) = 0.05 mV, so the capacitor only sets the load-step behaviour), series jumper **JP4**.
- **Block E-A (option A):** C11 1 uF flying capacitor, D2 and D3 PMEG6010CEJ (C406049), C12 4.7 uF output capacitor. Charge pump frequency is set by the controller; at 500 kHz the 1 uF flying capacitor adds only 1 / (f x C) = 2 ohm to the output resistance.
- **Block E-B (option B):** Q1, L6 47 uH (C223254), D4 PMEG6010CEJ, C13 4.7 uF, gate pull-up R5 1 Mohm (keeps Q1 off while the controller is in reset; costs 2.75 uA only while the pin is low), and the **sense amplifier** below.
- **Sense amplifier (U4, LPV521, C779403, extended):** the first sense circuit was a 3 Mohm resistor divider, which the controller cannot read (about 600 kohm source impedance against an ADC sampling capacitor, plus leakage). It is replaced by a nanopower **inverting amplifier** with a low-impedance output.
  - Gain: SENSE = -(R7 / R6) x V_RAIL = -(2.49 M / 4.99 M) x (-2.75 V) = **+1.372 V**. Full scale (SENSE = 2.75 V) is a rail of -5.51 V, so the whole range is readable.
  - The non-inverting input is at GND, which the LPV521 allows (input range from V- minus 0.1 V to V+ plus 0.1 V). It runs from +2.75 V and GND.
  - Current: op-amp 0.35 uA (typical 345 to 400 nA, datasheet) plus the input resistor current 2.75 V / 4.99 M = 0.55 uA, so about 0.9 uA, or 2.5 uW (0.09 % of 2.75 mW).
  - Error: offset +/-1 mV x noise gain 1.5 = +/-1.5 mV at the output, about +/-3 mV (0.1 %) referred to the rail; the 1 % resistors give up to +/-1.4 % gain error (about 38 mV at -2.75 V), which the firmware can calibrate. Input bias is 0.04 pA, so the megohm resistors add no offset.
  - Bandwidth and stability: GBW 6.2 kHz, noise gain 1.5, so the closed-loop bandwidth is about 4 kHz (time constant about 40 us). The 10 pF C0G capacitor C15 across R7 gives a pole at 1 / (2 pi x 2.49 M x 10 pF) = 6.4 kHz and exceeds the minimum sqrt(Cin / (2 pi x R7 x GBW)) = 8 pF needed against about 6 pF of input and stray capacitance. C14 (100 nF) decouples the supply.
  - Loading: the datasheet allows up to 20 pF at the output without an isolation resistor. Keep SENSE short, use a long ADC sampling time, or feed an STM32 comparator input (no sampling capacitor) for the burst loop. A larger output capacitor would slow the loop: the rail moves 0.21 V per ms at 1 mA with 4.7 uF.
- **JP5** (option A) and **JP6** (option B) are separate series current-measurement jumpers between each stage and the -2.75 V output net, which goes to **J4**. Fit only one of them: with both fitted the two converters would drive the same rail against each other. Leave the unused stage undriven (its controller pin idle).
- Net `SW_PB` is the option-B switch node (the IC buck B already uses `SW_B`). Every net has exactly one test point (29 nets in total).
