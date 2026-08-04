"""Вкладки: несколько терминалов в одном окне."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402

# Больше восьми вкладок полоса не вмещает по-человечески: подписи ужимаются до
# многоточия, и попасть пальцем в нужную становится лотереей.
MAX_TABS = 8

# Ширина подписи в символах: дальше Pango ставит многоточие.
TITLE_CHARS = 12


def short_title(title, index):
    """Подпись вкладки из заголовка, который выставил шелл.

    Шелл пишет туда «пользователь@машина: ~/каталог». Полезен только хвост:
    начало у всех вкладок одинаковое и место на полосе занимает зря.

    Номер идёт первым и всегда: соседние вкладки обычно открыты в одном
    каталоге, и без номера их подписи не различить. Заголовка ещё нет (шелл
    не поднялся, программа его не ставит) — остаётся один номер.
    """
    title = (title or "").strip()
    if ": " in title:
        title = title.split(": ", 1)[1].strip()
    return "%d %s" % (index + 1, title) if title else "№%d" % (index + 1)


class Tab:
    """Одна вкладка: терминал и его кнопка на полосе."""

    def __init__(self, term, row, button, label, close_btn):
        self.term = term
        self.row = row              # Gtk.Box: кнопка вкладки и крестик
        self.button = button
        self.label = label
        self.close_btn = close_btn
        self.title = ""


class Tabs:
    """Полоса вкладок и стопка терминалов.

    Полоса и терминалы висят в дереве порознь: кнопки лежат в шапке во всю
    ширину окна, а терминалы — в центральной колонке между половинами
    клавиатуры. Переключение ничего не пересобирает: у каждой вкладки свой
    виджет, меняется только видимая страница Gtk.Stack.

    Три обратных вызова, все необязательные:
      on_switch(old, new)  перешли на другую вкладку
      on_change()          вкладок стало больше или меньше
      on_empty()           закрылась последняя
    """

    def __init__(self, on_switch=None, on_change=None, on_empty=None):
        self.on_switch = on_switch
        self.on_change = on_change
        self.on_empty = on_empty
        self.tabs = []
        self.current = None

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)

        # FlowBox, а не Box: минимальная ширина Box'а — сумма всех вкладок, и
        # она стала бы полом для ширины окна. FlowBox переносит лишние на
        # вторую строку, и минимум равен ширине одной вкладки. Тем же занята
        # панель инструментов, там на это уже наступали.
        self.strip = Gtk.FlowBox()
        ctx = self.strip.get_style_context()
        ctx.add_class("terkb-bar")         # цвета схемы полоса берёт оттуда же
        ctx.add_class("terkb-tabs")
        self.strip.set_selection_mode(Gtk.SelectionMode.NONE)
        self.strip.set_min_children_per_line(1)
        self.strip.set_max_children_per_line(MAX_TABS)
        self.strip.set_row_spacing(2)
        self.strip.set_column_spacing(2)
        self.strip.set_homogeneous(True)    # вкладки одной ширины
        # Видимостью полосы распоряжаемся сами: с одной вкладкой её нет.
        self.strip.set_no_show_all(True)

    # -- список -------------------------------------------------------------
    @property
    def terms(self):
        return [tab.term for tab in self.tabs]

    def find(self, term):
        for tab in self.tabs:
            if tab.term is term:
                return tab
        return None

    # -- построение ---------------------------------------------------------
    def add(self, term):
        """Добавить вкладку с готовым терминалом и перейти на неё."""
        self.stack.add(term)
        term.show_all()

        lbl = Gtk.Label(label="")
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        lbl.set_max_width_chars(TITLE_CHARS)
        btn = Gtk.Button()
        btn.set_can_focus(False)           # фокус остаётся в терминале
        btn.add(lbl)
        btn.connect("clicked", lambda _b, t=term: self.select(t))

        close_btn = Gtk.Button(label="✕")
        close_btn.set_can_focus(False)
        close_btn.set_tooltip_text("Закрыть вкладку")
        close_btn.connect("clicked", lambda _b, t=term: self.close(t))

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        row.get_style_context().add_class("terkb-tab")
        row.pack_start(btn, True, True, 0)
        row.pack_start(close_btn, False, False, 0)
        self.strip.add(row)
        row.get_parent().set_can_focus(False)      # GtkFlowBoxChild
        row.show_all()
        row.get_parent().show()

        tab = Tab(term, row, btn, lbl, close_btn)
        self.tabs.append(tab)
        term.vte.connect("window-title-changed", self._on_title, tab)
        self.select(term)
        self.refresh()
        return tab

    def _on_title(self, vte, tab):
        """Шелл сменил заголовок — обновляем подпись, и только её.

        Заголовок меняется на каждом приглашении, то есть после каждой команды.
        Полный refresh отсюда звать нельзя: он дёргает on_change, а по нему
        окно пересчитывает раскладку.
        """
        tab.title = vte.get_window_title() or ""
        self.relabel()

    # -- переключение -------------------------------------------------------
    def select(self, term):
        if term is self.current:
            return
        old, self.current = self.current, term
        self.stack.set_visible_child(term)
        for tab in self.tabs:
            ctx = tab.button.get_style_context()
            if tab.term is term:
                ctx.add_class("terkb-tab-on")
            else:
                ctx.remove_class("terkb-tab-on")
        if self.on_switch:
            self.on_switch(old, term)

    def step(self, delta):
        """Соседняя вкладка, по кругу."""
        if len(self.tabs) < 2:
            return
        i = self.tabs.index(self.find(self.current))
        self.select(self.tabs[(i + delta) % len(self.tabs)].term)

    def close(self, term):
        """Закрыть вкладку.

        Терминал уничтожается вместе с pty, и шелл получает SIGHUP — то есть
        закрытие вкладки прилетит обратно сигналом child-exited на тот же
        терминал. Поэтому неизвестный терминал — не ошибка, а обычный повтор.
        """
        tab = self.find(term)
        if tab is None:
            return
        i = self.tabs.index(tab)
        self.tabs.remove(tab)
        child = tab.row.get_parent()               # GtkFlowBoxChild
        self.strip.remove(child)
        child.destroy()
        self.stack.remove(term)
        term.destroy()
        if self.current is term:
            self.current = None
        if self.tabs:
            # Соседняя справа, а на конце списка — слева.
            self.select(self.tabs[min(i, len(self.tabs) - 1)].term)
        self.refresh()
        if not self.tabs and self.on_empty:
            self.on_empty()

    # -- отображение --------------------------------------------------------
    def relabel(self):
        for i, tab in enumerate(self.tabs):
            tab.label.set_text(short_title(tab.title, i))
            tab.button.set_tooltip_text(
                "Вкладка %d%s" % (i + 1,
                                  ": " + tab.title if tab.title else ""))

    def refresh(self):
        """Подписи и видимость полосы.

        Одна вкладка — полосы нет: на десятидюймовом экране каждая строка
        интерфейса на счету, а переключать всё равно нечего.
        """
        self.relabel()
        self.strip.set_visible(len(self.tabs) > 1)
        if self.on_change:
            self.on_change()
