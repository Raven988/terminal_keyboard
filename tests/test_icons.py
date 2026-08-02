#!/usr/bin/env python3
"""Иконка: что её файлы вообще читаются тем загрузчиком, которым их читает
оболочка.

Поломка, ради которой написан тест: gdk-pixbuf узнаёт SVG по первым байтам —
«<svg» или «<!DOCTYPE svg» сразу за необязательной строкой <?xml?>. Комментарий
перед корневым тегом сбивает опознание, и файл считается нечитаемым. Иконка при
этом остаётся на месте и открывается в любом просмотрщике, но док и обзор
рисуют вместо неё чёрный квадрат — как раз там, где оболочке нужен размер, под
который нет готового PNG (44, 56, 96 пикселей).
"""
import os
import sys

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib  # noqa: E402

ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons")
SVG = os.path.join(ICONS, "terkb.svg")
# Размеры, которых нет среди растровых копий: на них оболочка берёт SVG.
ODD_SIZES = (44, 56, 96)
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256)

results = []


def expect(what, ok):
    results.append(ok)
    print(("  ok  " if ok else "ПРОВАЛ") + "  " + what)


for size in ODD_SIZES:
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(SVG, size, size)
        expect("SVG читается в %d пикселей" % size,
               (pb.get_width(), pb.get_height()) == (size, size))
    except GLib.Error as e:
        expect("SVG читается в %d пикселей (%s)" % (size, e.message), False)

for size in PNG_SIZES:
    path = os.path.join(ICONS, "terkb-%d.png" % size)
    if not os.path.exists(path):
        expect("растровая копия %d есть (собирается make-icons.py)" % size,
               False)
        continue
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file(path)
        expect("PNG %d читается и нужного размера" % size,
               (pb.get_width(), pb.get_height()) == (size, size))
    except GLib.Error as e:
        expect("PNG %d читается (%s)" % (size, e.message), False)

ok = sum(1 for r in results if r)
print("\nИтог: %d/%d прошли" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
