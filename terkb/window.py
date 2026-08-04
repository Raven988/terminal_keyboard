"""Окно: панель кнопок, раскладка, режимы и всё, что ими правится."""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, GLib, Gtk, Vte  # noqa: E402

from .config import load_settings, save_settings
from .geometry import (FULL_MAX_H, FULL_ROWS, FULL_W, GHOST_ALPHA_MAX,
                       GHOST_ALPHA_MIN, GHOST_ALPHA_STEP, KB_MAX_TOTAL,
                       KB_SCALE_MAX, KB_SCALE_MIN, KB_SCALE_STEP, KEY_STRETCH,
                       MAIN_ROWS, NUM_ROWS, PANE_PAD, SPLIT_L_W, SPLIT_R_W,
                       SCROLL_SPEED, TOP_ROWS, U, pad_ratio)
from .keypad import KeyPad, Touchpad, aspect
from .keys import KeyState
from .layouts import build_layout, load_layouts
from .schemes import SCHEMES, available_fonts, is_dark, scheme_by_id
from .styles import GHOST_CSS, SKIN_CSS, skin_colors
from .tabs import MAX_TABS, Tabs
from .terminal import LINK_REGEX_FLAGS, EntrySink, Terminal


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        # Заголовок короткий: он же подписывает окно в доке и в переключателе,
        # и длинная строка там просто обрезается.
        super().__init__(application=app, title="terkb")
        self.get_style_context().add_class("terkb-win")

        self.settings = load_settings()
        self.set_default_size(self.settings["width"], self.settings["height"])
        self.fonts = available_fonts()
        # Оформление хранит окно, а не терминал: терминалов теперь несколько,
        # и новая вкладка должна открываться с тем же шрифтом и той же схемой,
        # что и соседние.
        self.font_size = self.settings["font_size"]
        self.font_family = (self.settings["font"]
                            if self.settings["font"] in self.fonts
                            else "Monospace")
        self.scheme = None            # ставится set_scheme ниже
        # Вкладки: терминалы в стопке, кнопки — отдельной полосой в шапке.
        # Обратные вызовы навешиваем позже: они трогают состояние клавиатуры
        # и строку поиска, а тех ещё нет.
        self.tabs = Tabs()
        self.tabs.add(self.make_terminal())
        # Доля ширины под клавиатуру и её множитель: и то, и другое правится
        # кнопками ⌨−/⌨+ и переживает перезапуск.
        self.kb_fraction = self.settings["kb_fraction"]
        self.kb_scale = self.settings["kb_scale"]
        self.state = KeyState(self.term)
        self.kb = self.state          # для тестов и внешнего кода

        # Раскладки: свои из layout.json, если он есть, иначе встроенные.
        self.layouts = load_layouts()
        self.pad_left = KeyPad(self.state, SPLIT_L_W)
        build_layout(self.pad_left, "left", spec=self.layouts.get("left"))
        self.pad_right = KeyPad(self.state, SPLIT_R_W)
        # Полоса перемотки одна на все раскладки: она переезжает между сетками
        # вместе с переключением режима (mount_keyboard). Место, куда её
        # класть, каждая раскладка запомнила у себя в touchpad_at.
        self.touchpad = Touchpad(self.on_pad_drag)
        build_layout(self.pad_right, "right", self.touchpad,
                     self.layouts.get("right"))

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

        # Цельная раскладка для портрета. Живёт своим набором клавиш, а не
        # переставленными половинами: у неё другие ширины и другой цифровой
        # ряд. Состояние (модификаторы, Caps, язык, макросы) общее — оно
        # хранится в KeyState, куда клавиши прописываются при сборке.
        self.pad_full = KeyPad(self.state, FULL_W)
        build_layout(self.pad_full, "full", spec=self.layouts.get("full"))

        self.full_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.full_box.get_style_context().add_class("kb-pane")
        self.full_box.pack_start(aspect(self.pad_full,
                                        pad_ratio(FULL_W, FULL_ROWS)),
                                 True, True, 0)
        self.state.refresh_labels()     # после сборки всех трёх раскладок

        self.center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.bar = self.toolbar()
        self.center.pack_start(self.macro_editor(), False, False, 0)
        self.center.pack_start(self.search_bar(), False, False, 0)
        self.center.pack_start(self.tabs.stack, True, True, 0)
        self.state.on_macro_edit = self.edit_macro
        # Всё, чего касаются эти обработчики, собрано — можно подключать.
        self.tabs.on_switch = self.on_tab_switch
        self.tabs.on_change = self.on_tabs_changed
        self.tabs.on_empty = self.close

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

        # Панель во всю ширину окна, а не только над терминалом: в центральной
        # колонке кнопки лезли в две строки и жались, а её ширина ещё и
        # меняется вместе с разделителями. Заодно панель оказывается снаружи
        # оверлея — в режиме наложения половины физически не могут перекрыть
        # её своими GdkWindow.
        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.root.pack_start(self.bar, False, False, 0)
        # Полоса вкладок — под панелью, а не над ней: так кнопки остаются на
        # месте, когда вкладка открывается или закрывается.
        self.root.pack_start(self.tabs.strip, False, False, 0)
        self.root.pack_start(self.overlay, True, True, 0)
        self.add(self.root)

        self.ghost = False
        self.portrait = False     # ставится по форме окна, см. set_portrait
        self.hidden = False       # клавиатура убрана кнопкой «Скрыть ⌨»
        self.fullscreen_on = False   # своё имя: fullscreen() — метод GTK
        # Цветовая схема и плотность клавиш поверх терминала правятся на лету
        # кнопками панели, поэтому у них свой провайдер: базовую таблицу
        # перезагружать незачем.
        self.ghost_alpha = self.settings["ghost_alpha"]
        self.ghost_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.ghost_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
        gset = Gtk.Settings.get_default()
        self._prefer_dark = bool(gset and gset.get_property(
            "gtk-application-prefer-dark-theme"))
        self.set_scheme(self.settings["scheme"], save=False)
        self.set_font(self.font_family, save=False)
        for b in self.alpha_btns:
            b.set_sensitive(False)

        self._laid_out = (0, 0)   # размер, под который разложено
        self._retries = 0
        self._bar_h = 0           # высота панели, под которую разложено
        self.connect("size-allocate", self.on_alloc)
        self.bar.connect("size-allocate", self.on_bar_alloc)
        # Размер окна пишем не на каждое изменение, а один раз при закрытии:
        # иначе конфиг переписывался бы на каждый пиксель перетаскивания.
        self.connect("destroy", self.on_destroy)

        # Режимы восстанавливаем последними: кнопки уже собраны, дерево
        # виджетов готово, и обработчики сделают всю работу сами.
        if self.settings["fullscreen"]:
            self.fs_btn.set_active(True)
        if self.settings["hidden"]:
            self.hide_btn.set_active(True)
        elif self.settings["ghost"]:
            self.ghost_btn.set_active(True)

        self.state.refresh_macros()
        # Ускорители настоящей клавиатуры: обработчик на окне видит событие
        # раньше, чем оно уходит в терминал.
        self.connect("key-press-event", self.on_key)
        self.spawn(self.term)
        self.term.vte.grab_focus()

    # -- вкладки -------------------------------------------------------------
    @property
    def term(self):
        """Терминал открытой вкладки. Всё остальное окно работает с ним:
        клавиатура шлёт ввод сюда, поиск ищет здесь, полоса перемотки листает
        его."""
        return self.tabs.current

    def make_terminal(self):
        """Терминал с текущим оформлением: новая вкладка не должна отличаться
        от соседних ни шрифтом, ни цветами."""
        term = Terminal()
        term.font_family = self.font_family
        term.font_size = self.font_size
        term.apply_font()
        if self.scheme is not None:
            term.apply_scheme(self.scheme)
        return term

    def spawn(self, term):
        """Поднять шелл во вкладке. Вышел шелл — вкладка закрывается; была
        последняя — закрывается окно (это делает Tabs через on_empty)."""
        term.spawn(lambda t=term: self.tabs.close(t))

    def new_tab(self):
        if len(self.tabs.tabs) >= MAX_TABS:
            return
        term = self.make_terminal()
        self.tabs.add(term)
        self.spawn(term)
        term.vte.grab_focus()

    def close_tab(self):
        if self.term is not None:
            self.tabs.close(self.term)

    def on_tab_switch(self, old, new):
        """Перешли на другую вкладку."""
        if old is not None:
            old.vte.search_set_regex(None, 0)     # запрос был отдан ей
        if not isinstance(self.state.send, EntrySink):
            self.state.send = new                 # клавиатура печатает сюда
        if self.search_box.get_visible():
            self.search_apply()
        new.vte.grab_focus()

    def on_tabs_changed(self):
        """Вкладок стало больше или меньше: полоса появилась или исчезла, и
        клавиатуре досталось другое количество высоты."""
        self.new_btn.set_sensitive(len(self.tabs.tabs) < MAX_TABS)
        self._laid_out = (0, 0)
        self.schedule_layout()

    def on_key(self, _w, event):
        """Ускорители для настоящей клавиатуры.

        Экранной они не нужны — у неё есть кнопки панели, да и ввод она отдаёт
        VTE напрямую, мимо окна.
        """
        mods = event.state & Gtk.accelerator_get_default_mod_mask()
        ctrl = Gdk.ModifierType.CONTROL_MASK
        if mods == ctrl | Gdk.ModifierType.SHIFT_MASK:
            key = Gdk.keyval_to_lower(event.keyval)
            if key == Gdk.KEY_t:
                self.new_tab()
                return True
            if key == Gdk.KEY_w:
                self.close_tab()
                return True
        elif mods == ctrl:
            if event.keyval == Gdk.KEY_Page_Up:
                self.tabs.step(-1)
                return True
            if event.keyval == Gdk.KEY_Page_Down:
                self.tabs.step(1)
                return True
        return False

    def on_destroy(self, *_a):
        """Запомнить размер окна. В полном экране и в развёрнутом окне
        сохранять нечего: вернётся оно всё равно в те же границы, а записанный
        размер экрана потом мешал бы окну быть окном."""
        if not self.fullscreen_on and not self.is_maximized():
            w, h = self.get_size()
            self.store(width=w, height=h)

    def toolbar(self):
        # FlowBox, а не Box: минимальная ширина Box'а — это сумма всех кнопок,
        # и она становится полом для ширины терминала. С семью кнопками
        # разделитель переставал двигаться. FlowBox переносит их на вторую
        # строку, и минимум равен ширине одной кнопки.
        bar = Gtk.FlowBox()
        bar.get_style_context().add_class("terkb-bar")
        # Свой класс поверх общего: цвета схемы приходят из .terkb-bar, а
        # размер значков — только сюда, полосы вкладок он не касается.
        bar.get_style_context().add_class("terkb-tools")
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

        self.new_btn = btn("＋", self.new_tab,
                           "Новая вкладка (Ctrl+Shift+T). Между вкладками — "
                           "их полоса под панелью или Ctrl+PgUp/PgDn")

        btn("A−", lambda: self.zoom_font(-1), "Шрифт терминала мельче")
        btn("A+", lambda: self.zoom_font(1), "Шрифт терминала крупнее")

        # Циклеры: на планшете выбирать пункт списка пальцем неудобно, а одна
        # кнопка и попадается легко, и листает по кругу. Что выбрано сейчас,
        # написано в подсказке — её ставят set_scheme и set_font.
        #
        # Кисть, а не палитра (🎨): палитра рисуется только цветным эмодзи и
        # выбивалась из ряда, а кисть с текстовым селектором (U+FE0E, после
        # знака его не видно) идёт обычным глифом и красится в цвет подписей.
        self.scheme_btn = btn("🖌︎", self.next_scheme, "")
        self.font_btn = btn("Aa", self.next_font, "")
        if len(self.fonts) < 2:
            self.font_btn.set_sensitive(False)

        self.kb_scale_btns = [
            btn("⌨−", lambda: self.zoom_kb(-KB_SCALE_STEP),
                "Клавиатуру меньше"),
            btn("⌨+", lambda: self.zoom_kb(KB_SCALE_STEP),
                "Клавиатуру больше"),
        ]

        self.alpha_btns = [
            btn("◐−", lambda: self.fade_kb(GHOST_ALPHA_STEP),
                "Клавиши плотнее (меньше прозрачности)"),
            btn("◐+", lambda: self.fade_kb(-GHOST_ALPHA_STEP),
                "Клавиши прозрачнее"),
        ]

        self.ghost_btn = Gtk.ToggleButton(label="⧉")
        self.ghost_btn.set_tooltip_text(
            "Поверх: терминал во всю ширину, клавиши прозрачные поверх него")
        self.ghost_btn.connect("toggled", self.on_ghost)
        place(self.ghost_btn)

        # Стрелка показывает, куда уедет клавиатура: вниз — убрать, вверх —
        # вернуть. Подпись переставляет set_hidden.
        self.hide_btn = Gtk.ToggleButton(label="⌨↓")
        self.hide_btn.set_tooltip_text(
            "Убрать клавиатуру совсем: терминал на всё окно")
        self.hide_btn.connect("toggled", self.on_hide_kb)
        place(self.hide_btn)

        # Тот же текстовый селектор, что и у кисти: без него лупа приезжает
        # цветным эмодзи и не красится вместе с остальной панелью.
        self.search_btn = Gtk.ToggleButton(label="🔍︎")
        self.search_btn.set_tooltip_text("Искать по выводу терминала")
        self.search_btn.connect("toggled", self.on_search)
        place(self.search_btn)

        # На 10-дюймовом экране заголовок окна — это полсотни отъеденных
        # пикселей и лишний повод промахнуться мимо верхнего ряда клавиш.
        self.fs_btn = Gtk.ToggleButton(label="⛶")
        self.fs_btn.set_tooltip_text("Во весь экран, без заголовка окна")
        self.fs_btn.connect("toggled", self.on_fullscreen)
        place(self.fs_btn)
        return bar

    def on_fullscreen(self, btn):
        self.set_fullscreen(btn.get_active())
        self.term.vte.grab_focus()

    def set_fullscreen(self, on):
        self.fullscreen_on = on
        if on:
            self.fullscreen()
        else:
            self.unfullscreen()
        self.store(fullscreen=on)

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
                # бы касания у верхних строк терминала.
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
        self.update_mode_buttons()
        self.store(ghost=on)
        self._laid_out = (0, 0)   # заставить пересчитать
        self.schedule_layout()

    # -- раскладка окна: поворот и скрытие ----------------------------------
    def mount_keyboard(self):
        """Повесить в дерево ту клавиатуру, которая сейчас нужна.

        Все три раскладки собраны при запуске, поэтому переключение режима —
        это только перевешивание виджетов. Пересобирать нечего: состояние
        (модификаторы, Caps, язык, макросы) общее и живёт в KeyState.
        """
        for box in (self.left_box, self.right_box, self.full_box):
            parent = box.get_parent()
            if parent is not None:
                parent.remove(box)
        if self.hidden:
            return
        if self.portrait:
            self.move_touchpad(self.pad_full)
            self.center.pack_end(self.full_box, False, False, 0)
            self.full_box.show_all()
        else:
            self.move_touchpad(self.pad_right)
            # порядок важен: pack1 у outer, pack2 у inner
            self.outer.pack1(self.left_box, False, False)
            self.inner.pack2(self.right_box, False, False)
            self.left_box.show_all()
            self.right_box.show_all()

    def move_touchpad(self, pad):
        """Перевесить полосу перемотки в нужную раскладку.

        Полоса одна на все три: у неё свой GdkWindow и жест перетаскивания, и
        держать по копии на раскладку — значит держать копии состояния.
        """
        if self.touchpad.get_parent() is pad:
            return
        parent = self.touchpad.get_parent()
        if parent is not None:
            parent.remove(self.touchpad)
        pad.add_widget(self.touchpad, *pad.touchpad_at)
        self.touchpad.show_all()

    def update_mode_buttons(self):
        """Что можно нажать в текущем режиме.

        Без клавиатуры нечего накладывать и нечего масштабировать; в портрете
        размер задан шириной окна, а терминал и так во всю ширину. Прозрачность
        видна только под наложением.
        """
        live = not self.portrait and not self.hidden
        self.ghost_btn.set_sensitive(live)
        for b in self.kb_scale_btns:
            b.set_sensitive(live)
        for b in self.alpha_btns:
            b.set_sensitive(self.ghost and not self.hidden)

    def set_portrait(self, on):
        """Переключить раскладку под форму окна."""
        self.portrait = on
        # Наложение в портрете смысла не имеет: клавиатура и так внизу, а
        # терминал над ней во всю ширину.
        if on and self.ghost:
            self.ghost_btn.set_active(False)          # снимет режим наложения
        self.mount_keyboard()
        self.update_mode_buttons()
        self._laid_out = (0, 0)

    def on_hide_kb(self, btn):
        self.set_hidden(btn.get_active())
        self.term.vte.grab_focus()

    def set_hidden(self, on):
        """Убрать клавиатуру совсем: терминал на всё окно.

        Нужно, когда на планшет подключили настоящую клавиатуру или когда
        надо посмотреть длинный вывод целиком — в отличие от наложения, здесь
        экран не занят даже полупрозрачными клавишами.
        """
        self.hidden = on
        if on and self.ghost:
            self.ghost_btn.set_active(False)
        self.mount_keyboard()
        self.update_mode_buttons()
        self.hide_btn.set_label("⌨↑" if on else "⌨↓")
        self.hide_btn.set_tooltip_text(
            "Вернуть клавиатуру" if on
            else "Убрать клавиатуру совсем: терминал на всё окно")
        self.store(hidden=on)
        self._laid_out = (0, 0)
        self.schedule_layout()

    def full_key(self, w, h):
        """Размер клавиши цельной раскладки: по ширине окна, с потолком по
        высоте — иначе на узком экране терминал ужимается в пару строк."""
        key = (w - PANE_PAD) / FULL_W * U
        if h > 50:
            key = min(key, (h * FULL_MAX_H - PANE_PAD) / FULL_ROWS
                      / KEY_STRETCH)
        return max(1.0, key)

    def key_size(self, w, h):
        """Размер клавиши, общий для обеих половин.

        Один размер на обе — иначе клавиши слева и справа разъедутся. По
        высоте тоже ограничиваем, иначе AspectFrame ужмёт половины по-разному.
        """
        cols = SPLIT_L_W + SPLIT_R_W
        key = w * self.kb_fraction * self.kb_scale / cols * U
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

    # -- поиск по выводу -----------------------------------------------------
    def search_bar(self):
        """Строка поиска. Устроена как строка правки макроса: встроена в окно,
        а не диалогом, и на время поиска забирает ввод с экранной клавиатуры —
        иначе набирать запрос было бы нечем."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.get_style_context().add_class("kb-editor")
        box.pack_start(Gtk.Label(label="🔍"), False, False, 0)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_width_chars(6)
        self.search_entry.set_placeholder_text("что искать")
        self.search_entry.connect("changed", lambda *_a: self.search_apply())
        box.pack_start(self.search_entry, True, True, 0)

        for label, tip, cb in (("↑", "Раньше в выводе", self.search_prev),
                               ("↓", "Позже в выводе", self.search_next),
                               ("✕", "Закрыть поиск", self.search_close)):
            b = Gtk.Button(label=label)
            b.set_can_focus(False)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _b, f=cb: f())
            box.pack_start(b, False, False, 0)

        box.set_no_show_all(True)
        self.search_box = box
        return box

    def on_search(self, btn):
        if btn.get_active():
            self.search_open()
        else:
            self.search_close()

    def search_open(self):
        self.search_box.show()
        for w in self.search_box.get_children():
            w.show()
        self.search_entry.grab_focus()
        self.state.send = EntrySink(self.search_entry, self.search_prev,
                                    self.search_close)
        self.search_apply()

    def search_close(self):
        self.search_box.hide()
        self.term.vte.search_set_regex(None, 0)
        self.state.send = self.term          # ввод снова идёт в терминал
        self.search_btn.set_active(False)
        self.term.vte.grab_focus()

    def search_apply(self):
        """Отдать VTE текущий запрос. Ищем как простой текст: регулярное
        выражение на экранной клавиатуре никто набирать не станет."""
        text = self.search_entry.get_text()
        vte = self.term.vte
        if not text:
            vte.search_set_regex(None, 0)
            return
        try:
            regex = Vte.Regex.new_for_search(
                GLib.Regex.escape_string(text, -1), -1, LINK_REGEX_FLAGS)
        except (AttributeError, GLib.Error):
            return
        vte.search_set_regex(regex, 0)
        vte.search_set_wrap_around(True)

    def search_prev(self):
        """Предыдущее совпадение — то есть раньше в выводе, выше по экрану."""
        self.search_apply()
        self.term.vte.search_find_previous()

    def search_next(self):
        self.search_apply()
        self.term.vte.search_find_next()

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

    # -- оформление ---------------------------------------------------------
    def apply_ghost_css(self):
        """Перезагрузить динамическую таблицу.

        Имя историческое: сначала здесь была только плотность клавиш в режиме
        наложения, теперь оттуда же приходят цвета схемы. У «Системы» своих
        цветов нет — работает прежняя таблица поверх темы GTK.
        """
        if self.scheme["bg"] is None:
            css = GHOST_CSS % {"a": self.ghost_alpha}
        else:
            css = SKIN_CSS % skin_colors(self.scheme, self.ghost_alpha)
        self.ghost_provider.load_from_data(css.encode())

    def set_scheme(self, ident, save=True):
        self.scheme = scheme_by_id(ident) or SCHEMES[0]
        for term in self.tabs.terms:      # схема одна на все вкладки
            term.apply_scheme(self.scheme)
        self.apply_ghost_css()
        # Системные виджеты (выпадашки, тултипы, курсор в поле правки) нашей
        # таблицей не покрыты — им остаётся сказать только, светлая схема или
        # тёмная. У «Системы» возвращаем то, что стояло до запуска.
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property(
                "gtk-application-prefer-dark-theme",
                self._prefer_dark if self.scheme["bg"] is None
                else is_dark(self.scheme))
        # Название схемы — только в подсказке: на кнопке значок, а какая схема
        # выбрана, и так видно по цвету окна.
        self.scheme_btn.set_tooltip_text(
            "Схема: %s. Нажать — следующая" % self.scheme["name"])
        if save:
            self.store(scheme=self.scheme["id"])

    def next_scheme(self):
        ids = [s["id"] for s in SCHEMES]
        self.set_scheme(ids[(ids.index(self.scheme["id"]) + 1) % len(ids)])
        self.term.vte.grab_focus()

    def set_font(self, family, save=True):
        self.font_family = family
        for term in self.tabs.terms:      # шрифт один на все вкладки
            term.set_font_family(family)
        # Название шрифта — только в подсказке: полное имя вроде «JetBrains
        # Mono» в кнопку не влезало и обрезалось, а слово Mono у всех
        # одинаковое и ничего не различало.
        self.font_btn.set_tooltip_text(
            "Шрифт: %s. Нажать — следующий" % family)
        if save:
            self.store(font=family)

    def next_font(self):
        if len(self.fonts) < 2:
            return
        cur = self.font_family
        i = self.fonts.index(cur) + 1 if cur in self.fonts else 0
        self.set_font(self.fonts[i % len(self.fonts)])
        self.term.vte.grab_focus()

    def zoom_font(self, delta):
        # Размер меняем во всех вкладках сразу, а границы оставляем терминалу:
        # они у него уже есть, и на упоре все вкладки останутся вровень.
        for term in self.tabs.terms:
            term.zoom(delta)
        self.font_size = self.term.font_size
        self.store(font_size=self.font_size)
        self.term.vte.grab_focus()

    def store(self, **kw):
        self.settings.update(kw)
        save_settings(self.settings)

    def fade_kb(self, delta):
        """Изменить плотность клавиш в режиме наложения."""
        a = min(GHOST_ALPHA_MAX, max(GHOST_ALPHA_MIN, self.ghost_alpha + delta))
        if abs(a - self.ghost_alpha) < 1e-9:
            return
        self.ghost_alpha = a
        self.apply_ghost_css()
        self.store(ghost_alpha=a)
        self.term.vte.grab_focus()

    def strip_height(self, widget, w):
        """Высота полосы в шапке. До первого размещения аллокации ещё нет, а
        считать по ней нельзя: раскладка сойдётся на заниженной высоте панели,
        клавиши получатся крупнее, чем влезает, и половины разъедутся — у левой
        рядов больше, и AspectFrame ужмёт её сильнее правой. Поэтому спрашиваем
        предпочтительную высоту под известную ширину."""
        h = widget.get_allocation().height
        if h > 1:
            return h
        return widget.get_preferred_height_for_width(max(1, w))[1]

    def bar_height(self, w):
        """Высота всей шапки: панель кнопок и, если вкладок больше одной, их
        полоса."""
        h = self.strip_height(self.bar, w)
        if self.tabs.strip.get_visible():
            h += self.strip_height(self.tabs.strip, w)
        return h

    def avail_height(self, w, h):
        """Высота, доступная клавиатуре.

        h — высота всего окна, а шапка лежит над клавиатурой во всю ширину,
        и в обычном режиме, и в наложении.
        """
        return h - self.bar_height(w)

    def on_bar_alloc(self, _w, alloc):
        """Панель переехала на другое число строк — клавиатуре досталось
        больше или меньше высоты, надо пересчитать."""
        if alloc.height != self._bar_h:
            self._bar_h = alloc.height
            self._laid_out = (0, 0)
            self.schedule_layout()

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
            h = self.avail_height(a.width, a.height)
            before = self.key_size(a.width, h)
            prev, self.kb_scale = self.kb_scale, scale
            if self.key_size(a.width, h) <= before + 0.01:
                self.kb_scale = prev
                return
        else:
            self.kb_scale = scale
        self.store(kb_scale=self.kb_scale)
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
        avail = self.avail_height(w, h)
        if self.hidden:
            # клавиатуры в дереве нет, размеры считать не для кого
            return {"w": w, "h": h}
        if self.portrait:
            key = self.full_key(w, avail)
            return {"w": w, "h": h, "fh": self.half_height(key, FULL_ROWS)}
        key = self.key_size(w, avail)
        return {
            "w": w, "h": h,
            "lw": int(key * SPLIT_L_W / U) + PANE_PAD,
            "rw": int(key * SPLIT_R_W / U) + PANE_PAD,
            "lh": self.half_height(key, NUM_ROWS + MAIN_ROWS),
            "rh": self.half_height(key, TOP_ROWS + MAIN_ROWS),
        }

    def relayout(self, width=None, height=None):
        """Применить раскладку. False — размеры ещё не готовы."""
        self.check_orientation(width, height)
        t = self.targets(width, height)
        if t is None:
            return False
        if self.hidden:
            # Пустая сторона Paned всё равно держит позицию разделителя —
            # без этого терминал остался бы прежней ширины с пустотой по краям.
            self.outer.set_position(0)
            self.inner.set_position(t["w"])
        elif self.portrait:
            # Клавиатуре — своя высота, остальное забирает терминал. Ширину не
            # трогаем: цельная раскладка идёт во всю ширину окна.
            self.full_box.set_size_request(-1, t["fh"])
        elif self.ghost:
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

    def check_orientation(self, width=None, height=None):
        """Портрет или альбом — по форме окна, а не по монитору.

        Композитор поворачивает экран, окно приезжает узким и высоким; тот же
        признак работает и когда окно просто вытянули мышью. Квадрат остаётся
        за альбомом: в нём сплит ещё помещается.
        """
        a = self.root.get_allocation()
        w = width if width is not None else a.width
        h = height if height is not None else a.height
        if w <= 100 or h <= 100:
            return
        want = h > w
        if want != self.portrait:
            self.set_portrait(want)

    def layout_ok(self):
        """Приняло ли GTK выставленные размеры."""
        t = self.targets()
        if t is None:
            return False
        if self.hidden:
            return True
        if self.portrait:
            return abs(self.full_box.get_allocation().height - t["fh"]) <= 2
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
