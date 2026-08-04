"""Таблицы стилей: базовая, наложение и цвета выбранной схемы."""

from .schemes import luma, mix

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
/* На кнопках панели значки, а не подписи: без своей ширины они ужимаются до
   размера одного символа, и пальцем в них не попасть. */
.terkb-tools button {
  min-width: 36px;
  padding: 4px 8px;
  font-size: 1.1em;
}
.terkb-tabs { padding: 2px 4px; }
/* Открытую вкладку помечаем своим классом, а не состоянием :checked:
   переключение идёт кодом, и состояние кнопки пришлось бы гонять вручную.
   Селектор с именем элемента — иначе правило темы button:hover со
   специфичностью (0,1,1) перебивает наш одноклассовый.
   Здесь, у схемы «Система», годится акцентный цвет темы: он всегда яркий.
   У остальных схем выделение бывает почти неотличимо от панели, и там
   открытая вкладка красится фоном терминала — см. SKIN_CSS. */
button.terkb-tab-on, button.terkb-tab-on:hover, button.terkb-tab-on:active {
  background-image: none;
  background-color: @theme_selected_bg_color;
  color: #ffffff;
  font-weight: bold;
  text-shadow: none;
}
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

# Цветовая схема красит не только терминал: клавиши, панель и строка правки
# берут цвета оттуда же. Иначе тёмный терминал сидит в светлой рамке системной
# темы, и окно выглядит склеенным из двух программ.
#
# Состояния (:hover, :active, ...) перечислены так же, как в базовой таблице:
# у провайдера приоритет выше, но при равной специфичности спорить не о чем.
# Правила для .kb-ghost идут парами к обычным — в наложении отличается только
# плотность фона.
SKIN_CSS = """
window.terkb-win { background-color: %(bg)s; color: %(fg)s; }
.terkb-bar, .kb-pane, .kb-editor {
  background-color: %(panel)s;
  color: %(fg)s;
}
.terkb-bar { border-bottom: 1px solid %(edge)s; }
/* В наложении подложка половин лежит поверх терминала: непрозрачной она
   закрыла бы текст между клавишами. */
.kb-pane.kb-ghost { background-color: transparent; }
.kb-editor label, .terkb-bar label { color: %(fg)s; }
.terkb-bar button, .kb-editor button,
.terkb-bar button:hover, .kb-editor button:hover,
.terkb-bar button:active, .kb-editor button:active,
.terkb-bar button:checked {
  background-image: none;
  background-color: %(special)s;
  border: 1px solid %(edge)s;
  color: %(fg)s;
  text-shadow: none;
}
.terkb-bar button:checked, .terkb-bar button:active, .kb-editor button:active {
  background-color: %(sel)s;
  border-color: %(sel)s;
  color: %(selfg)s;
}
.terkb-bar button:disabled { color: %(dim)s; border-color: %(edge)s; }
/* Открытая вкладка — фоном терминала, как её содержимое: акцентным цветом
   красить нельзя, у половины схем выделение почти не отличается от панели
   (в Dracula это тёмно-серый #44475a), и открытая вкладка терялась. Рамка
   акцентная, подпись жирная — этого хватает и на светлых схемах.
   Селектор из двух классов и имени элемента: одноклассовый перебило бы
   правило «.terkb-bar button» несколькими строками выше. */
.terkb-bar button.terkb-tab-on, .terkb-bar button.terkb-tab-on:hover,
.terkb-bar button.terkb-tab-on:active {
  background-color: %(bg)s;
  border-color: %(sel)s;
  color: %(fg)s;
  font-weight: bold;
}
.kb-editor entry {
  background-image: none;
  background-color: %(key)s;
  border: 1px solid %(edge)s;
  color: %(fg)s;
}
.term-scroll { background-color: %(bg)s; border: none; }
.term-scroll slider {
  background-color: %(dim)s;
  border: none;
  border-radius: 6px;
  min-width: 8px;
}
.term-scroll slider:hover { background-color: %(sel)s; }

.kb-key, .kb-key:hover, .kb-key:active, .kb-key:checked, .kb-key:focus {
  background-color: %(key)s;
  border-color: %(edge)s;
  color: %(fg)s;
}
.kb-ghost .kb-key, .kb-ghost .kb-key:hover, .kb-ghost .kb-key:active,
.kb-ghost .kb-key:checked, .kb-ghost .kb-key:focus {
  background-color: alpha(%(key)s, %(a).2f);
  border-color: %(edge)s;
  color: %(fg)s;
}
.kb-special, .kb-special:hover, .kb-special:active,
.kb-mod, .kb-mod:hover, .kb-mod:active,
.kb-tool, .kb-tool:hover, .kb-tool:active,
.kb-macro, .kb-macro:hover, .kb-macro:active {
  background-color: %(special)s;
}
.kb-ghost .kb-special, .kb-ghost .kb-special:hover,
.kb-ghost .kb-special:active,
.kb-ghost .kb-mod, .kb-ghost .kb-mod:hover, .kb-ghost .kb-mod:active,
.kb-ghost .kb-tool, .kb-ghost .kb-tool:hover, .kb-ghost .kb-tool:active,
.kb-ghost .kb-macro, .kb-ghost .kb-macro:hover, .kb-ghost .kb-macro:active {
  background-color: alpha(%(special)s, %(a).2f);
}
.kb-arrow, .kb-arrow:hover, .kb-arrow:active {
  background-color: %(arrow)s;
}
.kb-ghost .kb-arrow, .kb-ghost .kb-arrow:hover, .kb-ghost .kb-arrow:active {
  background-color: alpha(%(arrow)s, %(a).2f);
}
.kb-accent, .kb-accent:hover, .kb-accent:active {
  background-color: alpha(%(sel)s, 0.45);
}
.kb-ghost .kb-accent, .kb-ghost .kb-accent:hover,
.kb-ghost .kb-accent:active {
  background-color: alpha(%(sel)s, 0.62);
}
.kb-active, .kb-active:hover, .kb-active:active,
.kb-key.kb-hit, .kb-key.kb-hit:hover, .kb-key.kb-hit:active,
.kb-ghost .kb-active, .kb-ghost .kb-active:hover, .kb-ghost .kb-active:active,
.kb-ghost .kb-key.kb-hit, .kb-ghost .kb-key.kb-hit:hover,
.kb-ghost .kb-key.kb-hit:active {
  background-color: %(sel)s;
  border-color: %(sel)s;
  color: %(selfg)s;
}
.kb-macro-empty, .kb-macro-empty:hover, .kb-macro-empty:active {
  background-color: transparent;
  border-style: dashed;
  color: %(dim)s;
}
.kb-ghost .kb-macro-empty, .kb-ghost .kb-macro-empty:hover {
  background-color: alpha(%(bg)s, %(a).2f);
  border-style: dashed;
}
.kb-touchpad {
  background-color: %(special)s;
  border: 1px dashed %(edge)s;
}
.kb-ghost .kb-touchpad {
  background-color: alpha(%(special)s, %(a).2f);
  border-color: %(edge)s;
}
.kb-touchpad:active, .kb-ghost .kb-touchpad:active {
  background-color: alpha(%(sel)s, 0.25);
}
.kb-touchpad-hint { color: %(dim)s; }
"""


def skin_colors(scheme, alpha):
    """Цвета для SKIN_CSS: от фона схемы к её тексту, ступенями."""
    bg, fg, sel = scheme["bg"], scheme["fg"], scheme["sel"]
    return {
        "a": alpha,
        "bg": bg,
        "fg": fg,
        "sel": sel,
        # текст на акцентном фоне: у светлых схем выделение светлое, и белым
        # по нему не прочитать
        "selfg": bg if luma(sel) > 0.55 else "#ffffff",
        # панель чуть отходит от фона терминала, клавиши — от панели: иначе
        # в светлых схемах всё сливается в одно пятно
        "panel": mix(bg, fg, 0.05),
        "key": mix(bg, fg, 0.14),
        "special": mix(bg, fg, 0.22),
        "arrow": mix(bg, fg, 0.30),
        "edge": mix(bg, fg, 0.34),
        "dim": mix(bg, fg, 0.45),
    }
