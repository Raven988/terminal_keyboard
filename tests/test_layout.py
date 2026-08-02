#!/usr/bin/env python3
"""Раскладки из layout.json: круг «выгрузить — загрузить», применение правок
и устойчивость к мусору в файле.

Терминал здесь не нужен, окно на экран не выводится — проверяется только то,
что получилось в сетках клавиш.
"""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import gi
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gtk, Gio
import terkb

_DIR = tempfile.mkdtemp(prefix="terkb-test-")
terkb.MACRO_FILE = os.path.join(_DIR, "macros.json")
terkb.SETTINGS_FILE = os.path.join(_DIR, "settings.json")
terkb.LAYOUT_FILE = os.path.join(_DIR, "layout.json")

results = []


def expect(name, cond):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name)


def places(win):
    """Что где лежит в каждой раскладке — по этому и сравниваем."""
    return {name: sorted((k.low, k.x, k.y, k.w, k.h, k.kind) for k in pad.keys)
            for name, pad in (("left", win.pad_left),
                              ("right", win.pad_right),
                              ("full", win.pad_full))}


def edit(fn):
    """Прочитать layout.json, дать функции его поправить, записать обратно."""
    with open(terkb.LAYOUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    fn(data)
    with open(terkb.LAYOUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


class A(terkb.App):
    def __init__(self):
        Gtk.Application.__init__(self, application_id=None,
                                 flags=Gio.ApplicationFlags.NON_UNIQUE)

    def build(self):
        """Окно с текущим layout.json. Из окна нужны только сетки клавиш,
        поэтому дерево виджетов сразу отцепляем."""
        win = terkb.Window(self)
        win.remove(win.root)
        return win

    def do_activate(self):
        builtin = places(self.build())
        expect("встроенные раскладки собраны",
               all(len(v) > 20 for v in builtin.values()))

        # 1. Круг: выгрузили встроенные, подняли окно — раскладка та же.
        terkb.dump_layouts()
        expect("файл раскладок создан", os.path.exists(terkb.LAYOUT_FILE))
        expect("выгрузка и загрузка ничего не теряют",
               places(self.build()) == builtin)

        # 2. Правка файла доезжает до клавиатуры.
        edit(lambda d: d["full"]["keys"].append(
            {"kind": "key", "low": "Своя", "keyval": "F5", "x": 0, "y": 6,
             "w": 4, "css": "special"}))
        win = self.build()
        expect("дописанная клавиша появилась",
               any(k.low == "Своя" for k in win.pad_full.keys))

        # 3. Место полосы перемотки тоже берётся из файла.
        edit(lambda d: d["right"].__setitem__("touchpad", [10, 1, 4, 2]))
        expect("полоса перемотки встала, куда указано",
               self.build().pad_right.touchpad_at == (10, 1, 4, 2))

        # 4. Мусор вместо файла — работаем на встроенных.
        with open(terkb.LAYOUT_FILE, "w", encoding="utf-8") as f:
            f.write("{это не json")
        expect("битый файл не оставляет без клавиатуры",
               places(self.build()) == builtin)

        # 5. Ошибка в одной раскладке не утаскивает остальные.
        terkb.dump_layouts()
        edit(lambda d: d["right"]["keys"].__setitem__(
            0, {"kind": "чепуха", "low": "?"}))
        got = places(self.build())
        expect("сломанная раскладка откатилась на встроенную",
               got["right"] == builtin["right"])
        expect("соседние раскладки не пострадали",
               got["full"] == builtin["full"] and got["left"] == builtin["left"])

        # 6. Понятные ошибки в отдельных клавишах.
        for spec, why in (
                ({"kind": "key", "low": "X"}, "клавише нужен keyval"),
                ({"kind": "key", "low": "X", "keyval": "Нетакой"},
                 "нет такой клавиши GDK"),
                ({"kind": "mod", "low": "X", "name": "чужой"},
                 "неизвестный модификатор"),
                ({"kind": "macro", "low": "X", "data": 99},
                 "макрос вне диапазона"),
                ("не словарь", "клавиша не объект")):
            try:
                terkb.key_from_spec(spec)
                expect("отвергается: " + why, False)
            except ValueError:
                expect("отвергается: " + why, True)

        expect("годная клавиша собирается",
               terkb.key_from_spec(
                   {"kind": "char", "low": "ф", "high": "Ф",
                    "ru": ["ф", "Ф"], "w": 4}).low == "ф")
        self.quit()


A().run([])
ok = sum(1 for r in results if r)
print("\nИтог: %d/%d прошли" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
