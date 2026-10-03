#!/usr/bin/env python3
"""Render the board to out/pcb_*.png (needs pymupdf; run with `py -3.12`)."""
import subprocess, sys
import pymupdf as fitz

K = r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"
layers = sys.argv[1] if len(sys.argv) > 1 else "F.Cu,B.Cu,F.Silkscreen,Edge.Cuts"
name = sys.argv[2] if len(sys.argv) > 2 else "pcb"
subprocess.run([K, "pcb", "export", "pdf", "--layers", layers, "-o", f"out/{name}.pdf", "mini-power/mini-power.kicad_pcb"], check=True, capture_output=True)
d = fitz.open(f"out/{name}.pdf")
p = d[0]
mm = 72 / 25.4
board = fitz.Rect(98 * mm, 48 * mm, 202 * mm, 152 * mm)
p.get_pixmap(dpi=330, clip=board).save(f"out/{name}.png")
# left and right halves for closer inspection
p.get_pixmap(dpi=520, clip=fitz.Rect(98 * mm, 48 * mm, 152 * mm, 152 * mm)).save(f"out/{name}_L.png")
p.get_pixmap(dpi=520, clip=fitz.Rect(148 * mm, 48 * mm, 202 * mm, 152 * mm)).save(f"out/{name}_R.png")
print("ok")
