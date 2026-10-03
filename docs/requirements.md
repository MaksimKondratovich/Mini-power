# Mini-power: system requirements

## Function
Power supply board. Input +3.3 V, three output rails.

## Electrical
| Item | Requirement |
|---|---|
| Input | +3.3 V |
| Output 1 | +2.75 V |
| Output 2 | -2.75 V |
| Output 3 | +1.375 V |
| Accuracy / ripple / noise | No limits |
| Grounding | All rails referenced to one common ground |
| Load current per rail | 5 mA maximum, 1 mA typical |
| Priority | Efficiency above all (especially at the 1 mA typical load) |

## Mechanical / interface
- PCB max size 100 x 100 mm.
- Input and outputs via male 2.54 mm headers.
- Each output rail has a 2.54 mm header in series, for current measurement or a jumper short.
- Every net has one test point: bare copper dot, 0.5 mm diameter, no solder mask.

## Design rules
- ICs: anything available on the whole market. Parts must be in the JLCPCB library: basic preferred, extended allowed (see CLAUDE.md).
- Resistors 1% or better; no class 3 capacitors.
- Nominal-value calculations only, documented per circuit block in `docs/`.
- Schematics must be drawn in a human-readable way.
