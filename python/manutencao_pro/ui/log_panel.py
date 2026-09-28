from __future__ import annotations

from gi.repository import GLib, Gtk

from manutencao_pro.i18n import _


class LogPanel(Gtk.Expander):
    def __init__(self) -> None:
        super().__init__(label=_("Detalhes"))
        self.view = Gtk.TextView(
            editable=False,
            cursor_visible=True,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
        )
        self.view.set_left_margin(8)
        self.view.set_right_margin(8)
        self.view.set_top_margin(8)
        self.view.set_bottom_margin(8)
        self._scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )
        self._scroll.set_size_request(-1, 160)
        self._scroll.set_child(self.view)
        self.set_child(self._scroll)

    def append(self, line: str) -> None:
        buffer = self.view.get_buffer()
        adjustment = self._scroll.get_vadjustment()
        at_bottom = adjustment.get_value() + adjustment.get_page_size() >= adjustment.get_upper() - 12
        buffer.insert(buffer.get_end_iter(), line + "\n")
        if at_bottom:
            GLib.idle_add(self._stick_to_bottom)

    def clear(self) -> None:
        self.view.get_buffer().set_text("")

    def text(self) -> str:
        buffer = self.view.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)

    def toggle(self) -> None:
        self.set_expanded(not self.get_expanded())

    def _stick_to_bottom(self) -> bool:
        adjustment = self._scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper())
        return False
