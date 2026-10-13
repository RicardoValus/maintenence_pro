from __future__ import annotations

from gi.repository import Gtk

from manutencao_pro.ui.motion import fade, play_entrance

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
    def __init__(self, pixel_size: int = 16, *, centered: bool = False) -> None:
        super().__init__()
        self._centered = centered
        gutter = 0 if centered else 12
        align = Gtk.Align.CENTER if centered else Gtk.Align.END
        self.set_size_request(pixel_size + gutter, pixel_size)
        self.set_overflow(Gtk.Overflow.VISIBLE)
        if centered:
            self.set_halign(Gtk.Align.CENTER)
        self.image = Gtk.Image(pixel_size=pixel_size, halign=align, valign=Gtk.Align.CENTER)
        self.image.add_css_class("mp-status-icon")
        self.append(self.image)

    def present(self, kind: str) -> None:
        icon_name, css_class = KIND_ICONS.get(kind, KIND_ICONS["info"])
        for name in _CLASSES:
            self.image.remove_css_class(name)
        self.image.add_css_class(css_class)
        self.image.set_from_icon_name(icon_name)
        if self._centered:
            self.image.set_margin_start(0)
            self.image.set_opacity(0)
            fade(self.image, 0, 1, 220)
            return
        play_entrance(self.image)
