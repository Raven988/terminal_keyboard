#!/usr/bin/env python3
"""Вкладки терминалов: открытие, переключение, закрытие.

Окно живёт в offscreen, как в test_input.py: проверяется поведение, а не
картинка — сколько вкладок, куда уходит ввод с экранной клавиатуры, что
остаётся после закрытия и что новая вкладка открывается с тем же оформлением.
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

# Настройки и макросы пишутся в конфиг — тест не трогает настоящий.
_DIR = tempfile.mkdtemp(prefix="terkb-test-")
terkb.config.MACRO_FILE = os.path.join(_DIR, "macros.json")
terkb.config.SETTINGS_FILE = os.path.join(_DIR, "settings.json")
terkb.config.LAYOUT_FILE = os.path.join(_DIR, "layout.json")

W, H = 1500, 950
results = []


def expect(name, cond):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name)


class A(terkb.App):
    def __init__(self):
        Gtk.Application.__init__(self, application_id=None,
                                 flags=Gio.ApplicationFlags.NON_UNIQUE)

    def do_activate(self):
        win = terkb.Window(self)
        root = win.root
        win.remove(root)
        off = Gtk.OffscreenWindow()
        off.add(root)
        off.set_size_request(W, H)
        off.show_all()
        win.place_dividers(W, H)
        self.win, self.off = win, off
        GLib.timeout_add(1500, self.go)

    # -- вспомогательное ----------------------------------------------------
    def pump(self, seconds=0.0):
        deadline = time.monotonic() + seconds
        while True:
            while Gtk.events_pending():
                Gtk.main_iteration()
            if time.monotonic() >= deadline:
                return
            time.sleep(0.02)

    def screen(self, term):
        txt = term.vte.get_text_format(Vte.Format.TEXT)
        return (txt[0] if isinstance(txt, tuple) else txt) or ""

    def wait_for(self, term, needle, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump(0.05)
            if needle in self.screen(term):
                return True
        return False

    def wait_prompt(self, term, timeout=10.0):
        return self.wait_for(term, "$", timeout)

    def wait_tabs(self, count, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump(0.05)
            if len(self.win.tabs.tabs) == count:
                return True
        return False

    def key(self, label):
        for k in self.win.state.all_keys:
            if k.low == label:
                return k
        raise KeyError(label)

    def tap(self, *labels):
        for lb in labels:
            self.win.state.press(self.key(lb))

    def type_line(self, text):
        """Набрать строку на экранной клавиатуре и выполнить её."""
        for ch in text:
            self.tap(ch)
        self.tap("Enter ⏎")

    def go(self):
        try:
            self.run_checks()
        finally:
            self.quit()
        return False

    # -- проверки -----------------------------------------------------------
    def run_checks(self):
        win = self.win

        expect("подпись вкладки — номер и хвост заголовка",
               terkb.short_title("ubuntu@planshet: ~/Документы", 0)
               == "1 ~/Документы")
        expect("без заголовка на вкладке остаётся номер",
               terkb.short_title("", 2) == "№3")

        expect("при запуске одна вкладка", len(win.tabs.tabs) == 1)
        expect("с одной вкладкой полосы нет",
               not win.tabs.strip.get_visible())
        first = win.term
        expect("шелл первой вкладки поднялся", self.wait_prompt(first))

        # ---------- открытие ----------
        kb_before = win.avail_height(W, H)
        win.new_tab()
        self.pump(0.5)
        second = win.term
        expect("вкладок стало две", len(win.tabs.tabs) == 2)
        expect("полоса вкладок появилась", win.tabs.strip.get_visible())
        expect("открыта именно новая вкладка", second is not first)
        expect("новая вкладка с тем же оформлением",
               second.font_family == win.font_family
               and second.font_size == win.font_size)
        expect("клавиатура печатает в открытую вкладку",
               win.state.send is second)
        expect("полоса отъела высоту у клавиатуры",
               win.avail_height(W, H) < kb_before)
        expect("шелл второй вкладки поднялся", self.wait_prompt(second))

        # ---------- ввод идёт в открытую вкладку ----------
        self.type_line("echo two")
        expect("вторая вкладка получила ввод",
               self.wait_for(second, "\ntwo\n"))
        expect("в первую вкладку ввод не попал",
               "two" not in self.screen(first))

        # ---------- переключение ----------
        win.tabs.step(-1)          # то же, что Ctrl+PgUp
        self.pump(0.3)
        expect("соседняя вкладка открылась по кругу", win.term is first)
        expect("ввод переехал вместе с вкладкой", win.state.send is first)
        self.type_line("echo one")
        expect("первая вкладка получила ввод",
               self.wait_for(first, "\none\n"))
        expect("во вторую вкладку ввод не попал",
               "one" not in self.screen(second))
        expect("подпись вкладки не пустая",
               bool(win.tabs.tabs[0].label.get_text()))

        # ---------- оформление общее на все вкладки ----------
        win.zoom_font(1)
        self.pump(0.2)
        expect("размер шрифта сменился во всех вкладках",
               {t.font_size for t in win.tabs.terms} == {win.font_size})
        win.next_scheme()
        self.pump(0.2)
        expect("схема записалась и применилась",
               win.settings["scheme"] == win.scheme["id"])

        # ---------- предел ----------
        while len(win.tabs.tabs) < terkb.MAX_TABS:
            win.new_tab()
            self.pump(0.1)
        expect("вкладок открылось ровно столько, сколько разрешено",
               len(win.tabs.tabs) == terkb.MAX_TABS)
        expect("на пределе кнопка «＋» недоступна",
               not win.new_btn.get_sensitive())
        win.new_tab()
        self.pump(0.1)
        expect("сверх предела вкладка не открывается",
               len(win.tabs.tabs) == terkb.MAX_TABS)
        for term in win.tabs.terms[2:]:
            win.tabs.close(term)
        self.pump(0.3)
        expect("лишние вкладки закрылись", len(win.tabs.tabs) == 2)
        expect("кнопка «＋» снова доступна", win.new_btn.get_sensitive())

        # ---------- закрытие крестиком ----------
        kb_two = win.avail_height(W, H)
        win.tabs.tabs[1].close_btn.clicked()
        self.pump(0.3)
        expect("крестик закрыл вкладку", len(win.tabs.tabs) == 1)
        expect("осталась соседняя вкладка", win.term is first)
        expect("ввод вернулся к оставшейся", win.state.send is first)
        expect("полоса вкладок исчезла", not win.tabs.strip.get_visible())
        expect("высота вернулась клавиатуре", win.avail_height(W, H) > kb_two)
        self.type_line("echo alive")
        expect("оставшаяся вкладка печатает",
               self.wait_for(first, "\nalive\n"))

        # ---------- выход из шелла закрывает вкладку ----------
        win.new_tab()
        self.pump(0.5)
        third = win.term
        expect("шелл третьей вкладки поднялся", self.wait_prompt(third))
        self.type_line("exit")
        expect("выход из шелла закрыл вкладку", self.wait_tabs(1))
        expect("открытой снова стала оставшаяся", win.term is first)

        # ---------- последняя вкладка закрывает окно ----------
        empty = []
        win.tabs.on_empty = lambda: empty.append(True)   # окно не закрываем
        win.close_tab()
        self.pump(0.3)
        expect("закрытие последней вкладки закрывает окно",
               not win.tabs.tabs and empty)


A().run([])
ok = sum(1 for r in results if r)
print("\nИтог: %d/%d прошли" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
