"""Файлы в ~/.config/terkb: настройки, макросы, раскладки.

Пути лежат здесь же, а не в модулях, которые ими пользуются: так их можно
подменить в одном месте (этим пользуются тесты).
"""

import json
import os
import sys

from .geometry import (GHOST_ALPHA, GHOST_ALPHA_MAX, GHOST_ALPHA_MIN,
                       KB_FRACTION, KB_MAX_TOTAL, KB_SCALE_MAX, KB_SCALE_MIN,
                       PROG_KEYS)
from .schemes import DEFAULT_SCHEME, FONT_MAX, FONT_MIN, scheme_by_id

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "terkb")
MACRO_FILE = os.path.join(CONFIG_DIR, "macros.json")

# Схема, шрифт и его размер: всё, что правится кнопками панели и должно
# пережить перезапуск.
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

# Раскладки клавиш. Файла нет — работают встроенные; создать его с текущими
# раскладками умеет сам terkb (--dump-layout).
LAYOUT_FILE = os.path.join(CONFIG_DIR, "layout.json")


SETTINGS_SPEC = {
    "scheme": (DEFAULT_SCHEME, lambda v: scheme_by_id(str(v)) is not None),
    "font": ("Monospace", lambda v: isinstance(v, str) and bool(v)),
    "font_size": (8, lambda v: isinstance(v, int)
                  and FONT_MIN <= v <= FONT_MAX),
    # Доля ширины окна под обе половины. Раньше правилась только в коде —
    # значит терялась при обновлении.
    "kb_fraction": (KB_FRACTION, lambda v: isinstance(v, (int, float))
                    and 0.2 <= v <= KB_MAX_TOTAL),
    "kb_scale": (1.0, lambda v: isinstance(v, (int, float))
                 and KB_SCALE_MIN <= v <= KB_SCALE_MAX),
    "ghost_alpha": (GHOST_ALPHA, lambda v: isinstance(v, (int, float))
                    and GHOST_ALPHA_MIN <= v <= GHOST_ALPHA_MAX),
    "ghost": (False, lambda v: isinstance(v, bool)),
    "hidden": (False, lambda v: isinstance(v, bool)),
    "fullscreen": (False, lambda v: isinstance(v, bool)),
    "width": (1280, lambda v: isinstance(v, int) and 320 <= v <= 8192),
    "height": (800, lambda v: isinstance(v, int) and 240 <= v <= 8192),
}


def load_settings():
    """Сохранённые настройки. Битый файл не должен ронять запуск."""
    out = {k: default for k, (default, _ok) in SETTINGS_SPEC.items()}
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    for key, (_default, ok) in SETTINGS_SPEC.items():
        if key in data:
            try:
                if ok(data[key]):
                    out[key] = data[key]
            except (TypeError, ValueError):
                pass
    return out


def save_settings(settings):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print("terkb: не удалось сохранить настройки: %s" % e, file=sys.stderr)


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
