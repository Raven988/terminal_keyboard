"""Терминал VTE и приёмник ввода для строк правки."""

import os
import sys

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, GLib, Gtk, Pango, Vte  # noqa: E402

from .schemes import FONT_MAX, FONT_MIN, gdk_rgba

# --- ссылки в выводе ------------------------------------------------------
# Что считать ссылкой. Хвостовая пунктуация отсекается: адрес в конце
# предложения обычно заканчивается точкой или запятой, и они в URL не входят.
# Второй шаблон ловит адреса без схемы (www.example.org) — к ним потом
# приписывается https://.
LINK_TAIL = r"""[^\s'"<>()\[\]{}«»]*[^\s'"<>()\[\]{}«».,;:!?]"""
LINK_PATTERNS = [
    r"(?:https?|ftp|file)://" + LINK_TAIL,
    r"www\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}" + LINK_TAIL,
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
]

# PCRE2_MULTILINE — иначе VTE ругается на шаблон без якорей; значение зашито
# числом, потому что через GI константы PCRE2 не пробрасываются.
LINK_REGEX_FLAGS = 0x00000400


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
        self.vte.set_cursor_shape(Vte.CursorShape.BLOCK)
        self.font_size = 8
        self.font_family = "Monospace"
        self.apply_font()
        self.setup_links()

        self.pack_start(self.vte, True, True, 0)
        adj = self.vte.get_vadjustment()
        sb = Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL, adjustment=adj)
        sb.get_style_context().add_class("term-scroll")
        self.pack_start(sb, False, False, 0)

    # -- ссылки -------------------------------------------------------------
    def setup_links(self):
        """Сделать ссылки в выводе нажимаемыми.

        На планшете ссылку иначе не открыть: выделить её пальцем в VTE толком
        не выходит, а перенабирать вручную — то ещё занятие. Кроме обычного
        поиска по тексту включаем OSC 8: программы вроде ls и gh отдают ссылку
        отдельной последовательностью, и угадывать её по виду не нужно.
        """
        self.link_tags = []
        try:
            self.vte.set_allow_hyperlink(True)
        except AttributeError:
            pass          # VTE старше 0.50
        for pattern in LINK_PATTERNS:
            try:
                regex = Vte.Regex.new_for_match(pattern, -1,
                                                LINK_REGEX_FLAGS)
                tag = self.vte.match_add_regex(regex, 0)
            except (AttributeError, GLib.Error):
                continue  # сборка VTE без PCRE2 — просто останемся без ссылок
            self.vte.match_set_cursor_name(tag, "pointer")
            self.link_tags.append(tag)
        self.vte.connect("button-press-event", self.on_click)

    def link_at(self, event):
        """URL под касанием: сначала OSC 8, потом распознанный по тексту."""
        try:
            uri = self.vte.hyperlink_check_event(event)
        except AttributeError:
            uri = None
        if uri:
            return uri
        match, tag = self.vte.match_check_event(event)
        if not match or tag not in self.link_tags:
            return None
        if "://" in match:
            return match
        # адрес почты открываем почтовиком, всё остальное — как http-адрес
        return ("mailto:" + match) if "@" in match else ("https://" + match)

    def on_click(self, _w, event):
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        uri = self.link_at(event)
        if not uri:
            return False
        try:
            Gtk.show_uri_on_window(self.get_toplevel(), uri, event.time)
        except GLib.Error as e:
            print("terkb: не удалось открыть %s: %s" % (uri, e.message),
                  file=sys.stderr)
        return True

    def apply_font(self):
        self.vte.set_font(Pango.FontDescription(
            "%s %d" % (self.font_family, self.font_size)))

    def zoom(self, delta):
        self.font_size = max(FONT_MIN, min(FONT_MAX, self.font_size + delta))
        self.apply_font()

    def set_font_family(self, family):
        self.font_family = family
        self.apply_font()

    def apply_scheme(self, scheme):
        """Цвета терминала. У «Системы» их нет — сбрасываем в тему GTK.

        set_colors перетирает и курсор с выделением, поэтому их ставим после
        неё, а не до.
        """
        palette = [gdk_rgba(c) for c in scheme["palette"]] or None
        fg = gdk_rgba(scheme["fg"]) if scheme["fg"] else None
        bg = gdk_rgba(scheme["bg"]) if scheme["bg"] else None
        self.vte.set_colors(fg, bg, palette)
        self.vte.set_color_cursor(
            gdk_rgba(scheme["cursor"]) if scheme["cursor"] else None)
        if scheme["sel"]:
            self.vte.set_color_highlight(gdk_rgba(scheme["sel"]))
            self.vte.set_color_highlight_foreground(fg)
        else:
            self.vte.set_color_highlight(None)
            self.vte.set_color_highlight_foreground(None)
        # Курсор-блок закрашивает символ под собой: без контрастного текста
        # под курсором не видно, какая это буква.
        try:
            self.vte.set_color_cursor_foreground(bg)
        except AttributeError:
            pass          # VTE старше 0.44
        try:
            self.vte.set_bold_is_bright(True)
        except AttributeError:
            pass          # VTE старше 0.52

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
