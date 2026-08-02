#!/usr/bin/env python3
"""Поиск по выводу в НАСТОЯЩЕМ окне.

Отдельно от test_input.py, потому что открывает окно на экране: в offscreen
VTE находит совпадение, но не выделяет его и не прокручивает к нему —
проверять там было бы нечего.
"""
import sys
import os
import time
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import gi
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gtk, GLib, Gio, Vte
import terkb

_DIR = tempfile.mkdtemp(prefix="terkb-test-")
terkb.config.MACRO_FILE = os.path.join(_DIR, "macros.json")
terkb.config.SETTINGS_FILE = os.path.join(_DIR, "settings.json")
terkb.config.LAYOUT_FILE = os.path.join(_DIR, "layout.json")

# Метка уезжает далеко вверх: важно, что поиск достаёт её из прокрутки, а не
# находит на видимом экране.
LINES = 200
MARK = "МЕТКА-ПОИСКА"
results = []


def expect(name, cond):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name)


class A(terkb.App):
    def __init__(self):
        Gtk.Application.__init__(self, application_id=None,
                                 flags=Gio.ApplicationFlags.NON_UNIQUE)

    def do_activate(self):
        self.win = terkb.Window(self)
        self.win.set_default_size(1200, 800)
        self.win.show_all()
        GLib.timeout_add(2500, self.go)

    def pump(self, seconds=0.0):
        """Прокрутить главный цикл. Прокрутка к совпадению приходит не сразу:
        VTE двигает adjustment уже после возврата из search_find_*."""
        deadline = time.monotonic() + seconds
        while True:
            while Gtk.events_pending():
                Gtk.main_iteration()
            if time.monotonic() >= deadline:
                return
            time.sleep(0.05)

    def screen(self):
        txt = self.win.term.vte.get_text_format(Vte.Format.TEXT)
        return (txt[0] if isinstance(txt, tuple) else txt) or ""

    def wait_for(self, needle, timeout=15.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump(0.05)
            if needle in self.screen():
                return True
        return False

    def selection(self):
        v = self.win.term.vte
        if not v.get_has_selection():
            return ""
        txt = v.get_text_selected(Vte.Format.TEXT)
        return (txt[0] if isinstance(txt, tuple) else txt) or ""

    def go(self):
        try:
            self.run_checks()
        finally:
            self.quit()
        return False

    def run_checks(self):
        win = self.win
        v = win.term.vte
        adj = v.get_vadjustment()

        expect("шелл поднялся", self.wait_for("$"))
        win.term.raw(("clear; echo %s; for i in $(seq 1 %d); do echo "
                      "\"строка $i\"; done\n" % (MARK, LINES)).encode())
        expect("длинный вывод получен", self.wait_for("строка %d" % LINES))

        self.pump(0.5)
        bottom = adj.get_value()
        expect("метка уехала за пределы экрана", MARK not in self.screen())

        win.search_btn.set_active(True)
        self.pump(0.2)
        win.search_entry.set_text(MARK)
        self.pump(0.2)
        found = v.search_find_previous()
        self.pump(1.0)
        expect("совпадение найдено", found)
        expect("выделена именно метка", MARK in self.selection())
        expect("вывод прокручен к метке", adj.get_value() < bottom)
        expect("метка видна на экране", MARK in self.screen())

        # Больше метки в выводе нет: следующий поиск вверх ничего не даёт,
        # а с перемоткой по кругу совпадение находится снова.
        expect("выше совпадений больше нет", not v.search_find_previous())
        self.pump(0.3)
        expect("поиск вниз возвращается к метке по кругу",
               v.search_find_next())

        # Запрос ищется как текст, а не как регулярное выражение.
        win.search_entry.set_text("строка 1$")
        self.pump(0.3)
        expect("спецсимволы ищутся буквально",
               not v.search_find_previous())

        win.search_close()
        self.pump(0.2)
        expect("после закрытия ввод снова у терминала",
               win.state.send is win.term
               and v.search_get_regex() is None)


A().run([])
ok = sum(1 for r in results if r)
print("\nИтог: %d/%d прошли" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
