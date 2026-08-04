"""terkb — терминал со сплит-клавиатурой для планшета.

Половины клавиатуры прижаты к краям экрана, терминал между ними: планшет
держат двумя руками и набирают большими пальцами. Над левой половиной —
цифровой блок, над правой — стрелки.

Клавиатура и терминал живут в одном процессе, поэтому ввод отдаётся
VTE-виджету напрямую — без ydotool/uinput и без проблем с инжектом
ввода в Wayland.

Пакет разложен так:

    geometry  размеры клавиатуры в «четвертях клавиши»
    schemes   цветовые схемы, работа с цветом, выбор шрифта
    styles    таблицы стилей GTK, в том числе собранные по схеме
    config    файлы в ~/.config/terkb: настройки, макросы, раскладки
    keys      клавиша, её запись в файле раскладки, общее состояние
    keypad    сетка клавиш, полоса перемотки
    layouts   встроенные раскладки и обмен с layout.json
    terminal  VTE и приёмник ввода для встроенных строк правки
    tabs      вкладки: полоса кнопок и стопка терминалов
    window    окно: панель, вкладки, режимы, поиск, правка макросов
    app       приложение GTK и разбор командной строки

Имена, которыми пользуются снаружи, собраны здесь — кроме путей к файлам и
HIT_TIMEOUT_MS: их подменяют в тестах, а подмена работает только там, где
имя определено, поэтому за ними ходят в terkb.config и terkb.keypad.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")

from . import config, geometry, keypad, keys, layouts, schemes  # noqa: E402
from . import styles, tabs, terminal, window                    # noqa: E402
from .app import APP_ID, App, main                              # noqa: E402
from .config import (SETTINGS_SPEC, load_macros, load_settings,  # noqa: E402
                     save_macros, save_settings)
from .geometry import *                                          # noqa: E402,F401,F403
from .keypad import KeyPad, Touchpad, aspect                     # noqa: E402
from .keys import (A, C, K, M, P, R, Key, KeyState, ctrl_code,   # noqa: E402
                   key_from_spec, macro_label)
from .layouts import (BUILTIN_LAYOUTS, build_full, build_layout,  # noqa: E402
                      build_left, build_right, dump_layouts, load_layouts)
from .schemes import (DEFAULT_SCHEME, FONT_CHOICES, FONT_MAX,    # noqa: E402
                      FONT_MIN, SCHEMES, available_fonts, is_dark, luma,
                      mix, scheme_by_id)
from .styles import CSS, GHOST_CSS, GUARD_CSS, SKIN_CSS, skin_colors  # noqa: E402
from .tabs import MAX_TABS, Tab, Tabs, short_title                # noqa: E402
from .terminal import (LINK_PATTERNS, EntrySink, Terminal)       # noqa: E402
from .window import Window                                       # noqa: E402
