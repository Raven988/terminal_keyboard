"""Встроенные раскладки и их обмен с layout.json."""

import json
import os
import sys

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk  # noqa: E402

from . import config
from .geometry import (ARROW_W, FULL_W, MOD_H, MOD_W, NUM_ROWS,
                       PROG_KEYS, PROG_L_KEYS, PROG_L_W, SPLIT_L_W, SPLIT_R_W,
                       TOP_ROWS, TOUCHPAD_ROWS, TOUCHPAD_W, U)
from .keys import A, C, K, M, P, KeyState, key_from_spec
from .keypad import KeyPad

def build_left(pad):
    """Левая половина: цифровой блок сверху, под ним основная часть.

    Раскол по классическому месту — между T и Y, G и H, B и N. Ширина каждого
    ряда подогнана ровно под SPLIT_L_W.
    """
    E = Gdk
    # цифровой блок, 4 колонки в левом верхнем углу половины
    pad.row([C("7", "7"), C("8", "8"), C("9", "9"), C("/", "/")], 0)
    pad.row([C("4", "4"), C("5", "5"), C("6", "6"), C("*", "*")], 1)
    pad.row([C("1", "1"), C("2", "2"), C("3", "3"), C("-", "-")], 2)
    pad.row([C("0", "0", w=2 * U), C(".", "."), C("+", "+")], 3)

    # Справа от цифрового блока пустовало 13 четвертей на четыре ряда — туда
    # уходит вторая половина программируемых клавиш, по одной на ряд. Они
    # широкие: подпись с именем команды читается целиком.
    for i in range(PROG_L_KEYS):
        pad.add_key(P(PROG_KEYS - PROG_L_KEYS + i, w=PROG_L_W), 4 * U, i)

    r = NUM_ROWS
    pad.row([K("Esc", E.KEY_Escape, w=5),
             K("F1", E.KEY_F1), K("F2", E.KEY_F2), K("F3", E.KEY_F3),
             K("F4", E.KEY_F4), K("F5", E.KEY_F5), K("F6", E.KEY_F6)], r)
    # Цифры с этого ряда убраны — они есть на цифровом блоке. Основными стали
    # символы, цифра осталась под Shift. Сам ряд убрать нельзя: ` ~ ! @ # $ % ^
    # на цифровом блоке отсутствуют, а без них в шелле делать нечего.
    pad.row([C("`", "~", "ё", "Ё", w=5),
             C("!", "1"), C("@", "2", '"', "2"), C("#", "3", "№", "3"),
             C("$", "4", ";", "4"), C("%", "5"),
             C("^", "6", ":", "6")], r + 1)
    pad.row([K("Tab ⇥", E.KEY_Tab, w=9),
             C("q", "Q", "й", "Й"), C("w", "W", "ц", "Ц"), C("e", "E", "у", "У"),
             C("r", "R", "к", "К"), C("t", "T", "е", "Е")], r + 2)
    pad.row([A("Caps", "caps", w=9, css="mod"),
             C("a", "A", "ф", "Ф"), C("s", "S", "ы", "Ы"), C("d", "D", "в", "В"),
             C("f", "F", "а", "А"), C("g", "G", "п", "П")], r + 3)
    pad.row([M("Shift ⇧", "shift", w=9),
             C("z", "Z", "я", "Я"), C("x", "X", "ч", "Ч"), C("c", "C", "с", "С"),
             C("v", "V", "м", "М"), C("b", "B", "и", "И")], r + 4)
    pad.row([M("Ctrl", "ctrl", w=6), M("Super", "super", w=5),
             M("Alt", "alt", w=6), C(" ", " ", " ", " ", w=12)], r + 5)


def build_right(pad, touchpad=None):
    """Правая половина.

    Стрелки — в двух нижних рядах, под большим пальцем. Модификаторы и смена
    языка подняты наверх, на освободившееся место: они нажимаются раз в
    несколько символов, а стрелками в терминале работают постоянно.
    Copy/Paste оставлены здесь — иначе до буфера обмена на планшете не
    добраться.
    """
    E = Gdk
    # Сверху справа: полоса перемотки прижата к самому краю, блок
    # модификаторов — слева от неё. Место под полосу запоминаем на самой
    # сетке: полоса одна на все раскладки и переезжает между ними.
    tx = SPLIT_R_W - TOUCHPAD_W
    mx = tx - 2 * MOD_W
    pad.touchpad_at = (tx, 0, TOUCHPAD_W, TOUCHPAD_ROWS)
    pad.add_key(M("Shift ⇧", "shift", w=MOD_W, h=MOD_H), mx, 0)
    pad.add_key(M("Ctrl", "ctrl", w=MOD_W, h=MOD_H), mx + MOD_W, 0)
    pad.add_key(M("Alt", "alt", w=MOD_W, h=MOD_H), mx, MOD_H)
    pad.add_key(A("RU/EN", "lang", w=MOD_W, h=MOD_H, css="tool"),
                mx + MOD_W, MOD_H)
    if touchpad is not None:
        pad.add_widget(touchpad, tx, 0, TOUCHPAD_W, TOUCHPAD_ROWS)

    # Слева от них свободно 22 четверти на два ряда: навигация и макросы.
    pad.row([K("Home", E.KEY_Home), K("End", E.KEY_End),
             K("PgUp", E.KEY_Page_Up), K("PgDn", E.KEY_Page_Down),
             K("Del", E.KEY_Delete, repeat=True)], 0)
    # Остальные программируемые клавиши — в левой половине: здесь на них места
    # нет, а там пустует зона рядом с цифровым блоком.
    pad.row([P(i) for i in range(PROG_KEYS - PROG_L_KEYS)], 1)

    r = TOP_ROWS
    pad.row([K("F7", E.KEY_F7), K("F8", E.KEY_F8), K("F9", E.KEY_F9),
             K("F10", E.KEY_F10), K("F11", E.KEY_F11), K("F12", E.KEY_F12),
             A("⧉ Copy", "copy", w=5, css="tool"),
             A("📋 Paste", "paste", w=5, css="tool")], r)
    pad.row([C("&", "7", "?", "7"), C("*", "8"), C("(", "9"), C(")", "0"),
             C("-", "_"), C("=", "+"),
             K("⌫", E.KEY_BackSpace, w=10, repeat=True)], r + 1)
    pad.row([C("y", "Y", "н", "Н"), C("u", "U", "г", "Г"), C("i", "I", "ш", "Ш"),
             C("o", "O", "щ", "Щ"), C("p", "P", "з", "З"),
             C("[", "{", "х", "Х"), C("]", "}", "ъ", "Ъ"),
             C("\\", "|", w=6)], r + 2)
    pad.row([C("h", "H", "р", "Р"), C("j", "J", "о", "О"), C("k", "K", "л", "Л"),
             C("l", "L", "д", "Д"), C(";", ":", "ж", "Ж"),
             C("'", '"', "э", "Э"),
             K("Enter ⏎", E.KEY_Return, w=10, css="accent")], r + 3)
    # ↑ стоит ровно над ↓ — привычное «перевёрнутое Т»
    def arrow(label, keyval):
        return K(label, keyval, w=ARROW_W, repeat=True, css="arrow")

    ax = SPLIT_R_W - 3 * ARROW_W
    pad.row([C("n", "N", "т", "Т"), C("m", "M", "ь", "Ь"),
             C(",", "<", "б", "Б"), C(".", ">", "ю", "Ю"),
             C("/", "?", ".", ",")], r + 4)
    pad.add_key(arrow("↑", E.KEY_Up), ax + ARROW_W, r + 4)
    pad.row([C(" ", " ", " ", " ", w=ax)], r + 5)
    pad.row([arrow("←", E.KEY_Left), arrow("↓", E.KEY_Down),
             arrow("→", E.KEY_Right)], r + 5, ax)


def build_full(pad, touchpad=None):
    """Цельная раскладка для портрета: обычная ANSI-клавиатура во всю ширину.

    Здесь, в отличие от половин, основными в цифровом ряду стоят цифры:
    отдельного цифрового блока нет, а под Shift уходят символы — как на
    настоящей клавиатуре. Всё остальное повторяет сплит, чтобы при повороте
    не пришлось переучиваться: те же макросы, Copy/Paste и полоса перемотки.
    """
    E = Gdk
    # Полоса перемотки — в правом верхнем углу, на два служебных ряда. Шириной
    # в одну клавишу, как в сплите: освободившиеся четверти нужны служебному
    # ряду, где теперь лежат все шесть программируемых клавиш.
    tx = FULL_W - TOUCHPAD_W
    pad.touchpad_at = (tx, 0, TOUCHPAD_W, 2)
    if touchpad is not None:
        pad.add_widget(touchpad, *pad.touchpad_at)

    # Программируемые здесь обычной ширины: их восемь, и служебный ряд иначе
    # не сходится. Навигация ужата до трёх четвертей — по ней попадают реже
    # всего, а прокрутка в портрете и так есть на полосе перемотки.
    pad.row([P(i, w=U) for i in range(PROG_KEYS)]
            + [A("⧉ Copy", "copy", w=6, css="tool"),
               A("📋 Paste", "paste", w=6, css="tool"),
               K("Home", E.KEY_Home, w=3), K("End", E.KEY_End, w=3),
               K("PgUp", E.KEY_Page_Up, w=3),
               K("PgDn", E.KEY_Page_Down, w=3)], 0)
    pad.row([K("Esc", E.KEY_Escape, w=8),
             K("F1", E.KEY_F1), K("F2", E.KEY_F2), K("F3", E.KEY_F3),
             K("F4", E.KEY_F4), K("F5", E.KEY_F5), K("F6", E.KEY_F6),
             K("F7", E.KEY_F7), K("F8", E.KEY_F8), K("F9", E.KEY_F9),
             K("F10", E.KEY_F10), K("F11", E.KEY_F11), K("F12", E.KEY_F12)], 1)
    pad.row([C("`", "~", "ё", "Ё"),
             C("1", "!"), C("2", "@", "2", '"'), C("3", "#", "3", "№"),
             C("4", "$", "4", ";"), C("5", "%"), C("6", "^", "6", ":"),
             C("7", "&", "7", "?"), C("8", "*"), C("9", "("), C("0", ")"),
             C("-", "_"), C("=", "+"),
             K("⌫", E.KEY_BackSpace, w=8, repeat=True)], 2)
    pad.row([K("Tab ⇥", E.KEY_Tab, w=6),
             C("q", "Q", "й", "Й"), C("w", "W", "ц", "Ц"), C("e", "E", "у", "У"),
             C("r", "R", "к", "К"), C("t", "T", "е", "Е"),
             C("y", "Y", "н", "Н"), C("u", "U", "г", "Г"), C("i", "I", "ш", "Ш"),
             C("o", "O", "щ", "Щ"), C("p", "P", "з", "З"),
             C("[", "{", "х", "Х"), C("]", "}", "ъ", "Ъ"),
             C("\\", "|", w=6)], 3)
    pad.row([A("Caps", "caps", w=7, css="mod"),
             C("a", "A", "ф", "Ф"), C("s", "S", "ы", "Ы"), C("d", "D", "в", "В"),
             C("f", "F", "а", "А"), C("g", "G", "п", "П"),
             C("h", "H", "р", "Р"), C("j", "J", "о", "О"), C("k", "K", "л", "Л"),
             C("l", "L", "д", "Д"), C(";", ":", "ж", "Ж"),
             C("'", '"', "э", "Э"),
             K("Enter ⏎", E.KEY_Return, w=9, css="accent")], 4)
    pad.row([M("Shift ⇧", "shift", w=9),
             C("z", "Z", "я", "Я"), C("x", "X", "ч", "Ч"), C("c", "C", "с", "С"),
             C("v", "V", "м", "М"), C("b", "B", "и", "И"),
             C("n", "N", "т", "Т"), C("m", "M", "ь", "Ь"),
             C(",", "<", "б", "Б"), C(".", ">", "ю", "Ю"),
             C("/", "?", ".", ","),
             K("↑", E.KEY_Up, repeat=True, css="arrow"),
             K("Del", E.KEY_Delete, w=7, repeat=True)], 5)
    pad.row([M("Ctrl", "ctrl", w=6), M("Super", "super", w=5),
             M("Alt", "alt", w=5), A("RU/EN", "lang", w=6, css="tool"),
             C(" ", " ", " ", " ", w=26),
             K("←", E.KEY_Left, repeat=True, css="arrow"),
             K("↓", E.KEY_Down, repeat=True, css="arrow"),
             K("→", E.KEY_Right, repeat=True, css="arrow")], 6)


# --- раскладка из файла ---------------------------------------------------
# Три встроенные раскладки: как называются в layout.json, чем собираются и
# сколько в них колонок.
BUILTIN_LAYOUTS = {
    "left": (build_left, SPLIT_L_W),
    "right": (build_right, SPLIT_R_W),
    "full": (build_full, FULL_W),
}


def build_layout(pad, which, touchpad=None, spec=None):
    """Собрать раскладку: из файла, если он есть и цел, иначе встроенную.

    Файл — это возможность переставить клавиши, не трогая Python: добавить
    свои, поменять ширины, сделать вторую пару языков. Ошибку в нём не считаем
    поводом остаться без клавиатуры — говорим, что не так, и собираем
    встроенную.
    """
    builder = BUILTIN_LAYOUTS[which][0]
    if spec is None:
        return builder(pad, touchpad) if touchpad is not None else builder(pad)
    try:
        keys = spec["keys"]
        if not isinstance(keys, list) or not keys:
            raise ValueError("нет ни одной клавиши")
        parsed = [key_from_spec(k) for k in keys]
    except (KeyError, TypeError, ValueError) as e:
        print("terkb: раскладка «%s» из %s не годится (%s), беру встроенную"
              % (which, config.LAYOUT_FILE, e), file=sys.stderr)
        return builder(pad, touchpad) if touchpad is not None else builder(pad)

    for key, raw in zip(parsed, keys):
        pad.add_key(key, int(raw.get("x", 0)), int(raw.get("y", 0)))
    at = spec.get("touchpad")
    if isinstance(at, list) and len(at) == 4:
        pad.touchpad_at = tuple(int(v) for v in at)
    if touchpad is not None:
        pad.add_widget(touchpad, *pad.touchpad_at)


def load_layouts():
    """Раскладки из ~/.config/terkb/layout.json. Нет файла — нет и правок."""
    if not os.path.exists(config.LAYOUT_FILE):
        return {}
    try:
        with open(config.LAYOUT_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("в файле должен быть объект")
    except (OSError, ValueError) as e:
        print("terkb: %s не читается (%s), беру встроенные раскладки"
              % (config.LAYOUT_FILE, e), file=sys.stderr)
        return {}
    return {k: v for k, v in data.items() if k in BUILTIN_LAYOUTS}


def dump_layouts(path=None):
    """Записать встроенные раскладки в файл — чтобы было что править.

    Собираем их во временном KeyState: клавишам нужен приёмник ввода, но
    нажимать их никто не собирается.
    """
    path = path or config.LAYOUT_FILE
    state = KeyState(None)
    out = {"note": "правьте и перезапустите; удалите файл — вернутся "
                   "встроенные раскладки",
           "keyval": "имена клавиш GDK: Return, BackSpace, Page_Up, F7, Up"}
    for which, (builder, cols) in BUILTIN_LAYOUTS.items():
        pad = KeyPad(state, cols)
        builder(pad)
        out[which] = {
            "cols": cols,
            "touchpad": list(getattr(pad, "touchpad_at", ())) or None,
            "keys": [k.to_spec() for k in pad.keys],
        }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return path
