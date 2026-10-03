#!/usr/bin/env python3
"""Replace one symbol in a KiCad symbol library with the same-named symbol from another library.

Usage: merge_symbol.py <target.kicad_sym> <source.kicad_sym> <symbol name>
Used after `kicad-cli sym upgrade` of a temporary one-symbol library.
"""
import sys


def block(text, name):
    i = text.index('(symbol "%s"' % name)
    depth = 0
    in_str = False
    j = i
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


target, source, name = sys.argv[1:4]
t = open(target, encoding="utf-8").read()
s = open(source, encoding="utf-8").read()
t = t.replace(block(t, name), block(s, name), 1)
open(target, "w", encoding="utf-8").write(t)
print("merged", name)
