#!/usr/bin/env python3
"""Многократное переключение режима наложения в НАСТОЯЩЕМ окне.

Отдельно от test_input.py, потому что открывает окно на экране. Offscreen-окно
здесь бесполезно: оно раскладывается с первой попытки, а поломка возникала
именно там, где GTK сходится не сразу.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import gi
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gtk, GLib, Gio
import terkb
import tempfile

# Настройки внешнего вида пишутся в конфиг — тест не трогает настоящий.
terkb.SETTINGS_FILE = os.path.join(
    tempfile.mkdtemp(prefix="terkb-test-"), "settings.json")

ROUNDS = 8
bad = []


class A(terkb.App):
    def __init__(self):
        Gtk.Application.__init__(self, application_id=None,
                                 flags=Gio.ApplicationFlags.NON_UNIQUE)

    def do_activate(self):
        win = terkb.Window(self)
        win.set_default_size(1400, 900)
        win.show_all()
        self.win, self.i, self.seen = win, 0, {}
        GLib.timeout_add(1500, self.tick)

    def tick(self):
        if self.i:
            self.win.ghost_btn.set_active(not self.win.ghost)
        GLib.timeout_add(700, self.check)
        return False

    def check(self):
        w = self.win
        lb = w.left_box.get_allocation()
        rb = w.right_box.get_allocation()
        kl = w.pad_left.get_allocation().width / terkb.SPLIT_L_W
        kr = w.pad_right.get_allocation().width / terkb.SPLIT_R_W
        mode = "поверх" if w.ghost else "обычный"
        ok = True
        if lb.width < 100 or rb.width < 100:
            bad.append("%d: половина схлопнулась (%dx%d, %dx%d)"
                       % (self.i, lb.width, lb.height, rb.width, rb.height))
            ok = False
        if abs(kl - kr) >= 1.0:
            bad.append("%d: клавиши разъехались (%.1f и %.1f)"
                       % (self.i, kl * 4, kr * 4))
            ok = False
        # размеры одного и того же режима должны повторяться
        prev = self.seen.get(mode)
        cur = (lb.width, lb.height, rb.width, rb.height)
        if prev is not None and prev != cur:
            bad.append("%d: размеры режима «%s» изменились: %s -> %s"
                       % (self.i, mode, prev, cur))
            ok = False
        self.seen[mode] = cur
        print("%2d %-7s left %4dx%-4d right %4dx%-4d клавиша %.1f/%.1f  %s"
              % (self.i, mode, lb.width, lb.height, rb.width, rb.height,
                 kl * 4, kr * 4, "ok" if ok else "СБОЙ"))
        self.i += 1
        if self.i > ROUNDS:
            self.quit()
            return False
        GLib.timeout_add(300, self.tick)
        return False


A().run([])
print("\nИтог: %s" % ("все %d переключений прошли" % ROUNDS if not bad
                      else "СБОЕВ %d" % len(bad)))
for b in bad:
    print("  " + b)
sys.exit(1 if bad else 0)
