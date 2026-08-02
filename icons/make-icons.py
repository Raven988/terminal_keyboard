#!/usr/bin/env python3
"""Растровые копии иконки: icons/terkb-<размер>.png.

SVG-загрузчик gdk-pixbuf стоит не в каждой системе, и без растровых копий
иконка в меню молча не показывается. Рисунок здесь тот же, что в terkb.svg,
только на cairo — держать две картинки врозь нельзя, поэтому при правке одной
правится и вторая.

    python3 icons/make-icons.py
"""
import os
import sys

import cairo

SIZES = (16, 24, 32, 48, 64, 128, 256)
HERE = os.path.dirname(os.path.abspath(__file__))


def rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -1.5708, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
    cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
    cr.arc(x + r, y + r, r, 3.1416, 4.7124)
    cr.close_path()


def rgb(color):
    return tuple(int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def draw(cr, size):
    """Рисунок в координатах 128×128, дальше масштабируется.

    Начиная с 48 пикселей рисуем всё; ниже — только силуэт: строки вывода и
    пять клавиш на половину там сливаются в грязь, а узнают иконку всё равно
    по паре «полосы клавиш — тёмное окно с приглашением».
    """
    cr.scale(size / 128.0, size / 128.0)
    detail = size >= 48

    # корпус с вертикальным градиентом, как в svg
    body = cairo.LinearGradient(0, 10, 0, 118)
    body.add_color_stop_rgb(0, *rgb("#3a3f4e"))
    body.add_color_stop_rgb(1, *rgb("#272b36"))
    rounded(cr, 4, 10, 120, 108, 16)
    cr.set_source(body)
    cr.fill_preserve()
    # светлый кант: без него на тёмном фоне иконка сливается в пятно
    cr.set_source_rgb(*rgb("#79839a"))
    cr.set_line_width(3)
    cr.stroke()

    # экран терминала
    glass = cairo.LinearGradient(0, 20, 0, 108)
    glass.add_color_stop_rgb(0, *rgb("#15171d"))
    glass.add_color_stop_rgb(1, *rgb("#0d0f13"))
    rounded(cr, 45, 20, 38, 88, 5)
    cr.set_source(glass)
    cr.fill()

    # приглашение и курсор — единственная яркая деталь, поэтому на мелких
    # размерах они крупнее и стоят по центру экрана
    cr.set_source_rgb(*rgb("#50fa7b"))
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    if detail:
        cr.set_line_width(4.5)
        cr.move_to(53, 36)
        cr.line_to(60, 42)
        cr.line_to(53, 48)
        cr.stroke()
        rounded(cr, 64, 38, 12, 5, 2.5)
        cr.fill()
        cr.set_source_rgb(*rgb("#6a7385"))
        for y, w in ((54, 23), (65, 16), (76, 20), (87, 11)):
            rounded(cr, 53, y, w, 4.5, 2.25)
            cr.fill()
    else:
        cr.set_line_width(7)
        cr.move_to(53, 50)
        cr.line_to(63, 62)
        cr.line_to(53, 74)
        cr.stroke()
        rounded(cr, 53, 82, 24, 7, 3.5)
        cr.fill()

    # половины клавиатуры
    cr.set_source_rgb(*rgb("#8d97ad") if not detail else rgb("#596376"))
    rows = (30, 46, 62, 78, 94) if detail else (30, 56, 82)
    height = 12 if detail else 18
    for y in rows:
        rounded(cr, 12, y, 24, height, 3.5)
        cr.fill()
    for y in rows[:-1]:
        rounded(cr, 92, y, 24, height, 3.5)
        cr.fill()
    cr.set_source_rgb(*rgb("#7c6cf0"))     # нижняя правая — Enter
    rounded(cr, 92, rows[-1], 24, height, 3.5)
    cr.fill()


def main():
    for size in SIZES:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        draw(cairo.Context(surface), size)
        path = os.path.join(HERE, "terkb-%d.png" % size)
        surface.write_to_png(path)
        print("записано:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
