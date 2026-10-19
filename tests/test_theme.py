from __future__ import annotations

import os
import unittest

from manutencao_pro.paths import project_root, style_css
from manutencao_pro.ui.status_icon import KIND_ICONS

_ICONS = (
    "mp-alert-symbolic.svg",
    "mp-check-symbolic.svg",
    "mp-info-symbolic.svg",
    "mp-minus-symbolic.svg",
    "mp-power-symbolic.svg",
    "mp-x-symbolic.svg",
)


class ThemeAssetsTest(unittest.TestCase):
    def test_style_css_ships_the_dark_palette(self) -> None:
        path = style_css()
        self.assertIsNotNone(path)
        assert path is not None
        text = path.read_text(encoding="utf-8")
        self.assertIn("#0f1115", text)
        self.assertIn("#1a1c22", text)
        self.assertIn("#ff7800", text)
        self.assertIn("Inter", text)
        self.assertIn("JetBrains Mono", text)
        self.assertIn("columnview.mp-audit", text)
        self.assertIn("window.mp-app", text)

    def test_outline_icons_use_the_symbolic_palette(self) -> None:
        root = project_root()
        self.assertIsNotNone(root)
        assert root is not None
        folder = root / "data" / "icons" / "hicolor" / "scalable" / "status"
        for name in _ICONS:
            text = (folder / name).read_text(encoding="utf-8")
            self.assertIn("#2e3436", text)
            self.assertIn("stroke", text)

    def test_status_kinds_point_at_outline_icons(self) -> None:
        root = project_root()
        self.assertIsNotNone(root)
        assert root is not None
        folder = root / "data" / "icons" / "hicolor" / "scalable" / "status"
        for kind in ("success", "warning", "error", "info", "cancelled", "reboot"):
            icon_name, css_class = KIND_ICONS[kind]
            self.assertTrue(icon_name.endswith("-symbolic"))
            self.assertTrue(css_class.startswith("mp-status-"))
            self.assertTrue((folder / f"{icon_name}.svg").is_file())


@unittest.skipUnless(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"), "sem display")
class ThemeLoadTest(unittest.TestCase):
    def test_css_parses_and_icons_resolve(self) -> None:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Gdk, GLib, Gtk

        from manutencao_pro.ui.motion import play_entrance
        from manutencao_pro.ui.status_icon import StatusIcon
        from manutencao_pro.ui.theme import apply_app_theme

        errors: list[str] = []

        def on_error(_provider: Gtk.CssProvider, section: Gtk.CssSection, error: GLib.Error) -> None:
            errors.append(f"{section.get_start_location().lines}: {error.message}")

        provider = Gtk.CssProvider()
        provider.connect("parsing-error", on_error)
        path = style_css()
        assert path is not None
        provider.load_from_string(path.read_text(encoding="utf-8"))
        self.assertEqual(errors, [])
        apply_app_theme()
        display = Gdk.Display.get_default()
        if display is None:
            self.skipTest("sem display gráfico (build headless)")
        theme = Gtk.IconTheme.get_for_display(display)
        root = project_root()
        assert root is not None
        theme.add_search_path(str(root / "data" / "icons"))
        for icon_name, _css in KIND_ICONS.values():
            self.assertTrue(theme.has_icon(icon_name), icon_name)
        icon = StatusIcon()
        icon.present("success")
        play_entrance(icon.image)
        context = GLib.MainContext.default()
        for _step in range(8):
            context.iteration(False)
