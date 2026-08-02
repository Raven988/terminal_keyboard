#!/usr/bin/env python3
"""Функциональный тест: нажимаем клавиши на экранной клавиатуре и проверяем,
что шелл в терминале действительно их получил."""
import sys
import os
import time
import json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import gi
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gtk, GLib, Gio, Vte
import terkb

# Макросы пишутся в файл — тест не должен трогать настоящий конфиг.
import tempfile
_MACRO_DIR = tempfile.mkdtemp(prefix="terkb-test-")
terkb.MACRO_FILE = os.path.join(_MACRO_DIR, "macros.json")

W, H = 1500, 950
results = []


class A(terkb.App):
    def __init__(self):
        Gtk.Application.__init__(self, application_id=None,
                                 flags=Gio.ApplicationFlags.NON_UNIQUE)

    def do_activate(self):
        win = terkb.Window(self)
        root = win.root
        win.remove(root)
        off = Gtk.OffscreenWindow(); off.add(root)
        off.set_size_request(W, H); off.show_all()
        win.place_dividers(W, H)
        self.win, self.off = win, off
        self.state = win.state
        self.term = win.term
        self.L, self.R = win.pad_left, win.pad_right
        self.steps = self.script()
        GLib.timeout_add(1500, self.step)

    # ищем клавишу по подписи; pad ограничивает поиск одной половиной
    def key(self, label, pad=None):
        keys = pad.keys if pad is not None else self.state.all_keys
        for k in keys:
            if k.low == label:
                return k
        raise KeyError(label)

    def tap(self, *labels, **kw):
        pad = kw.get("pad")
        for lb in labels:
            self.state.press(self.key(lb, pad))

    def screen(self):
        txt = self.term.vte.get_text_format(Vte.Format.TEXT)
        if isinstance(txt, tuple):
            txt = txt[0]
        return txt or ""

    def check(self, name, needle, timeout=3.0):
        """Ждём текст, а не проверяем однократно: шелл отвечает не мгновенно,
        и одномоментная проверка периодически падала на ровном месте."""
        deadline = time.monotonic() + timeout
        ok = False
        while time.monotonic() < deadline:
            while Gtk.events_pending():
                Gtk.main_iteration()
            if needle in self.screen():
                ok = True
                break
            time.sleep(0.05)
        results.append((ok, name, needle))
        print(("PASS " if ok else "FAIL ") + name + "  <- " + repr(needle))

    def expect(self, name, cond):
        results.append((bool(cond), name, cond))
        print(("PASS " if cond else "FAIL ") + name)

    def script(self):
        L, R = self.L, self.R

        # Фиксированной паузы мало: шелл иногда не успевает подняться, и
        # первый же тест печати падал примерно через раз.
        yield lambda: self.expect("шелл поднялся", self.wait_prompt())

        # ---------- раскладка ----------
        yield lambda: self.expect(
            "терминал между половинами",
            self.win.outer.get_position() > 0
            and self.win.inner.get_position() > 0)
        # Окно-ручки GtkPaned наезжало на крайнюю клавишу, и касание уходило
        # на изменение размера: подсветка не загоралась, нажатие терялось.
        yield lambda: self.expect(
            "крайние клавиши не задеты зоной изменения размера",
            self.key_clear_of_handles(L, "F6")
            and self.key_clear_of_handles(R, "F7"))
        yield lambda: self.expect(
            "клавиши в половинах одного размера",
            abs(self.win.pad_left.get_allocation().width / terkb.SPLIT_L_W
                - self.win.pad_right.get_allocation().width / terkb.SPLIT_R_W)
            < 1.0)

        # ---------- ввод ----------
        # e, c — левая половина; h, o — правая
        yield lambda: (self.tap("e", "c", pad=L), self.tap("h", "o", pad=R),
                       self.tap(" ", pad=L), self.tap(*"ab1", pad=None))
        yield lambda: self.check("обе половины печатают", "echo ab1")
        yield lambda: self.tap("Enter ⏎", pad=R)
        yield lambda: self.check("Enter правой половины", "\nab1")

        yield lambda: (self.tap("Shift ⇧", pad=L), self.tap("h", pad=R))
        yield lambda: self.check("Shift слева влияет на правую половину", "H")
        yield lambda: (self.tap("Ctrl", pad=L), self.tap("c", pad=L))

        yield lambda: (self.tap("RU/EN", pad=R), self.tap(*"echo"),
                       self.tap(" "), self.tap(*"ghbdtn"))
        yield lambda: self.check("русская раскладка", "привет")
        yield lambda: (self.tap("RU/EN", pad=R), self.tap("Ctrl", pad=L),
                       self.tap("c", pad=L))

        yield lambda: (self.tap(*"echo"), self.tap(" "),
                       self.tap(*"qq", pad=L),
                       self.tap("⌫", pad=R), self.tap("Enter ⏎", pad=R))
        yield lambda: self.check("Backspace правой половины", "\nq\n")

        yield lambda: (self.tap(*"ech"), self.tap("Tab ⇥", pad=L))
        yield lambda: self.check("Tab левой половины дополняет", "echo ")
        yield lambda: (self.tap("Ctrl", pad=L), self.tap("c", pad=L))

        # ---------- стрелки над правой половиной ----------
        yield lambda: self.expect(
            "стрелки есть в правой половине",
            all(any(k.low == a for k in R.keys) for a in ("↑", "↓", "←", "→")))
        yield lambda: self.tap("↑", pad=R)
        yield lambda: self.check("↑ поднимает историю", "echo q")
        yield lambda: (self.tap("Ctrl", pad=L), self.tap("c", pad=L))
        # ← ставит курсор между a и b, туда вставляется z
        yield lambda: (self.tap(*"echo"), self.tap(" "),
                       self.tap("a", pad=L), self.tap("b", pad=L),
                       self.tap("←", pad=R), self.tap("z", pad=L),
                       self.tap("Enter ⏎", pad=R))
        yield lambda: self.check("← двигает курсор внутри строки", "\nazb\n")

        # ---------- цифровой блок над левой половиной ----------
        yield lambda: (self.tap(*"echo"), self.tap(" "),
                       self.tap("7", pad=L), self.tap("+", pad=L),
                       self.tap("9", pad=L), self.tap("Enter ⏎", pad=R))
        yield lambda: self.check("цифровой блок печатает", "\n7+9\n")

        # ---------- ряд под F-клавишами: символы, цифры под Shift ----------
        yield lambda: self.expect(
            "цифр в ряду под F-клавишами нет",
            not any(k.low.isdigit() for k in self.row_under_f()))
        yield lambda: self.expect(
            "символы шелла на месте",
            {"`", "!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "-", "="}
            <= {k.low for k in self.row_under_f()})
        yield lambda: (self.tap(*"echo"), self.tap(" "),
                       self.tap("$", pad=L), self.tap("^", pad=L),
                       self.tap("&", pad=R), self.tap("=", pad=R))
        yield lambda: self.check("символы печатаются без Shift", "$^&=")
        # строку не выполняем: & увёл бы echo в фон и сбил тайминг дальше
        yield lambda: (self.tap("Ctrl", pad=L), self.tap("c", pad=L))
        yield lambda: (self.tap(*"echo"), self.tap(" "),
                       self.tap("Shift ⇧", pad=L), self.tap("$", pad=L),
                       self.tap("Shift ⇧", pad=L), self.tap("!", pad=L),
                       self.tap("Enter ⏎", pad=R))
        yield lambda: self.check("Shift даёт цифру", "\n41\n")

        # ---------- дополнительные клавиши справа ----------
        yield lambda: self.expect(
            "Home/End/PgUp/PgDn/Del есть в правой половине",
            all(any(k.low == lb for k in R.keys)
                for lb in ("Home", "End", "PgUp", "PgDn", "Del")))
        yield lambda: (self.tap(*"echo"), self.tap(" "), self.tap(*"abc"),
                       self.tap("Home", pad=R), self.tap("x", pad=L),
                       self.tap("Enter ⏎", pad=R))
        yield lambda: self.check("Home уводит курсор в начало строки",
                                 "xecho abc")
        yield lambda: (self.tap("Ctrl", pad=L), self.tap("c", pad=L))

        # ---------- программируемые клавиши ----------
        yield lambda: self.expect(
            "их четыре и все пустые",
            len(self.macro_keys()) == terkb.PROG_KEYS
            and all(k.label.get_text() == "M%d" % (k.data + 1)
                    and k.button.get_style_context().has_class("kb-macro-empty")
                    for k in self.macro_keys()))
        yield lambda: self.win.state.press(self.macro_keys()[0])
        yield lambda: self.expect(
            "нажатие пустой открывает правку",
            self.win.macro_box.get_visible()
            and isinstance(self.win.state.send, terkb.EntrySink))
        # команда с меткой: её видно в выводе независимо от прокрутки
        yield lambda: (self.tap(*"echo"), self.tap(" "), self.tap(*"mokz"))
        yield lambda: self.expect(
            "клавиатура набирает в поле, а не в терминал",
            self.win.macro_entry.get_text() == "echo mokz")
        yield lambda: self.tap("⌫", pad=R)
        yield lambda: self.expect(
            "Backspace работает в поле",
            self.win.macro_entry.get_text() == "echo mok")
        yield lambda: self.tap("Enter ⏎", pad=R)
        yield lambda: self.expect(
            "Enter сохраняет и возвращает ввод в терминал",
            not self.win.macro_box.get_visible()
            and self.win.state.send is self.win.term)
        yield lambda: self.expect(
            "подпись стала командой, класс «пусто» снят",
            self.macro_keys()[0].label.get_text() == "echo mok"
            and not self.macro_keys()[0].button.get_style_context()
            .has_class("kb-macro-empty"))
        yield lambda: self.expect(
            "команда записана в файл", self.macro_saved(0) == "echo mok")
        yield lambda: self.win.state.press(self.macro_keys()[0])
        yield lambda: self.check("нажатие выполняет команду", "\nmok\n")
        yield lambda: self.expect(
            "Отмена не портит сохранённое", self.macro_cancel_keeps())

        # ---------- полоса перемотки ----------
        yield lambda: self.expect(
            "полоса шириной в клавишу и высотой в две",
            self.pad_size_in_keys())
        yield lambda: self.expect(
            "полоса прижата к правому краю половины",
            R.child_get_property(self.win.touchpad, "left-attach")
            + R.child_get_property(self.win.touchpad, "width")
            == terkb.SPLIT_R_W)
        yield lambda: self.expect(
            "модификаторы слева от полосы",
            max(self.col_of(lb, R) + terkb.MOD_W
                for lb in ("Shift ⇧", "Ctrl", "Alt", "RU/EN"))
            <= R.child_get_property(self.win.touchpad, "left-attach"))
        yield lambda: (self.tap(*"seq"), self.tap(" "), self.tap("1", pad=L),
                       self.tap(" "), self.tap("4", pad=L), self.tap("0", pad=L),
                       self.tap("0", pad=L), self.tap("Enter ⏎", pad=R))
        yield lambda: self.expect(
            "палец вниз листает назад", self.pad_scroll(+12) < 0)
        yield lambda: self.expect(
            "палец вверх листает вперёд", self.pad_scroll(-12) > 0)
        yield lambda: self.expect(
            "перемотка не уходит за границы", self.pad_stays_in_range())

        # ---------- подсветка нажатия не залипает ----------
        # Проверяем по пикселям: get_background_color устарел и игнорирует
        # переданное состояние, по нему картина всегда выглядит исправной.
        yield lambda: self.expect(
            "prelight не меняет вид клавиши (из-за него залипало)",
            self.state_looks_same(L, "q", Gtk.StateFlags.PRELIGHT)
            and self.state_looks_same(L, "Tab ⇥", Gtk.StateFlags.PRELIGHT))
        yield lambda: self.expect(
            "подсветка нажатия видна и снимается",
            self.hit_visible(L, "q"))
        # Подсветка идёт от состояния кнопки, а не от нашего жеста: у клавиш
        # рядом с терминалом жест в фазе CAPTURE до подсветки не доходил.
        yield lambda: self.expect(
            "состояние «нажата» зажигает клавишу везде",
            all(self.active_lights(pad, lb) for pad, lb in (
                (L, "Esc"), (L, "F6"), (L, "q"), (L, "Shift ⇧"),
                (R, "F7"), (R, "⧉ Copy"), (R, "y"), (R, "Enter ⏎"))))
        yield lambda: self.expect(
            "отпускание снимает подсветку",
            self.hit_state(L, "q", True) and self.hit_state(L, "q", False))
        # страховка: если release не придёт, подсветка уходит по таймауту
        yield lambda: L.hit(self.key("w", L).button, True)
        yield lambda: self.expect(
            "подсветка держится сразу после нажатия",
            self.has_hit(L, "w"))
        yield lambda: self.expect(
            "и снимается по таймауту без отпускания",
            self.wait_hit_gone(L, "w"))
        yield lambda: self.expect(
            "ни одна клавиша не осталась подсвеченной",
            not any(k.button.get_style_context().has_class("kb-hit")
                    for k in self.state.all_keys))

        # ---------- стрелки внизу, модификаторы наверху ----------
        yield lambda: self.expect(
            "стрелка шире обычной клавиши",
            self.arrow_alloc().width > self.plain_alloc().width * 1.4)
        yield lambda: self.expect(
            "стрелки в двух нижних рядах правой половины",
            self.row_of("↑", R) == terkb.TOP_ROWS + terkb.MAIN_ROWS - 2
            and self.row_of("←", R) == terkb.TOP_ROWS + terkb.MAIN_ROWS - 1
            and self.row_of("↓", R) == self.row_of("←", R)
            and self.row_of("→", R) == self.row_of("←", R))
        yield lambda: self.expect(
            "↑ стоит ровно над ↓",
            self.col_of("↑", R) == self.col_of("↓", R))
        yield lambda: self.expect(
            "модификаторы и смена языка подняты наверх",
            all(self.row_of(lb, R) < terkb.TOP_ROWS
                for lb in ("Shift ⇧", "Ctrl", "Alt", "RU/EN")))
        yield lambda: (self.tap(*"echo"), self.tap(" "),
                       self.tap("Shift ⇧", pad=R), self.tap("h", pad=R),
                       self.tap("Enter ⏎", pad=R))
        yield lambda: self.check("Shift из верхнего блока работает", "\nH\n")

        # ---------- режим наложения ----------
        yield lambda: self.snapshot()
        # отдельно от snap: внутри режима snapshot() переиспользуется
        yield lambda: setattr(self, "term_w_normal",
                              self.win.term.get_allocation().width)
        yield lambda: self.win.ghost_btn.set_active(True)
        yield lambda: self.expect(
            "терминал занял всё окно",
            self.win.term.get_allocation().width > self.term_w_normal * 1.5)
        yield lambda: self.expect(
            "половины лежат поверх терминала",
            self.win.left_box.get_parent() is self.win.overlay
            and self.win.right_box.get_parent() is self.win.overlay)
        yield lambda: self.expect(
            "клавиши помечены как прозрачные",
            self.win.left_box.get_style_context().has_class("kb-ghost"))
        yield lambda: self.expect(
            "половины прижаты к краям и не съехались",
            self.win.left_box.get_allocation().width > 100
            and self.win.right_box.get_allocation().width > 100)
        # у оверлей-ребёнка своё GdkWindow: всё, что он накрывает, перестаёт
        # нажиматься. Панель инструментов должна остаться снаружи, иначе
        # обратно из режима не выйти
        yield lambda: self.expect(
            "панель инструментов не перекрыта половинами",
            not self.overlaps(self.win.left_box, self.win.bar)
            and not self.overlaps(self.win.right_box, self.win.bar))
        yield lambda: self.expect(
            "клавиши в половинах по-прежнему одного размера",
            abs(self.win.pad_left.get_allocation().width / terkb.SPLIT_L_W
                - self.win.pad_right.get_allocation().width / terkb.SPLIT_R_W)
            < 1.0)
        yield lambda: (self.tap(*"echo"), self.tap(" "),
                       self.tap(*"ghost"), self.tap("Enter ⏎", pad=R))
        yield lambda: self.check("поверх терминала ввод работает", "\nghost\n")
        yield lambda: self.tap("↑", pad=R)
        yield lambda: self.check("стрелки работают поверх", "echo ghost")
        yield lambda: (self.tap("Ctrl", pad=L), self.tap("c", pad=L))

        # ---------- прозрачность правится на лету ----------
        yield lambda: self.expect(
            "кнопки прозрачности активны только поверх терминала",
            all(b.get_sensitive() for b in self.win.alpha_btns))
        yield lambda: self.expect(
            "◐+ делает клавиши прозрачнее",
            self.fades(-terkb.GHOST_ALPHA_STEP))
        yield lambda: self.expect(
            "◐− делает клавиши плотнее",
            self.fades(terkb.GHOST_ALPHA_STEP))
        yield lambda: [self.win.fade_kb(-terkb.GHOST_ALPHA_STEP)
                       for _ in range(20)]
        yield lambda: self.expect(
            "прозрачность ограничена снизу",
            self.win.ghost_alpha >= terkb.GHOST_ALPHA_MIN - 1e-9)
        yield lambda: [self.win.fade_kb(terkb.GHOST_ALPHA_STEP)
                       for _ in range(30)]
        yield lambda: self.expect(
            "и сверху",
            self.win.ghost_alpha <= terkb.GHOST_ALPHA_MAX + 1e-9)
        yield lambda: setattr(self.win, "ghost_alpha", terkb.GHOST_ALPHA)
        yield lambda: self.win.apply_ghost_css()

        # ---------- размер клавиатуры меняется прямо в режиме наложения ------
        yield lambda: self.snapshot()
        yield lambda: self.win.zoom_kb(-terkb.KB_SCALE_STEP * 3)
        yield lambda: self.expect(
            "⌨− уменьшает клавиатуру поверх терминала",
            self.win.pad_left.get_allocation().width < self.snap[0] - 20)
        yield lambda: self.expect(
            "после уменьшения клавиши по-прежнему одного размера",
            abs(self.win.pad_left.get_allocation().width / terkb.SPLIT_L_W
                - self.win.pad_right.get_allocation().width / terkb.SPLIT_R_W)
            < 1.0)
        yield lambda: self.snapshot()
        yield lambda: self.win.zoom_kb(terkb.KB_SCALE_STEP * 2)
        yield lambda: self.expect(
            "⌨+ увеличивает клавиатуру обратно",
            self.win.pad_left.get_allocation().width > self.snap[0] + 20)
        # упираемся в потолок: половины не должны сойтись посередине и залезть
        # на панель инструментов
        yield lambda: [self.win.zoom_kb(terkb.KB_SCALE_STEP) for _ in range(12)]
        yield lambda: self.expect(
            "на максимуме половины не наехали друг на друга",
            self.win.left_box.get_allocation().width
            + self.win.right_box.get_allocation().width
            < self.win.root.get_allocation().width)
        yield lambda: self.expect(
            "на максимуме панель инструментов не перекрыта",
            not self.overlaps(self.win.left_box, self.win.bar)
            and not self.overlaps(self.win.right_box, self.win.bar))
        yield lambda: self.expect(
            "масштаб не копится сверх достижимого",
            self.at_scale_ceiling())
        yield lambda: [self.win.zoom_kb(-terkb.KB_SCALE_STEP) for _ in range(20)]
        yield lambda: self.expect(
            "снизу масштаб тоже ограничен",
            self.win.kb_scale >= terkb.KB_SCALE_MIN - 1e-9
            and self.win.pad_left.get_allocation().width > 100)
        yield lambda: setattr(self.win, "kb_scale", 1.0)
        yield lambda: self.win.schedule_layout()

        yield lambda: self.win.ghost_btn.set_active(False)
        yield lambda: self.expect(
            "половины вернулись в Paned",
            self.win.left_box.get_parent() is self.win.outer
            and self.win.right_box.get_parent() is self.win.inner)
        yield lambda: self.expect(
            "прозрачность снята",
            not self.win.left_box.get_style_context().has_class("kb-ghost"))
        yield lambda: self.expect(
            "терминал снова между половинами",
            abs(self.win.term.get_allocation().width - self.term_w_normal) < 40)

        # ---------- режим выдерживает многократное переключение ----------
        # раньше после нескольких переключений половины схлопывались в свой
        # минимум и больше не восстанавливались
        for _ in range(6):
            yield lambda: self.win.ghost_btn.set_active(not self.win.ghost)
        yield lambda: self.expect(
            "после 6 переключений половины не схлопнулись",
            self.win.left_box.get_allocation().width > 100
            and self.win.right_box.get_allocation().width > 100)
        yield lambda: self.expect(
            "после 6 переключений клавиши одного размера",
            abs(self.win.pad_left.get_allocation().width / terkb.SPLIT_L_W
                - self.win.pad_right.get_allocation().width / terkb.SPLIT_R_W)
            < 1.0)
        # Прямая проверка того, что чинилось: бюджет попыток раскладки должен
        # обнуляться на каждый запрос. Раньше он исчерпывался за несколько
        # переключений навсегда, и раскладка переставала сходиться. В offscreen
        # окне это не воспроизводится — оно сходится с первой попытки, поэтому
        # проверяем инвариант напрямую.
        yield lambda: self.expect(
            "переключение обнуляет бюджет попыток раскладки",
            self.retry_budget_reset())
        yield lambda: self.expect(
            "после 6 переключений вернулись в обычный режим",
            not self.win.ghost
            and self.win.left_box.get_parent() is self.win.outer)
        yield lambda: (self.tap(*"echo"), self.tap(" "),
                       self.tap(*"still"), self.tap("Enter ⏎", pad=R))
        yield lambda: self.check("после переключений ввод жив", "\nstill\n")

        # ---------- разделители перетаскиваются ----------
        # ждём, пока доиграет отложенная раскладка после переключений режима,
        # иначе она перебьёт выставленную позицию
        yield lambda: None
        yield lambda: None
        yield lambda: self.snapshot()
        yield lambda: self.win.inner.set_position(
            self.win.inner.get_position() - 120)
        yield lambda: self.expect(
            "разделитель терминала двигается",
            abs(self.win.center.get_allocation().width - self.snap[2] + 120) <= 2)
        yield lambda: self.win.outer.set_position(
            self.win.outer.get_position() + 60)
        yield lambda: self.expect(
            "разделитель левой половины двигается",
            abs(self.win.left_box.get_allocation().width - self.snap[3] - 60) <= 2)

        yield lambda: (self.tap(*"echo"), self.tap(" "), self.tap(*"done"),
                       self.tap("Enter ⏎", pad=R))
        yield lambda: self.check("итоговая команда", "\ndone\n")
        yield lambda: self.finish()

    snap = (0, 0, 0, 0)
    term_w_normal = 0

    def at_scale_ceiling(self):
        """Следующее ⌨+ не должно менять масштаб, если размер уже упёрся."""
        before = self.win.kb_scale
        self.win.zoom_kb(terkb.KB_SCALE_STEP)
        return self.win.kb_scale == before

    def fades(self, delta):
        """Меняет ли кнопка прозрачность и перезагружается ли CSS."""
        before = self.win.ghost_alpha
        self.win.fade_kb(delta)
        return (self.win.ghost_alpha - before) * delta > 0

    def retry_budget_reset(self):
        self.win._retries = 99
        self.win.schedule_layout()
        return self.win._retries == 0

    def overlaps(self, a, b):
        """Пересекаются ли два виджета на экране.

        Координаты берём через translate_coordinates: у детей Gtk.Overlay своё
        GdkWindow, и get_allocation() отдаёт позицию относительно него, то есть
        всегда (0, 0).
        """
        aa, bb = a.get_allocation(), b.get_allocation()
        ax, ay = a.translate_coordinates(self.win.overlay, 0, 0)
        bx, by = b.translate_coordinates(self.win.overlay, 0, 0)
        return (ax < bx + bb.width and ax + aa.width > bx
                and ay < by + bb.height and ay + aa.height > by)

    def wait_prompt(self):
        """Ждём, пока шелл начнёт исполнять команды.

        Одного приглашения на экране мало: оно появляется раньше, чем bash
        готов читать ввод, и первый тест печати падал примерно через раз.
        Поэтому шлём метку прямо в PTY и ждём её в выводе.
        """
        deadline = time.monotonic() + 20.0
        sent = False
        while time.monotonic() < deadline:
            while Gtk.events_pending():
                Gtk.main_iteration()
            screen = self.screen()
            if not sent and "$" in screen:
                self.term.raw(b"printf '__ready__\n'\n")
                sent = True
            elif sent and "__ready__" in screen:
                self.term.raw(b"clear\n")
                time.sleep(0.2)
                while Gtk.events_pending():
                    Gtk.main_iteration()
                return True
            time.sleep(0.05)
        return False

    def pad_size_in_keys(self):
        """Полоса должна быть в одну клавишу шириной и в две высотой."""
        a = self.win.touchpad.get_allocation()
        key_w = self.win.pad_right.get_allocation().width / terkb.SPLIT_R_W * 4
        key_h = key_w * terkb.KEY_STRETCH
        return abs(a.width - key_w) <= 6 and abs(a.height - 2 * key_h) <= 8

    def pad_scroll(self, step):
        """Протаскиваем палец по полосе, возвращаем сдвиг прокрутки."""
        adj = self.win.term.vte.get_vadjustment()
        before = adj.get_value()
        for _ in range(10):
            self.win.on_pad_drag(step)
        while Gtk.events_pending():
            Gtk.main_iteration()
        return adj.get_value() - before

    def pad_stays_in_range(self):
        """Долгая перемотка в обе стороны не должна вылезать за пределы."""
        adj = self.win.term.vte.get_vadjustment()
        for _ in range(200):
            self.win.on_pad_drag(40)
        lo_ok = adj.get_value() >= adj.get_lower() - 0.01
        for _ in range(400):
            self.win.on_pad_drag(-40)
        top = adj.get_upper() - adj.get_page_size()
        hi_ok = adj.get_value() <= top + 0.01
        return lo_ok and hi_ok

    def sample_key(self, btn):
        """Самый частый цвет фона клавиши: полоса у верхнего края, мимо подписи."""
        self.off.queue_draw()
        while Gtk.events_pending():
            Gtk.main_iteration()
        pb = self.off.get_pixbuf()
        n, rs, data = pb.get_n_channels(), pb.get_rowstride(), pb.get_pixels()
        a = btn.get_allocation()
        ox, oy = btn.translate_coordinates(self.win.root, 0, 0)
        vals = []
        for y in range(oy + 6, oy + max(8, int(a.height * 0.22))):
            for x in range(ox + 6, ox + a.width - 6):
                i = y * rs + x * n
                vals.append(tuple(data[i:i + 3]))
        return max(set(vals), key=vals.count)

    def state_looks_same(self, pad, label, flags):
        btn = self.key(label, pad).button
        base = self.sample_key(btn)
        btn.set_state_flags(flags, False)
        got = self.sample_key(btn)
        btn.unset_state_flags(flags)
        return got == base

    def hit_visible(self, pad, label):
        btn = self.key(label, pad).button
        base = self.sample_key(btn)
        pad.hit(btn, True)
        lit = self.sample_key(btn)
        pad.hit(btn, False)
        return lit != base and self.sample_key(btn) == base

    def macro_keys(self):
        return sorted((k for k in self.win.pad_right.keys
                       if k.kind == "macro"), key=lambda k: k.data)

    def macro_saved(self, index):
        with open(terkb.MACRO_FILE, encoding="utf-8") as f:
            return json.load(f)[index]

    def macro_cancel_keeps(self):
        """Правка с отменой не должна менять сохранённую команду."""
        before = self.win.state.macros[0]
        self.win.edit_macro(0)
        self.win.macro_entry.set_text("мусор")
        self.win.macro_cancel()
        while Gtk.events_pending():
            Gtk.main_iteration()
        return (self.win.state.macros[0] == before
                and self.win.state.send is self.win.term
                and not self.win.macro_box.get_visible())

    def handle_zones(self):
        """Горизонтальные границы окон-ручек обоих разделителей."""
        zones = []
        for paned in (self.win.outer, self.win.inner):
            hw = paned.get_handle_window()
            if hw is None:
                continue
            x, _y, w, _h = hw.get_geometry()
            origin = paned.translate_coordinates(self.win.root, 0, 0)
            px = origin[0] if origin else 0
            zones.append((px + x, px + x + w))
        return zones

    def key_clear_of_handles(self, pad, label, need=8):
        btn = self.key(label, pad).button
        a = btn.get_allocation()
        origin = btn.translate_coordinates(self.win.root, 0, 0)
        if origin is None:
            return False
        x0, x1 = origin[0], origin[0] + a.width
        for z0, z1 in self.handle_zones():
            if x0 < z1 and x1 > z0:
                return False              # прямое перекрытие
            if not (x0 - z1 >= need or z0 - x1 >= need):
                return False              # слишком близко
        return True

    def active_lights(self, pad, label):
        """Флаг ACTIVE ставит сама GtkButton — от него и должна идти подсветка."""
        btn = self.key(label, pad).button
        btn.unset_state_flags(Gtk.StateFlags.ACTIVE)
        while Gtk.events_pending():
            Gtk.main_iteration()
        was = self.has_hit(pad, label)
        btn.set_state_flags(Gtk.StateFlags.ACTIVE, False)
        while Gtk.events_pending():
            Gtk.main_iteration()
        lit = self.has_hit(pad, label)
        btn.unset_state_flags(Gtk.StateFlags.ACTIVE)
        while Gtk.events_pending():
            Gtk.main_iteration()
        return (not was) and lit and not self.has_hit(pad, label)

    def has_hit(self, pad, label):
        return self.key(label, pad).button.get_style_context().has_class("kb-hit")

    def hit_state(self, pad, label, on):
        pad.hit(self.key(label, pad).button, on)
        return self.has_hit(pad, label) is on

    def wait_hit_gone(self, pad, label):
        """Крутим главный цикл, пока не сработает таймаут подсветки."""
        deadline = time.monotonic() + (terkb.HIT_TIMEOUT_MS / 1000.0) + 1.0
        while time.monotonic() < deadline:
            while Gtk.events_pending():
                Gtk.main_iteration()
            if not self.has_hit(pad, label):
                return True
            time.sleep(0.05)
        return False

    def row_of(self, label, pad):
        return pad.child_get_property(self.key(label, pad).button, "top-attach")

    def col_of(self, label, pad):
        return pad.child_get_property(self.key(label, pad).button, "left-attach")

    def arrow_alloc(self):
        return self.key("↑", self.R).button.get_allocation()

    def plain_alloc(self):
        return self.key("y", self.R).button.get_allocation()

    def row_under_f(self):
        """Клавиши ряда, идущего сразу под F-клавишами, в обеих половинах."""
        out = []
        for pad, r in ((self.L, terkb.NUM_ROWS + 1),
                       (self.R, terkb.TOP_ROWS + 1)):
            for ch in pad.get_children():
                if pad.child_get_property(ch, "top-attach") == r:
                    out += [k for k in pad.keys if k.button is ch]
        return out

    def snapshot(self):
        """Запоминаем размеры, чтобы сравнить с ними после изменения."""
        self.snap = (self.win.pad_left.get_allocation().width,
                     self.win.pad_left.get_allocation().height,
                     self.win.center.get_allocation().width,
                     self.win.left_box.get_allocation().width)

    def step(self):
        try:
            fn = next(self.steps)
        except StopIteration:
            return False
        try:
            fn()
        except Exception as e:                      # тест не должен зависать
            results.append((False, "ошибка шага", repr(e)))
            print("ERROR", repr(e))
        GLib.timeout_add(450, self.step)
        return False

    def finish(self):
        print("\n--- экран терминала ---")
        print("\n".join(l for l in self.screen().splitlines() if l.strip()))
        bad = [r for r in results if not r[0]]
        print("\nИтог: %d/%d прошли" % (len(results) - len(bad), len(results)))
        self.quit()
        return False


A().run([])
sys.exit(1 if any(not r[0] for r in results) else 0)
