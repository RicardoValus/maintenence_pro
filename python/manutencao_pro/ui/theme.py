from __future__ import annotations

from gi.repository import Adw, Gdk, Gtk

from manutencao_pro.paths import style_css

_APPLIED = False


def apply_app_theme() -> None:
    global _APPLIED
    if _APPLIED:
        return
    display = Gdk.Display.get_default()
    path = style_css()
    if display is None or path is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(path.read_text(encoding="utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    _APPLIED = True
