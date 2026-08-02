"""Клавиша, её описание в файле раскладки и общее состояние клавиатуры."""

import os

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib  # noqa: E402

from .config import load_macros, save_macros
from .geometry import PROG_KEYS, PROG_W, U

# Служебные слова, за которыми стоит настоящая команда: подпись на клавише
# должна показывать её, а не «sudo».
CMD_PREFIXES = {"sudo", "env", "nohup", "time", "doas", "exec", "command"}

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
        self.x = self.y = 0       # место в сетке, проставляет KeyPad.add_key

    # -- обмен с файлом раскладки -------------------------------------------
    def to_spec(self):
        """Клавиша в виде словаря для layout.json. Пишем только то, что
        отличается от умолчаний: файл читают и правят руками."""
        spec = {"kind": self.kind, "low": self.low,
                "x": self.x, "y": self.y}
        if self.w != U:
            spec["w"] = self.w
        if self.h != 1:
            spec["h"] = self.h
        if self.kind == "char":
            spec["high"] = self.high
            if getattr(self, "ru", None):
                spec["ru"] = list(self.ru)
        if self.keyval is not None:
            spec["keyval"] = Gdk.keyval_name(self.keyval) or self.keyval
        if self.name is not None:
            spec["name"] = self.name
        if self.data is not None:
            spec["data"] = (self.data.decode("utf-8", "replace")
                            if isinstance(self.data, bytes) else self.data)
        if self.css:
            spec["css"] = self.css
        if self.repeat:
            spec["repeat"] = True
        return spec


def key_from_spec(spec):
    """Клавиша из словаря layout.json. Ошибку описываем словами: файл правят
    руками, и «KeyError» вместо «нет поля low» там не поможет."""
    if not isinstance(spec, dict):
        raise ValueError("клавиша должна быть объектом, а не %s"
                         % type(spec).__name__)
    kind = spec.get("kind")
    if kind not in ("char", "key", "mod", "raw", "action", "macro"):
        raise ValueError("неизвестный вид клавиши: %r" % (kind,))
    low = spec.get("low", "")
    if not isinstance(low, str):
        raise ValueError("подпись low должна быть строкой")

    keyval = spec.get("keyval")
    if isinstance(keyval, str):
        code = Gdk.keyval_from_name(keyval)
        if code == Gdk.KEY_VoidSymbol:
            raise ValueError("нет такой клавиши GDK: %r" % keyval)
        keyval = code
    if kind == "key" and keyval is None:
        raise ValueError("клавише %r нужен keyval" % low)
    if kind == "mod" and spec.get("name") not in ("ctrl", "alt", "shift",
                                                  "super"):
        raise ValueError("модификатор %r: name должен быть ctrl/alt/shift/super"
                         % low)

    data = spec.get("data")
    if kind == "macro":
        if not isinstance(data, int) or not 0 <= data < PROG_KEYS:
            raise ValueError("макросу нужен data от 0 до %d" % (PROG_KEYS - 1))
    elif kind == "raw" and isinstance(data, str):
        data = data.encode("utf-8")

    key = Key(kind, low, spec.get("high"), keyval=keyval,
              w=int(spec.get("w", U)), h=int(spec.get("h", 1)),
              name=spec.get("name"), data=data, css=spec.get("css"),
              repeat=bool(spec.get("repeat", False)))
    if kind == "char":
        ru = spec.get("ru") or [key.low, key.high]
        if len(ru) != 2:
            raise ValueError("ru у клавиши %r: нужны две подписи" % low)
        key.ru = (str(ru[0]), str(ru[1]))
    if key.w < 1 or key.h < 1:
        raise ValueError("клавиша %r: ширина и высота от одной четверти" % low)
    return key


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


def macro_label(cmd, index):
    """Короткая подпись на клавише макроса.

    Целиком команда не влезает: клавиша шириной чуть больше обычной, и подпись
    обрезалась многоточием на втором-третьем символе — «g…» не говорит ничего.
    Поэтому берём саму команду без пути и аргументов: «git», «htop», «run.sh».
    """
    for word in cmd.split():
        if word in CMD_PREFIXES or "=" in word:
            continue                      # sudo, env, VAR=значение
        name = os.path.basename(word.strip("\"'"))
        if name:
            return name[:12]
        break
    return "M%d" % (index + 1)


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
            key.label.set_text(macro_label(cmd, key.data))
            key.button.set_tooltip_text(
                "M%d: %s" % (key.data + 1, cmd) if cmd
                else "M%d — долгое нажатие задаёт команду" % (key.data + 1))
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
