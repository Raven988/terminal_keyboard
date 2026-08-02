#!/usr/bin/env python3
"""terkb — терминал со сплит-клавиатурой для планшета.

Половины клавиатуры прижаты к краям экрана, терминал между ними: планшет
держат двумя руками и набирают большими пальцами. Над левой половиной —
цифровой блок, над правой — стрелки.

Клавиатура и терминал живут в одном процессе, поэтому ввод отдаётся
VTE-виджету напрямую — без ydotool/uinput и без проблем с инжектом
ввода в Wayland.
"""

import json
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, GLib, Gtk, Pango, Vte  # noqa: E402

APP_ID = "org.terkb.Terminal"

# --- геометрия ------------------------------------------------------------
# Всё считается в «четвертях клавиши»: обычная клавиша = 4, Tab = 6, Shift = 9
# и т.д. — как на настоящей раскладке ANSI.
U = 4

# Ширины половин. Правая шире: на неё приходятся Backspace, Enter и правый
# Shift. Окно делится в той же пропорции, поэтому клавиши в обеих половинах
# получаются одного размера.
SPLIT_L_W = 29
SPLIT_R_W = 34

# Во сколько раз клавише разрешено быть выше своей ширины.
KEY_STRETCH = 1.35

MAIN_ROWS = 6            # F-ряд, символы, qwerty, asdf, zxcv, пробел
NUM_ROWS = 4             # цифровой блок над левой половиной

# Стрелки «перевёрнутым Т» — в двух нижних рядах правой половины, под большим
# пальцем. Полторы обычных ширины каждая.
ARROW_W = 6

# Над правой половиной — блок модификаторов: Shift/Ctrl сверху, Alt/RU-EN под
# ними. Клавиши обычного размера: жмут их редко, а место лучше отдать высоте
# основной части.
MOD_W = U                # ширина клавиши блока в четвертях
MOD_H = 1                # высота в рядах

# Тачпад: узкая полоса рядом с блоком модификаторов — в одну клавишу шириной
# и в две высотой. Только перемотка вверх-вниз.
TOUCHPAD_ROWS = 2
TOUCHPAD_W = U

TOP_ROWS = max(2 * MOD_H, TOUCHPAD_ROWS)

SCROLL_SPEED = 1.0       # во сколько раз прокрутка быстрее движения пальца

# Программируемые клавиши: короткое нажатие выполняет команду, долгое —
# открывает строку правки. Сохраняются между запусками.
PROG_KEYS = 4
PROG_W = 5               # ширина в четвертях
MACRO_FILE = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "terkb", "macros.json")

# Какую долю ширины окна занимают обе половины вместе.
KB_FRACTION = 0.68

# Кнопки ⌨−/⌨+ домножают эту долю. Верхняя граница — чтобы половины не
# сошлись посередине, нижняя — чтобы клавиши не стали неприцельными.
KB_SCALE_STEP = 0.1
KB_SCALE_MIN = 0.6
KB_SCALE_MAX = 1.35

# Сколько ширины окна половины не имеют права занимать суммарно: иначе в режиме
# наложения левая и правая наедут друг на друга.
KB_MAX_TOTAL = 0.94

# Зазор со стороны терминала. Окно-ручка GtkPaned шириной 9 px наезжает на
# крайнюю клавишу, и касание уходило на изменение размера, а не на клавишу:
# подсветка не загоралась. Замер показал перекрытие F7 на 4 px.
HANDLE_GUARD = 24

PANE_PAD = 4 + HANDLE_GUARD   # отступы .kb-pane слева и справа вместе

# Через сколько подсветка нажатия снимается сама, если release не пришёл.
HIT_TIMEOUT_MS = 600

# Плотность клавиш в режиме наложения. Меньше — сильнее просвечивает терминал,
# но хуже читаются подписи: под клавишами идёт текст. Правится на лету
# кнопками ◐−/◐+ в пределах GHOST_ALPHA_MIN..MAX.
GHOST_ALPHA = 0.82
GHOST_ALPHA_STEP = 0.08
GHOST_ALPHA_MIN = 0.30
GHOST_ALPHA_MAX = 1.0


def pad_ratio(cols, rows):
    return cols / (rows * U * KEY_STRETCH)

# --- состояния модификаторов ----------------------------------------------
MOD_OFF, MOD_ONCE, MOD_LOCK = 0, 1, 2


def ctrl_code(ch):
    """ASCII-символ -> управляющий код, как его выдаёт настоящий Ctrl."""
    if not ch:
        return None
    c = ch.upper()
    if "A" <= c <= "Z":
        return bytes([ord(c) - 64])
    return {
        "@": b"\x00", " ": b"\x00", "[": b"\x1b", "\\": b"\x1c",
        "]": b"\x1d", "^": b"\x1e", "_": b"\x1f", "?": b"\x7f",
        "/": b"\x1f", "2": b"\x00", "3": b"\x1b", "4": b"\x1c",
        "5": b"\x1d", "6": b"\x1e", "7": b"\x1f", "8": b"\x7f",
    }.get(c)


class Key:
    """Описание одной клавиши.

    kind:
      char    — печатный символ (low/high — без Shift и с Shift)
      key     — специальная клавиша, задаётся keyval'ом GDK
      mod     — модификатор (Ctrl/Alt/Shift/Super), трёхпозиционный
      raw     — фиксированная последовательность байт
      action  — действие приложения (копировать/вставить/...)
    """

    def __init__(self, kind, low, high=None, keyval=None, w=U, h=1,
                 name=None, data=None, css=None, repeat=False):
        self.kind = kind
        self.low = low
        self.high = high if high is not None else low
        self.keyval = keyval
        self.w = w
        self.h = h
        self.name = name
        self.data = data
        self.css = css
        self.repeat = repeat
        self.button = None
        self.label = None


def C(low, high, ru_low=None, ru_high=None, w=U):
    """Печатная клавиша с латинской и русской раскладкой."""
    k = Key("char", low, high, w=w, repeat=True)
    k.ru = (ru_low if ru_low is not None else low,
            ru_high if ru_high is not None else (ru_low or high))
    return k


def K(label, keyval, w=U, h=1, repeat=False, css="special"):
    return Key("key", label, keyval=keyval, w=w, h=h, repeat=repeat, css=css)


def M(label, name, w=U, h=1):
    return Key("mod", label, name=name, w=w, h=h, css="mod")


def R(label, data, w=U, css="special"):
    return Key("raw", label, data=data, w=w, css=css)


def A(label, name, w=U, h=1, css="special"):
    return Key("action", label, name=name, w=w, h=h, css=css)


def P(index, w=PROG_W):
    """Программируемая клавиша: data — её номер."""
    return Key("macro", "M%d" % (index + 1), w=w, data=index, css="macro")


def load_macros():
    """Команды программируемых клавиш. Битый файл не должен ронять запуск."""
    try:
        with open(MACRO_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            out = [str(x) for x in data[:PROG_KEYS]]
            return out + [""] * (PROG_KEYS - len(out))
    except (OSError, ValueError):
        pass
    return [""] * PROG_KEYS


def save_macros(macros):
    try:
        os.makedirs(os.path.dirname(MACRO_FILE), exist_ok=True)
        with open(MACRO_FILE, "w", encoding="utf-8") as f:
            json.dump(macros, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print("terkb: не удалось сохранить макросы: %s" % e, file=sys.stderr)


class KeyState:
    """Общее состояние обеих половин.

    Половины — разные наборы кнопок, но модификаторы, Caps и язык у них одни:
    нажал Shift слева — подсветились оба Shift и сработало на правой половине.
    """

    def __init__(self, send):
        self.send = send
        self.mods = {"ctrl": MOD_OFF, "alt": MOD_OFF,
                     "shift": MOD_OFF, "super": MOD_OFF}
        self.caps = False
        self.ru = False
        self.all_keys = []
        self.char_keys = []
        self._repeat_id = None
        self.macros = load_macros()
        self.on_macro_edit = None       # ставит окно: открыть строку правки

    # -- автоповтор ---------------------------------------------------------
    def on_press(self, _gesture, _n, _x, _y, key):
        self.press(key)
        self.stop_repeat()
        self._repeat_id = GLib.timeout_add(400, self._start_repeat, key)

    def on_release(self, *_a):
        self.stop_repeat()

    def _start_repeat(self, key):
        self._repeat_id = GLib.timeout_add(45, self._do_repeat, key)
        return False

    def _do_repeat(self, key):
        self.press(key, sticky=True)
        return True

    def stop_repeat(self):
        if self._repeat_id:
            GLib.source_remove(self._repeat_id)
            self._repeat_id = None

    # -- ввод ---------------------------------------------------------------
    def mod_on(self, name):
        return self.mods[name] != MOD_OFF

    def press(self, key, sticky=False):
        if key.kind == "mod":
            self.mods[key.name] = (self.mods[key.name] + 1) % 3
            self.refresh_mods()
            return
        if key.kind == "action":
            self.do_action(key.name)
            return
        if key.kind == "macro":
            cmd = self.macros[key.data]
            if cmd:
                self.send.text(cmd + "\n")
            elif self.on_macro_edit:
                # пустую клавишу логично сразу предложить заполнить
                self.on_macro_edit(key.data)
            return

        ctrl, alt = self.mod_on("ctrl"), self.mod_on("alt")
        shift, sup = self.mod_on("shift"), self.mod_on("super")

        if key.kind == "raw":
            self.send.raw(key.data)
        elif key.kind == "key":
            state = 0
            if ctrl:
                state |= Gdk.ModifierType.CONTROL_MASK
            if alt:
                state |= Gdk.ModifierType.MOD1_MASK
            if shift:
                state |= Gdk.ModifierType.SHIFT_MASK
            if sup:
                state |= Gdk.ModifierType.SUPER_MASK
            keyval = key.keyval
            if keyval == Gdk.KEY_Tab and shift:
                keyval = Gdk.KEY_ISO_Left_Tab
            self.send.keyval(keyval, state)
        else:  # char
            up = shift ^ (self.caps and key.low.isalpha())
            text = self.label_for(key, up)
            if ctrl:
                code = ctrl_code(key.high if shift else key.low)
                if code is None:
                    code = ctrl_code(key.low)
                if code is not None:
                    self.send.raw((b"\x1b" if alt else b"") + code)
                    self._clear_once(sticky)
                    return
            if alt:
                self.send.raw(b"\x1b" + text.encode())
            else:
                self.send.text(text)

        self._clear_once(sticky)

    def _clear_once(self, sticky=False):
        if sticky:
            return
        changed = False
        for name, state in self.mods.items():
            if state == MOD_ONCE:
                self.mods[name] = MOD_OFF
                changed = True
        if changed:
            self.refresh_mods()

    def do_action(self, name):
        if name == "caps":
            self.caps = not self.caps
            self.refresh_mods()
        elif name == "lang":
            self.ru = not self.ru
            self.refresh_labels()
        else:
            self.send.action(name)

    # -- отображение --------------------------------------------------------
    def label_for(self, key, upper):
        if self.ru and hasattr(key, "ru"):
            low, high = key.ru
        else:
            low, high = key.low, key.high
        return high if upper else low

    def set_macro(self, index, cmd):
        self.macros[index] = cmd
        save_macros(self.macros)
        self.refresh_macros()

    def refresh_macros(self):
        for key in self.all_keys:
            if key.kind != "macro":
                continue
            cmd = self.macros[key.data]
            key.label.set_text(cmd if cmd else "M%d" % (key.data + 1))
            key.button.set_tooltip_text(
                cmd if cmd else "Долгое нажатие — задать команду")
            ctx = key.button.get_style_context()
            if cmd:
                ctx.remove_class("kb-macro-empty")
            else:
                ctx.add_class("kb-macro-empty")

    def refresh_labels(self):
        shift = self.mod_on("shift")
        for key in self.char_keys:
            up = shift ^ (self.caps and key.low.isalpha())
            text = self.label_for(key, up)
            key.label.set_text("␣" if text == " " else text)

    def refresh_mods(self):
        # Ctrl/Alt/Shift есть в обеих половинах — красим все сразу.
        for key in self.all_keys:
            if key.kind == "mod":
                state = self.mods[key.name]
            elif key.kind == "action" and key.name == "caps":
                state = MOD_LOCK if self.caps else MOD_OFF
            else:
                continue
            ctx = key.button.get_style_context()
            ctx.remove_class("kb-active")
            ctx.remove_class("kb-locked")
            if state == MOD_ONCE:
                ctx.add_class("kb-active")
            elif state == MOD_LOCK:
                ctx.add_class("kb-locked")
        self.refresh_labels()


_pad_seq = [0]


class KeyPad(Gtk.Grid):
    """Одна половина клавиатуры."""

    def __init__(self, state, cols):
        super().__init__()
        self.state = state
        self.cols = cols
        self.keys = []

        self.set_row_homogeneous(True)
        self.set_column_homogeneous(True)
        # Промежутки делаются CSS-отступом внутри клавиши, а не spacing сетки:
        # при десятках колонок spacing съедал бы заметную долю ширины.
        self.set_row_spacing(0)
        self.set_column_spacing(0)

        # Шрифт пересчитывается под реальный размер клавиш, иначе подписи
        # обрезаются многоточием. Правило скоупится собственным классом:
        # провайдер в GTK3 действует на весь экран, а не на поддерево виджета.
        _pad_seq[0] += 1
        self.css_name = "kb-pad-%d" % _pad_seq[0]
        self.get_style_context().add_class(self.css_name)
        self._font_px = 0
        self._font_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self._font_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.connect("size-allocate", self._on_alloc)

    def _on_alloc(self, _w, alloc):
        key_w = alloc.width / max(1, self.cols) * U
        px = max(7, min(34, round(key_w * 0.36)))
        if px != self._font_px:
            self._font_px = px
            GLib.idle_add(self._apply_font, px)

    def _apply_font(self, px):
        self._font_provider.load_from_data(
            (".%s .kb-key { font-size: %dpx; }\n"
             ".%s .kb-special, .%s .kb-mod, .%s .kb-tool { font-size: %dpx; }\n"
             % (self.css_name, px, self.css_name, self.css_name,
                self.css_name, max(6, int(px * 0.72)))).encode())
        return False

    # -- подсветка нажатия ---------------------------------------------------
    def _on_pressed(self, gesture, n, x, y, key):
        self.state.on_press(gesture, n, x, y, key)

    def _on_released(self, _gesture, _n, _x, _y, _key):
        self.state.on_release()

    def _on_cancel(self, _gesture, _sequence, _key):
        self.state.stop_repeat()

    def _on_long_press(self, _gesture, _x, _y, key):
        if self.state.on_macro_edit:
            self.state.on_macro_edit(key.data)

    def _on_state(self, btn, _old_flags):
        """Подсветку ведём от собственного состояния кнопки.

        Не от нашего жеста: он живёт в фазе CAPTURE, и у клавиш рядом с
        терминалом подсветка не загоралась, хотя нажатие срабатывало. Флаг
        ACTIVE ставит сама GtkButton — та же машинерия, что даёт "clicked",
        поэтому загорается везде, где клавиша вообще нажимается.
        """
        self.hit(btn, bool(btn.get_state_flags() & Gtk.StateFlags.ACTIVE))

    def hit(self, btn, on):
        """Подсветить нажатие.

        Своим классом, а не готовым видом состояния: после касания тачскрина
        виджет нередко остаётся в prelight, и подсветка залипала. Плюс
        страховка по таймауту — если ACTIVE почему-то не снимется, подсветка
        уйдёт сама.
        """
        if getattr(btn, "_hit_id", 0):
            GLib.source_remove(btn._hit_id)
            btn._hit_id = 0
        ctx = btn.get_style_context()
        if on:
            ctx.add_class("kb-hit")
            btn._hit_id = GLib.timeout_add(HIT_TIMEOUT_MS, self._hit_expired, btn)
        else:
            ctx.remove_class("kb-hit")

    def _hit_expired(self, btn):
        btn._hit_id = 0
        btn.get_style_context().remove_class("kb-hit")
        return False

    # -- построение ---------------------------------------------------------
    def add_key(self, key, col, row):
        if key is None:
            return
        btn = Gtk.Button()
        btn.set_can_focus(False)          # фокус остаётся в терминале
        lbl = Gtk.Label(label=key.low)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        # Без этого минимальная ширина длинных подписей раздувает всю
        # однородную сетку, и край клавиатуры уезжает за пределы панели.
        lbl.set_width_chars(1)
        lbl.set_max_width_chars(1)
        btn.set_size_request(1, 1)
        btn.add(lbl)
        btn.get_style_context().add_class("kb-key")
        if key.css:
            btn.get_style_context().add_class("kb-" + key.css)
        key.button, key.label = btn, lbl

        # Подсветка — от состояния самой кнопки, независимо от жестов.
        btn.connect("state-flags-changed", self._on_state)

        if key.kind == "macro":
            lp = Gtk.GestureLongPress.new(btn)
            lp.connect("pressed", self._on_long_press, key)
            key._long_press = lp

        if key.repeat:
            # Автоповтор при удержании. Жест в фазе CAPTURE видит события
            # раньше кнопки, поэтому "clicked" для таких клавиш не подключаем.
            g = Gtk.GestureMultiPress.new(btn)
            g.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            g.connect("pressed", self._on_pressed, key)
            g.connect("released", self._on_released, key)
            g.connect("cancel", self._on_cancel, key)
            key._gesture = g
        else:
            btn.connect("clicked", lambda _b, k=key: self.state.press(k))

        self.attach(btn, col, row, key.w, key.h)
        self.keys.append(key)
        self.state.all_keys.append(key)
        if key.kind == "char":
            self.state.char_keys.append(key)

    def add_widget(self, widget, col, row, w, h):
        """Вставить в сетку не-клавишу (тачпад)."""
        widget.set_size_request(1, 1)
        self.attach(widget, col, row, w, h)

    def row(self, keys, row, x0=0):
        x = x0
        for k in keys:
            if isinstance(k, int):      # число = пустой промежуток
                x += k
                continue
            self.add_key(k, x, row)
            x += k.w

# --- раскладки ------------------------------------------------------------
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


class Touchpad(Gtk.EventBox):
    """Полоса перемотки справа: палец листает терминал вверх-вниз.

    Кликов не шлём: VTE не реагирует на синтетические события указателя —
    они до него доходят, но внутренние жесты требуют настоящего захвата
    устройства от композитора. Прокрутка же идёт мимо событий, прямо через
    vadjustment, и работает всегда.
    """

    def __init__(self, on_drag):
        super().__init__()
        self.set_above_child(True)
        self.get_style_context().add_class("kb-touchpad")
        lbl = Gtk.Label(label="⇕")
        lbl.get_style_context().add_class("kb-touchpad-hint")
        self.add(lbl)

        self._on_drag = on_drag
        self._last = 0.0
        g = Gtk.GestureDrag.new(self)
        g.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        g.connect("drag-begin", self._begin)
        g.connect("drag-update", self._update)
        self._gesture = g

    def _begin(self, _g, _x, _y):
        self._last = 0.0

    def _update(self, _g, _ox, oy):
        dy = oy - self._last
        self._last = oy
        self._on_drag(dy)


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
    # модификаторов — слева от неё.
    tx = SPLIT_R_W - TOUCHPAD_W
    mx = tx - 2 * MOD_W
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
    pad.row([P(i) for i in range(PROG_KEYS)], 1)

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


class EntrySink:
    """Приёмник ввода с экранной клавиатуры вместо терминала.

    Модального диалога тут быть не может: он перекрыл бы клавиатуру, которой
    и надо набирать. Поэтому строка правки встроена в окно, а ввод на это
    время подменяется — интерфейс тот же, что у Terminal.
    """

    def __init__(self, entry, accept, cancel):
        self.entry = entry
        self.accept = accept
        self.cancel = cancel

    def text(self, s):
        pos = self.entry.get_position()
        self.entry.insert_text(s, pos)
        self.entry.set_position(pos + len(s))

    def raw(self, data):
        try:
            s = data.decode("utf-8")
        except UnicodeDecodeError:
            return
        if s.isprintable():
            self.text(s)

    def keyval(self, keyval, _state):
        e = self.entry
        pos = e.get_position()
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.accept()
        elif keyval == Gdk.KEY_Escape:
            self.cancel()
        elif keyval == Gdk.KEY_BackSpace:
            if pos > 0:
                e.delete_text(pos - 1, pos)
                e.set_position(pos - 1)
        elif keyval == Gdk.KEY_Delete:
            e.delete_text(pos, pos + 1)
        elif keyval == Gdk.KEY_Left:
            e.set_position(max(0, pos - 1))
        elif keyval == Gdk.KEY_Right:
            e.set_position(pos + 1)
        elif keyval == Gdk.KEY_Home:
            e.set_position(0)
        elif keyval == Gdk.KEY_End:
            e.set_position(-1)
        elif keyval == Gdk.KEY_Tab:
            self.text("    ")

    def action(self, name):
        if name == "paste":
            clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            txt = clip.wait_for_text()
            if txt:
                self.text(txt)


class Terminal(Gtk.Box):
    """Обёртка над VTE: терминал + вертикальный скроллбар."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.vte = Vte.Terminal()
        self.vte.set_scrollback_lines(50000)
        self.vte.set_mouse_autohide(True)
        self.vte.set_scroll_on_output(False)
        self.vte.set_scroll_on_keystroke(True)
        self.vte.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
        self.font_size = 13
        self.apply_font()

        self.pack_start(self.vte, True, True, 0)
        adj = self.vte.get_vadjustment()
        sb = Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL, adjustment=adj)
        sb.get_style_context().add_class("term-scroll")
        self.pack_start(sb, False, False, 0)

    def apply_font(self):
        self.vte.set_font(Pango.FontDescription("Monospace %d" % self.font_size))

    def zoom(self, delta):
        self.font_size = max(6, min(40, self.font_size + delta))
        self.apply_font()

    def spawn(self, on_exit):
        shell = os.environ.get("SHELL") or "/bin/bash"
        env = ["%s=%s" % (k, v) for k, v in os.environ.items()]
        env = [e for e in env if not e.startswith("COLUMNS=")]
        env.append("TERM=xterm-256color")
        self.vte.connect("child-exited", lambda *_a: on_exit())
        self.vte.spawn_async(
            Vte.PtyFlags.DEFAULT,
            os.path.expanduser("~"),
            [shell, "-l"],
            env,
            GLib.SpawnFlags.DEFAULT,
            None, None,
            -1, None,
            None, None,
        )

    # -- приём ввода от клавиатуры -----------------------------------------
    def text(self, s):
        self.raw(s.encode("utf-8"))

    def raw(self, data):
        try:
            self.vte.feed_child(data)
        except TypeError:
            self.vte.feed_child(data.decode("utf-8", "replace"), len(data))

    def keyval(self, keyval, state):
        """Синтезируем настоящее событие клавиши.

        Так VTE сам выберет правильную последовательность с учётом режима
        приложения (стрелки в vim/less шлют ESC O A, а не ESC [ A).
        """
        window = self.vte.get_window()
        if window is None:
            return
        display = self.vte.get_display()
        keymap = Gdk.Keymap.get_for_display(display)
        ok, entries = keymap.get_entries_for_keyval(keyval)
        keycode = entries[0].keycode if ok and entries else 0
        group = entries[0].group if ok and entries else 0

        for etype in (Gdk.EventType.KEY_PRESS, Gdk.EventType.KEY_RELEASE):
            ev = Gdk.Event.new(etype)
            ev.window = window
            ev.send_event = 1
            ev.time = Gdk.CURRENT_TIME
            ev.state = Gdk.ModifierType(state)
            ev.keyval = keyval
            ev.hardware_keycode = keycode
            ev.group = group
            ev.is_modifier = 0
            self.vte.event(ev)

    def action(self, name):
        if name == "copy":
            if self.vte.get_has_selection():
                self.vte.copy_clipboard_format(Vte.Format.TEXT)
        elif name == "paste":
            self.vte.paste_clipboard()


# Состояния GTK (:hover, :active, :checked) везде перечислены явно. Без этого
# правило темы "button:hover" со специфичностью (0,1,1) перебивает наш
# одноклассовый ".kb-key", а на тачскрине GTK часто не снимает prelight после
# касания: подсветка залипала. Само нажатие показываем своим классом .kb-hit,
# который снимается по отпусканию и по таймауту.
CSS = """
.kb-key, .kb-key:hover, .kb-key:active, .kb-key:checked, .kb-key:focus {
  padding: 0; margin: 1px; min-width: 0; min-height: 0;
  border-radius: 6px;
  background-image: none;
  background-color: @theme_bg_color;
  border: 1px solid alpha(@theme_fg_color, 0.18);
  color: @theme_fg_color;
  text-shadow: none;
}
.kb-special, .kb-special:hover, .kb-special:active,
.kb-mod, .kb-mod:hover, .kb-mod:active {
  background-color: alpha(@theme_fg_color, 0.10);
  font-size: 0.8em;
}
.kb-arrow, .kb-arrow:hover, .kb-arrow:active {
  background-color: alpha(@theme_fg_color, 0.14);
  font-size: 1.2em;
}
.kb-accent, .kb-accent:hover, .kb-accent:active {
  background-color: alpha(@theme_selected_bg_color, 0.45);
}
/* Copy/Paste и RU/EN — такие же, как остальные служебные клавиши: акцентный
   фон читался как «нажато». */
.kb-tool, .kb-tool:hover, .kb-tool:active {
  background-color: alpha(@theme_fg_color, 0.10);
  font-size: 0.8em;
}
.kb-active, .kb-active:hover, .kb-active:active {
  background-color: @theme_selected_bg_color; color: #ffffff;
  border-color: @theme_selected_bg_color;
}
.kb-locked, .kb-locked:hover, .kb-locked:active {
  background-color: #d4801a; color: #ffffff; border-color: #d4801a;
}
.kb-key.kb-hit, .kb-key.kb-hit:hover, .kb-key.kb-hit:active {
  background-color: @theme_selected_bg_color; color: #ffffff;
  border-color: @theme_selected_bg_color;
}
.kb-pane { padding: 4px; }
.kb-macro, .kb-macro:hover, .kb-macro:active {
  background-color: alpha(@theme_fg_color, 0.10);
  font-size: 0.75em;
}
/* незаполненная клавиша не должна выглядеть как рабочая */
.kb-macro-empty, .kb-macro-empty:hover, .kb-macro-empty:active {
  background-color: transparent;
  border-style: dashed;
  color: alpha(@theme_fg_color, 0.45);
}
.kb-editor { padding: 2px 4px; }
.kb-touchpad {
  margin: 1px;
  border-radius: 8px;
  background-color: alpha(@theme_fg_color, 0.07);
  border: 1px dashed alpha(@theme_fg_color, 0.30);
}
.kb-touchpad:active { background-color: alpha(@theme_selected_bg_color, 0.25); }
.kb-touchpad-hint { color: alpha(@theme_fg_color, 0.35); font-size: 1.4em; }
"""

# Зазор подставляется числом, поэтому отдельной таблицей.
GUARD_CSS = """
.kb-pane-left  { padding-right: %(g)dpx; }
.kb-pane-right { padding-left:  %(g)dpx; }
"""

# Перезагружается на лету кнопками ◐−/◐+, поэтому отдельной таблицей.
GHOST_CSS = """
/* Режим наложения: клавиши лежат поверх терминала и просвечивают. Селекторы
   из двух классов, чтобы перебить одноклассовые правила базовой таблицы.
   Плотность подставляется на лету: под клавишами идёт текст терминала, и при
   сильной прозрачности он забивает подписи. */
.kb-ghost .kb-key, .kb-ghost .kb-key:hover, .kb-ghost .kb-key:active,
.kb-ghost .kb-key:checked, .kb-ghost .kb-key:focus {
  background-color: alpha(@theme_bg_color, %(a).2f);
  border-color: alpha(@theme_fg_color, 0.40);
  color: @theme_fg_color;
}
.kb-ghost .kb-special, .kb-ghost .kb-special:hover,
.kb-ghost .kb-special:active,
.kb-ghost .kb-mod, .kb-ghost .kb-mod:hover, .kb-ghost .kb-mod:active,
.kb-ghost .kb-tool, .kb-ghost .kb-tool:hover, .kb-ghost .kb-tool:active {
  background-color: alpha(shade(@theme_bg_color, 1.35), %(a).2f);
}
.kb-ghost .kb-arrow, .kb-ghost .kb-arrow:hover, .kb-ghost .kb-arrow:active {
  background-color: alpha(shade(@theme_bg_color, 1.5), %(a).2f);
}
.kb-ghost .kb-accent, .kb-ghost .kb-accent:hover,
.kb-ghost .kb-accent:active {
  background-color: alpha(@theme_selected_bg_color, 0.62);
}
.kb-ghost .kb-active, .kb-ghost .kb-active:hover,
.kb-ghost .kb-active:active {
  background-color: @theme_selected_bg_color; color: #ffffff;
}
.kb-ghost .kb-locked, .kb-ghost .kb-locked:hover,
.kb-ghost .kb-locked:active {
  background-color: #d4801a; color: #ffffff; border-color: #d4801a;
}
.kb-ghost .kb-key.kb-hit, .kb-ghost .kb-key.kb-hit:hover,
.kb-ghost .kb-key.kb-hit:active {
  background-color: @theme_selected_bg_color; color: #ffffff;
}
.kb-ghost .kb-macro, .kb-ghost .kb-macro:hover, .kb-ghost .kb-macro:active {
  background-color: alpha(shade(@theme_bg_color, 1.35), %(a).2f);
}
.kb-ghost .kb-macro-empty, .kb-ghost .kb-macro-empty:hover {
  background-color: alpha(@theme_bg_color, %(a).2f);
  border-style: dashed;
}
.kb-ghost .kb-touchpad {
  background-color: alpha(shade(@theme_bg_color, 1.35), %(a).2f);
  border-color: alpha(@theme_fg_color, 0.45);
}
"""


def aspect(child, ratio):
    # yalign=1.0 — клавиатура прижата вниз, туда, где лежат большие пальцы
    fr = Gtk.AspectFrame(xalign=0.5, yalign=1.0, ratio=ratio, obey_child=False)
    fr.set_shadow_type(Gtk.ShadowType.NONE)
    fr.add(child)
    return fr


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app,
                         title="terkb — терминал со сплит-клавиатурой")
        self.set_default_size(1280, 800)

        self.term = Terminal()
        self.kb_scale = 1.0       # множитель размера клавиатуры, кнопки ⌨−/⌨+
        self.state = KeyState(self.term)
        self.kb = self.state          # для тестов и внешнего кода

        self.pad_left = KeyPad(self.state, SPLIT_L_W)
        build_left(self.pad_left)
        self.pad_right = KeyPad(self.state, SPLIT_R_W)
        self.touchpad = Touchpad(self.on_pad_drag)
        build_right(self.pad_right, self.touchpad)
        self.state.refresh_labels()

        self.left_frame = aspect(self.pad_left,
                                 pad_ratio(SPLIT_L_W, NUM_ROWS + MAIN_ROWS))
        self.right_frame = aspect(self.pad_right,
                                  pad_ratio(SPLIT_R_W, TOP_ROWS + MAIN_ROWS))

        self.left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.left_box.get_style_context().add_class("kb-pane")
        self.left_box.get_style_context().add_class("kb-pane-left")
        self.left_box.pack_start(self.left_frame, True, True, 0)

        self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.right_box.get_style_context().add_class("kb-pane")
        self.right_box.get_style_context().add_class("kb-pane-right")
        self.right_box.pack_start(self.right_frame, True, True, 0)

        self.center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.bar = self.toolbar()
        self.center.pack_start(self.bar, False, False, 0)
        self.center.pack_start(self.macro_editor(), False, False, 0)
        self.center.pack_start(self.term, True, True, 0)
        self.state.on_macro_edit = self.edit_macro

        # Два вложенных Paned: левая половина | (терминал | правая половина)
        # Два вложенных Paned: левая половина | (терминал | правая половина).
        # Оба разделителя перетаскиваются.
        #
        # resize=False у половин, True у терминала: при изменении размера окна
        # клавиатура сохраняет ширину, а слак забирает терминал. Если отдать
        # resize=True обеим сторонам, Paned начинает перераспределять место сам
        # и затирает выставленные позиции.
        self.inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.inner.pack1(self.center, True, False)
        self.inner.pack2(self.right_box, False, False)
        self.outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.outer.pack1(self.left_box, False, False)
        self.outer.pack2(self.inner, True, False)

        # В режиме наложения половины вынимаются из Paned и кладутся поверх
        # терминала: сам терминал при этом занимает всё окно.
        self.overlay = Gtk.Overlay()
        self.overlay.add(self.outer)
        self.root = self.overlay      # то, что реально лежит в окне
        self.add(self.overlay)

        self.ghost = False
        # Плотность клавиш поверх терминала правится на лету кнопками ◐−/◐+,
        # поэтому у неё свой провайдер: базовую таблицу перезагружать незачем.
        self.ghost_alpha = GHOST_ALPHA
        self.ghost_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.ghost_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
        self.apply_ghost_css()
        for b in self.alpha_btns:
            b.set_sensitive(False)

        self._laid_out = (0, 0)   # размер, под который разложено
        self._retries = 0
        self.connect("size-allocate", self.on_alloc)

        self.state.refresh_macros()
        self.term.spawn(self.close)
        self.term.vte.grab_focus()

    def toolbar(self):
        # FlowBox, а не Box: минимальная ширина Box'а — это сумма всех кнопок,
        # и она становится полом для ширины терминала. С семью кнопками
        # разделитель переставал двигаться. FlowBox переносит их на вторую
        # строку, и минимум равен ширине одной кнопки.
        bar = Gtk.FlowBox()
        bar.set_selection_mode(Gtk.SelectionMode.NONE)
        bar.set_min_children_per_line(1)
        bar.set_max_children_per_line(20)
        bar.set_row_spacing(2)
        bar.set_column_spacing(2)
        bar.set_homogeneous(False)

        def place(widget):
            widget.set_can_focus(False)
            bar.add(widget)
            widget.get_parent().set_can_focus(False)   # GtkFlowBoxChild

        def btn(label, cb, tip=None):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda *_a: cb())
            if tip:
                b.set_tooltip_text(tip)
            place(b)
            return b

        btn("A−", lambda: self.term.zoom(-1), "Уменьшить шрифт терминала")
        btn("A+", lambda: self.term.zoom(1), "Увеличить шрифт терминала")

        btn("⌨−", lambda: self.zoom_kb(-KB_SCALE_STEP), "Клавиатуру меньше")
        btn("⌨+", lambda: self.zoom_kb(KB_SCALE_STEP), "Клавиатуру больше")

        self.alpha_btns = [
            btn("◐−", lambda: self.fade_kb(GHOST_ALPHA_STEP),
                "Клавиши плотнее (меньше прозрачности)"),
            btn("◐+", lambda: self.fade_kb(-GHOST_ALPHA_STEP),
                "Клавиши прозрачнее"),
        ]

        self.ghost_btn = Gtk.ToggleButton(label="Поверх")
        self.ghost_btn.set_tooltip_text(
            "Терминал во всю ширину, клавиши прозрачные поверх него")
        self.ghost_btn.connect("toggled", self.on_ghost)
        place(self.ghost_btn)
        return bar

    # -- режим наложения ----------------------------------------------------
    def on_ghost(self, btn):
        self.set_ghost(btn.get_active())
        self.term.vte.grab_focus()

    def set_ghost(self, on):
        self.ghost = on
        for box, halign in ((self.left_box, Gtk.Align.START),
                            (self.right_box, Gtk.Align.END)):
            parent = box.get_parent()
            if parent is not None:
                parent.remove(box)
            ctx = box.get_style_context()
            if on:
                ctx.add_class("kb-ghost")
                box.set_halign(halign)
                # Прижимаем вниз и задаём высоту ровно по клавиатуре: у
                # оверлей-ребёнка своё GdkWindow, и всё, что он накрывает,
                # перестаёт нажиматься. Растянутый на всю высоту, он забирал
                # касания у панели инструментов — кнопку «Поверх» было не
                # нажать обратно.
                box.set_valign(Gtk.Align.END)
                self.overlay.add_overlay(box)
            else:
                ctx.remove_class("kb-ghost")
                box.set_halign(Gtk.Align.FILL)
                box.set_valign(Gtk.Align.FILL)
                box.set_size_request(-1, -1)
        if not on:
            # порядок важен: pack1 у outer, pack2 у inner
            self.outer.pack1(self.left_box, False, False)
            self.inner.pack2(self.right_box, False, False)
        self.left_box.show_all()
        self.right_box.show_all()
        # прозрачность видна только поверх терминала
        for b in self.alpha_btns:
            b.set_sensitive(on)
        self._laid_out = (0, 0)   # заставить пересчитать
        self.schedule_layout()

    def key_size(self, w, h):
        """Размер клавиши, общий для обеих половин.

        Один размер на обе — иначе клавиши слева и справа разъедутся. По
        высоте тоже ограничиваем, иначе AspectFrame ужмёт половины по-разному.
        """
        cols = SPLIT_L_W + SPLIT_R_W
        key = w * KB_FRACTION * self.kb_scale / cols * U
        # потолок по ширине: половины не должны сойтись посередине
        key = min(key, w * KB_MAX_TOTAL / cols * U)
        if h > 50:
            rows = max(NUM_ROWS, TOP_ROWS) + MAIN_ROWS
            key = min(key, (h - PANE_PAD) / rows / KEY_STRETCH)
        return key

    # -- программируемые клавиши ---------------------------------------------
    def macro_editor(self):
        """Строка правки макроса. Живёт в окне, а не в диалоге: модальное окно
        перекрыло бы клавиатуру, которой и надо набирать."""
        # Подписи короткие и поле узкое намеренно: минимальная ширина Box'а —
        # это сумма детей, и она стала бы полом для центральной колонки,
        # сдвинув разделители (уже наступали на это с панелью инструментов).
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.get_style_context().add_class("kb-editor")
        self.macro_label = Gtk.Label(label="")
        box.pack_start(self.macro_label, False, False, 0)

        self.macro_entry = Gtk.Entry()
        self.macro_entry.set_width_chars(6)
        self.macro_entry.set_placeholder_text("команда, например: ls -la")
        box.pack_start(self.macro_entry, True, True, 0)

        for label, tip, cb in (("✓", "Сохранить", self.macro_accept),
                               ("✕", "Отмена", self.macro_cancel)):
            b = Gtk.Button(label=label)
            b.set_can_focus(False)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _b, f=cb: f())
            box.pack_start(b, False, False, 0)

        box.set_no_show_all(True)
        self.macro_box = box
        self.macro_index = -1
        return box

    def edit_macro(self, index):
        self.macro_index = index
        self.macro_label.set_text("M%d" % (index + 1))
        self.macro_entry.set_text(self.state.macros[index])
        self.macro_entry.set_position(-1)
        self.macro_box.show()
        for w in self.macro_box.get_children():
            w.show()
        self.macro_entry.grab_focus()
        # ввод с клавиатуры на время правки уходит в поле, а не в терминал
        self.state.send = EntrySink(self.macro_entry, self.macro_accept,
                                    self.macro_cancel)

    def macro_accept(self):
        if self.macro_index >= 0:
            self.state.set_macro(self.macro_index,
                                 self.macro_entry.get_text().strip())
        self.macro_cancel()

    def macro_cancel(self):
        self.macro_index = -1
        self.macro_box.hide()
        self.state.send = self.term          # ввод снова идёт в терминал
        self.term.vte.grab_focus()

    # -- тачпад --------------------------------------------------------------
    def on_pad_drag(self, dy):
        """Палец по полосе листает терминал. Как на телефоне: тянешь вниз —
        уходишь к более ранним строкам."""
        self.scroll_lines(-dy * SCROLL_SPEED
                          / max(1.0, self.term.vte.get_char_height()))

    def scroll_lines(self, lines):
        adj = self.term.vte.get_vadjustment()
        top = max(adj.get_lower(), adj.get_upper() - adj.get_page_size())
        adj.set_value(min(top, max(adj.get_lower(), adj.get_value() + lines)))

    def apply_ghost_css(self):
        self.ghost_provider.load_from_data(
            (GHOST_CSS % {"a": self.ghost_alpha}).encode())

    def fade_kb(self, delta):
        """Изменить плотность клавиш в режиме наложения."""
        a = min(GHOST_ALPHA_MAX, max(GHOST_ALPHA_MIN, self.ghost_alpha + delta))
        if abs(a - self.ghost_alpha) < 1e-9:
            return
        self.ghost_alpha = a
        self.apply_ghost_css()
        self.term.vte.grab_focus()

    def avail_height(self, h):
        """Высота, доступная клавиатуре.

        В режиме наложения панель инструментов надо оставить свободной: под
        оверлей-ребёнком ничего не нажимается.
        """
        return h - (self.bar.get_allocation().height if self.ghost else 0)

    def zoom_kb(self, delta):
        """Изменить размер клавиатуры.

        В режиме наложения это единственный способ: разделителей там нет.
        В обычном режиме кнопки переставляют разделители — подвинуть их потом
        руками всё равно можно.
        """
        scale = min(KB_SCALE_MAX, max(KB_SCALE_MIN, self.kb_scale + delta))
        if abs(scale - self.kb_scale) < 1e-9:
            return
        a = self.root.get_allocation()
        if a.width > 100 and delta > 0:
            # Клавиатура может упереться в высоту окна раньше, чем масштаб
            # дойдёт до предела. Копить недостижимый масштаб нельзя: иначе
            # ⌨+ жмётся вхолостую, а потом ⌨− несколько раз без реакции.
            h = self.avail_height(a.height)
            before = self.key_size(a.width, h)
            prev, self.kb_scale = self.kb_scale, scale
            if self.key_size(a.width, h) <= before + 0.01:
                self.kb_scale = prev
                return
        else:
            self.kb_scale = scale
        self.schedule_layout()
        self.term.vte.grab_focus()

    def half_widths(self, w, h):
        """Ширины половин: пропорционально числу колонок в каждой."""
        key = self.key_size(w, h)
        return (int(key * SPLIT_L_W / U) + PANE_PAD,
                int(key * SPLIT_R_W / U) + PANE_PAD)

    def half_height(self, key, rows):
        return int(key * rows * KEY_STRETCH) + PANE_PAD

    def targets(self, width=None, height=None):
        """Желаемые размеры половин под текущий режим.

        Размер берётся у root, а не у окна: в тестах дерево виджетов живёт
        в OffscreenWindow, и аллокация самого окна остаётся нулевой.
        """
        a = self.root.get_allocation()
        w = width if width is not None else a.width
        h = height if height is not None else a.height
        if w <= 100:
            return None
        key = self.key_size(w, self.avail_height(h))
        return {
            "w": w, "h": h,
            "lw": int(key * SPLIT_L_W / U) + PANE_PAD,
            "rw": int(key * SPLIT_R_W / U) + PANE_PAD,
            "lh": self.half_height(key, NUM_ROWS + MAIN_ROWS),
            "rh": self.half_height(key, TOP_ROWS + MAIN_ROWS),
        }

    def relayout(self, width=None, height=None):
        """Применить раскладку. False — размеры ещё не готовы."""
        t = self.targets(width, height)
        if t is None:
            return False
        if self.ghost:
            self.left_box.set_size_request(t["lw"], t["lh"])
            self.right_box.set_size_request(t["rw"], t["rh"])
        else:
            self.outer.set_position(t["lw"])
            self.inner.set_position(max(120, t["w"] - t["lw"] - t["rw"]))
        return True

    def place_dividers(self, width=None, height=None):
        """Разложить под явный размер и добить асинхронно.

        Нужно тестам и харнессу скриншотов: там окно не показано на экране,
        size-allocate не приходит, и сам по себе schedule_layout не запустится.
        """
        self.relayout(width, height)
        self.schedule_layout()

    def layout_ok(self):
        """Приняло ли GTK выставленные размеры."""
        t = self.targets()
        if t is None:
            return False
        return (abs(self.left_box.get_allocation().width - t["lw"]) <= 2
                and abs(self.right_box.get_allocation().width - t["rw"]) <= 2)

    def schedule_layout(self):
        """Разложить, когда GTK досчитает размеры.

        Сразу после смены режима аллокации ещё старые: Paned обрезает позицию
        по прежней ширине, а половина, которой ничего не выставили, схлопы-
        вается в свой минимум. Поэтому пробуем на idle и повторяем, пока не
        сойдётся. Счётчик попыток обнуляется на каждый новый запрос — иначе
        после нескольких переключений он исчерпывался навсегда, и раскладка
        переставала чиниться.
        """
        self._retries = 0
        GLib.idle_add(self._layout_step)

    def _layout_step(self):
        if self._retries >= 15:
            return False
        self._retries += 1
        if not self.relayout():
            GLib.timeout_add(50, self._layout_step)   # окно ещё не размещено
        elif not self.layout_ok():
            GLib.timeout_add(30, self._layout_step)
        return False

    def on_alloc(self, _w, alloc):
        size = (alloc.width, alloc.height)
        if alloc.width > 100 and size != self._laid_out:
            # Раскладываем при смене размера окна. Дальше в обычном режиме
            # разделители — дело пользователя, мы их не трогаем.
            self._laid_out = size
            self.schedule_layout()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(
            (CSS + GUARD_CSS % {"g": HANDLE_GUARD}).encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        win = Window(self)
        win.show_all()


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
