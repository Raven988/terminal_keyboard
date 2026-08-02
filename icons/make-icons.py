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

# Корпус светлый и цветной намеренно: тёмно-серый сливался с фоном дока, и
# закреплённый значок выглядел чёрным пятном. Тёмным остаётся только экран
# терминала — по нему иконка и узнаётся.
BODY_TOP, BODY_BOTTOM = "#7d6cf2", "#4a37c8"
SCREEN_TOP, SCREEN_BOTTOM = "#181b22", "#0c0e12"
KEY_COLOR, KEY_ALPHA = "#ffffff", 0.55
PROMPT = "#50fa7b"      # приглашение, курсор и клавиша Enter
TEXT_ALPHA = 0.45       # строки вывода на экране


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

    body = cairo.LinearGradient(0, 6, 0, 122)
    body.add_color_stop_rgb(0, *rgb(BODY_TOP))
    body.add_color_stop_rgb(1, *rgb(BODY_BOTTOM))
    rounded(cr, 6, 6, 116, 116, 26)
    cr.set_source(body)
    cr.fill()

    screen = cairo.LinearGradient(0, 22, 0, 106)
    screen.add_color_stop_rgb(0, *rgb(SCREEN_TOP))
    screen.add_color_stop_rgb(1, *rgb(SCREEN_BOTTOM))
    rounded(cr, 47, 22, 34, 84, 6)
    cr.set_source(screen)
    cr.fill()

    # приглашение и курсор — на мелких размерах крупнее и по центру экрана
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_source_rgb(*rgb(PROMPT))
    if detail:
        cr.set_line_width(5)
        cr.move_to(54, 38)
        cr.line_to(61, 45)
        cr.line_to(54, 52)
        cr.stroke()
        rounded(cr, 64, 41, 11, 5, 2.5)
        cr.fill()
        cr.set_source_rgba(*rgb("#ffffff"), TEXT_ALPHA)
        for y, w in ((60, 20), (71, 14), (82, 17), (93, 10)):
            rounded(cr, 54, y, w, 4.5, 2.25)
            cr.fill()
    else:
        cr.set_line_width(8)
        cr.move_to(54, 48)
        cr.line_to(64, 60)
        cr.line_to(54, 72)
        cr.stroke()
        rounded(cr, 54, 80, 22, 8, 4)
        cr.fill()

    # половины клавиатуры
    cr.set_source_rgba(*rgb(KEY_COLOR), KEY_ALPHA)
    rows = (32, 48, 64, 80, 96) if detail else (32, 58, 84)
    height = 12 if detail else 18
    for y in rows:
        rounded(cr, 14, y, 25, height, 4)
        cr.fill()
    for y in rows[:-1]:
        rounded(cr, 89, y, 25, height, 4)
        cr.fill()
    cr.set_source_rgb(*rgb(PROMPT))        # нижняя правая — Enter
    rounded(cr, 89, rows[-1], 25, height, 4)
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
