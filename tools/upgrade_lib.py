#!/usr/bin/env python3
"""Bring freshly imported easyeda2kicad symbols in mini-power/lib/mp.kicad_sym up to KiCad 9 format.

easyeda2kicad appends legacy-format symbols (with "(id N)" properties) to the library. This script
takes each legacy symbol, runs `kicad-cli sym upgrade` on a temporary one-symbol library, sets the
pin electrical types, and replaces the legacy block in mp.kicad_sym.

Pin types: pins named GND/VIN are power_in; MODE/EN/STOP/EN/UVLO/FBX are input; the rest passive.
Usage: python tools/upgrade_lib.py
"""
import re
import subprocess
import tempfile
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "mini-power" / "lib" / "mp.kicad_sym"
KICAD_CLI = r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"


def top_level_symbols(text):
    """Yield (name, start, end) for each top-level (symbol "..." ...) block."""
    depth = 0
    in_str = False
    i = 0
    start = None
    out = []
    while i < len(text):
        c = text[i]
        if c == '"' and text[i - 1] != "\\":
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
                if depth == 2 and text.startswith("(symbol", i):
                    start = i
            elif c == ")":
                if depth == 2 and start is not None:
                    name = re.match(r'\(symbol\s+"([^"]*)"', text[start:]).group(1)
                    out.append((name, start, i + 1))
                    start = None
                depth -= 1
        i += 1
    return out


def set_pin_types(block):
    def sub(m):
        name = m.group(3)
        if name in ("GND", "VIN"):
            typ = "power_in"
        elif name in ("MODE", "EN", "STOP", "EN/UVLO", "FBX"):
            typ = "input"
        else:
            typ = "passive"
        return "(pin %s line%s" % (typ, m.group(2))

    return re.sub(r'\(pin (\w+) line(\s*\(at [^)]*\)\s*\(length [^)]*\)\s*\(name "([^"]*)")', sub, block)


def main():
    text = LIB.read_text(encoding="utf-8")
    legacy = [(n, a, b) for n, a, b in top_level_symbols(text) if "(id " in text[a:b]]
    # symbols already in the current format still need their pin types set
    for name, a, b in reversed([x for x in top_level_symbols(text) if "(pin unspecified" in text[x[1] : x[2]]]):
        text = text[:a] + set_pin_types(text[a:b]) + text[b:]
        print("pin types set for", name)
    if not legacy:
        LIB.write_text(text, encoding="utf-8")
        return
    for name, a, b in reversed(legacy):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "tmp.kicad_sym"
            tmp.write_text(
                "(kicad_symbol_lib\n  (version 20211014)\n  (generator test)\n" + text[a:b] + "\n)\n", encoding="utf-8"
            )
            subprocess.run([KICAD_CLI, "sym", "upgrade", str(tmp)], check=True, capture_output=True)
            new = tmp.read_text(encoding="utf-8")
        sym = next(s for s in top_level_symbols(new) if s[0] == name)
        block = set_pin_types(new[sym[1] : sym[2]])
        text = text[:a] + block + text[b:]
        print("upgraded", name)
    LIB.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
