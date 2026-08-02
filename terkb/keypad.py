"""Сетка клавиш, полоса перемотки и рамка с постоянными пропорциями."""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from .geometry import HIT_TIMEOUT_MS, U

# Номер сетки: у каждой свой CSS-класс, чтобы правило размера шрифта не
# разъезжалось между половинами.
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

        key.x, key.y = col, row       # понадобится при выгрузке раскладки
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


def aspect(child, ratio):
    # yalign=1.0 — клавиатура прижата вниз, туда, где лежат большие пальцы
    fr = Gtk.AspectFrame(xalign=0.5, yalign=1.0, ratio=ratio, obey_child=False)
    fr.set_shadow_type(Gtk.ShadowType.NONE)
    fr.add(child)
    return fr
