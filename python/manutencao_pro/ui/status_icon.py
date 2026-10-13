from __future__ import annotations

from gi.repository import Gtk

from manutencao_pro.ui.motion import play_entrance

KIND_ICONS = {
    "success": ("mp-check-symbolic", "mp-status-success"),
    "warning": ("mp-alert-symbolic", "mp-status-warning"),
    "error": ("mp-x-symbolic", "mp-status-error"),
    "info": ("mp-info-symbolic", "mp-status-info"),
    "cancelled": ("mp-minus-symbolic", "mp-status-muted"),
    "reboot": ("mp-power-symbolic", "mp-status-accent"),
}

_CLASSES = tuple(css_class for _icon, css_class in KIND_ICONS.values())


class StatusIcon(Gtk.Box):
    def __init__(self, pixel_size: int = 16) -> None:
        super().__init__()
        self.set_size_request(pixel_size + 12, pixel_size)
        self.set_overflow(Gtk.Overflow.VISIBLE)
        self.image = Gtk.Image(pixel_size=pixel_size, halign=Gtk.Align.END)
        self.image.add_css_class("mp-status-icon")
        self.append(self.image)

    def present(self, kind: str) -> None:
        icon_name, css_class = KIND_ICONS.get(kind, KIND_ICONS["info"])
        for name in _CLASSES:
            self.image.remove_css_class(name)
        self.image.add_css_class(css_class)
        self.image.set_from_icon_name(icon_name)
        play_entrance(self.image)
