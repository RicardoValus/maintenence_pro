from __future__ import annotations

from gi.repository import GLib, Gtk

from manutencao_pro.i18n import _


class LogPanel(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._chevron = Gtk.Image(icon_name="pan-end-symbolic")
        label = Gtk.Label(label=_("Detalhes"), xalign=0, hexpand=True)
        header = Gtk.Box(spacing=8)
        header.append(self._chevron)
        header.append(label)
        self._toggle = Gtk.ToggleButton()
        self._toggle.add_css_class("mp-disclosure")
        self._toggle.set_child(header)
        self._toggle.connect("toggled", self._on_toggled)
        self.view = Gtk.TextView(
            editable=False,
            cursor_visible=True,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
        )
        self.view.add_css_class("mp-log-view")
        self.view.set_left_margin(12)
        self.view.set_right_margin(12)
        self.view.set_top_margin(12)
        self.view.set_bottom_margin(12)
        self._scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )
        self._scroll.add_css_class("mp-log")
        self._scroll.set_size_request(-1, 160)
        self._scroll.set_child(self.view)
        self._revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            transition_duration=240,
            child=self._scroll,
        )
        self.append(self._toggle)
        self.append(self._revealer)

    def append_line(self, line: str) -> None:
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
        self._toggle.set_active(not self._toggle.get_active())

    def get_expanded(self) -> bool:
        return self._revealer.get_reveal_child()

    def _on_toggled(self, button: Gtk.ToggleButton) -> None:
        opened = button.get_active()
        self._revealer.set_reveal_child(opened)
        icon = "pan-down-symbolic" if opened else "pan-end-symbolic"
        self._chevron.set_from_icon_name(icon)

    def _stick_to_bottom(self) -> bool:
        adjustment = self._scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper())
        return False
