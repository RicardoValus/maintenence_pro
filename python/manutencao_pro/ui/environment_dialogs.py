from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from manutencao_pro.i18n import _

FileCallback = Callable[[Gio.File], None]


class ImportDialog(Adw.Dialog):
    def __init__(
        self,
        plan_text: str,
        manual_text: str,
        blocked_reason: str | None,
        on_apply: Callable[[], None],
        warning: str | None = None,
    ) -> None:
        super().__init__(title=_("Conferir importação"), content_width=680, content_height=560)
        self.add_css_class("mp-app")
        self._on_apply = on_apply
        self._running = False
        self._log = _text_view()
        self._log_scroll = _scrolled(self._log)
        self._log_scroll.set_size_request(-1, 140)
        self._manual = _text_view()
        self._manual.get_buffer().set_text(manual_text)
        self._plan = _text_view()
        self._plan.get_buffer().set_text(plan_text)
        self._apply = Gtk.Button(label=_("Aplicar"))
        self._apply.add_css_class("suggested-action")
        self._apply.add_css_class("pill")
        self._apply.connect("clicked", self._clicked)
        self._close = Gtk.Button(label=_("Cancelar"))
        self._close.add_css_class("pill")
        self._close.connect("clicked", lambda *_args: self.close())
        if blocked_reason:
            self._apply.set_sensitive(False)
        header = Adw.HeaderBar()
        header.pack_start(self._close)
        header.pack_end(self._apply)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        if warning:
            box.append(_notice(warning))
        if blocked_reason:
            box.append(_notice(blocked_reason))
        box.append(_heading(_("O que vai executar")))
        box.append(self._plan_scroll())
        box.append(_heading(_("Progresso")))
        box.append(self._log_scroll)
        box.append(_heading(_("Ações manuais")))
        manual_scroll = _scrolled(self._manual)
        manual_scroll.set_vexpand(False)
        manual_scroll.set_size_request(-1, 140)
        box.append(manual_scroll)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(box)
        self.set_child(toolbar)

    def begin_progress(self) -> None:
        self._running = True
        self._apply.set_sensitive(False)
        self._close.set_sensitive(False)
        self.set_can_close(False)
        self.set_title(_("Importando ambiente"))
        self._log.get_buffer().set_text("")

    def append_log(self, line: str) -> None:
        buffer = self._log.get_buffer()
        adjustment = self._log_scroll.get_vadjustment()
        at_bottom = adjustment.get_value() + adjustment.get_page_size() >= adjustment.get_upper() - 12
        buffer.insert(buffer.get_end_iter(), line + "\n")
        if at_bottom:
            GLib.idle_add(self._stick)

    def finish(self, manual_text: str) -> None:
        self._running = False
        self._manual.get_buffer().set_text(manual_text)
        self.set_can_close(True)
        self._close.set_label(_("Fechar"))
        self._close.set_sensitive(True)
        self.set_title(_("Importação concluída"))

    def _clicked(self, _button: Gtk.Button) -> None:
        if self._running or not self._apply.get_sensitive():
            return
        self._on_apply()

    def _plan_scroll(self) -> Gtk.ScrolledWindow:
        scroll = _scrolled(self._plan)
        scroll.set_vexpand(False)
        scroll.set_size_request(-1, 160)
        return scroll

    def _stick(self) -> bool:
        adjustment = self._log_scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper())
        return False


def present_save_json(parent: Gtk.Window, on_file: FileCallback) -> None:
    dialog = _json_dialog(_("Exportar ambiente"))
    dialog.set_initial_name("ambiente-dev.json")
    dialog.save(parent, None, _finish_save, on_file)


def present_open_json(parent: Gtk.Window, on_file: FileCallback) -> None:
    dialog = _json_dialog(_("Importar ambiente"))
    dialog.open(parent, None, _finish_open, on_file)


def _json_dialog(title: str) -> Gtk.FileDialog:
    dialog = Gtk.FileDialog(title=title)
    dialog.set_filters(_json_filters())
    dialog.set_initial_folder(Gio.File.new_for_path(str(Path.home())))
    return dialog


def _json_filters() -> Gio.ListStore:
    file_filter = Gtk.FileFilter()
    file_filter.set_name(_("JSON"))
    file_filter.add_pattern("*.json")
    file_filter.add_mime_type("application/json")
    store = Gio.ListStore.new(Gtk.FileFilter)
    store.append(file_filter)
    return store


def _finish_save(dialog: Gtk.FileDialog, result: Gio.AsyncResult, on_file: FileCallback) -> None:
    _finish(dialog.save_finish, result, on_file)


def _finish_open(dialog: Gtk.FileDialog, result: Gio.AsyncResult, on_file: FileCallback) -> None:
    _finish(dialog.open_finish, result, on_file)


def _finish(finish: Callable[[Gio.AsyncResult], Gio.File | None], result: Gio.AsyncResult, on_file: FileCallback) -> None:
    try:
        chosen = finish(result)
    except GLib.Error:
        return
    if chosen is not None:
        on_file(chosen)


def _text_view() -> Gtk.TextView:
    view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    view.add_css_class("mp-log-view")
    view.set_left_margin(8)
    view.set_right_margin(8)
    view.set_top_margin(8)
    view.set_bottom_margin(8)
    return view


def _scrolled(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)
    scroll.set_child(child)
    return scroll


def _notice(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text, wrap=True, xalign=0)
    label.add_css_class("warning")
    return label


def _heading(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0)
    label.add_css_class("heading")
    return label
