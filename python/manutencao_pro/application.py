from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gdk, Gtk

from manutencao_pro.constants import SCENARIOS
from manutencao_pro.i18n import _
from manutencao_pro.paths import APP_ID, icon_theme_dir
from manutencao_pro.ui.dialogs import present_about
from manutencao_pro.ui.window import MainWindow


class ManutencaoApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.demo = False
        self.scenario = "ok"
        self.autostart = False
        self.add_main_option("run", ord("r"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, _("Inicia a manutenção ao abrir"), None)
        self.add_main_option("demo", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, _("Abre em modo demonstração"), None)
        self.add_main_option("scenario", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING, _("Cenário de demonstração"), "CENÁRIO")

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._icons()
        action = Gio.SimpleAction.new("about", None)
        action.connect("activate", self._on_about)
        self.add_action(action)
        leave = Gio.SimpleAction.new("sair", None)
        leave.connect("activate", self._on_sair)
        self.add_action(leave)
        self.set_accels_for_action("app.sair", ["<Control>q"])

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            window = MainWindow(self)
            window.set_mode(self.demo, self.scenario)
        window.present()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        self._read_options(command_line)
        window = self.props.active_window
        if not isinstance(window, MainWindow):
            self.activate()
            window = self.props.active_window
        if isinstance(window, MainWindow):
            window.set_mode(self.demo, self.scenario)
            window.present()
            if self.autostart:
                window.start()
        return 0

    def _read_options(self, command_line: Gio.ApplicationCommandLine) -> None:
        options = command_line.get_options_dict()
        self.demo = options.contains("demo") or self.demo
        self.autostart = options.contains("run")
        value = options.lookup_value("scenario", GLib.VariantType.new("s"))
        if value is not None:
            scenario = value.get_string()
            if scenario in SCENARIOS:
                self.scenario = scenario
                self.demo = True

    def _icons(self) -> None:
        icons = icon_theme_dir()
        display = Gdk.Display.get_default()
        if icons is None or display is None:
            return
        Gtk.IconTheme.get_for_display(display).add_search_path(str(icons))

    def _on_about(self, _action: Gio.SimpleAction, _parameter: None) -> None:
        window = self.props.active_window
        if isinstance(window, Gtk.Window):
            present_about(window)

    def _on_sair(self, _action: Gio.SimpleAction, _parameter: None) -> None:
        window = self.props.active_window
        if isinstance(window, Gtk.Window):
            window.close()
            return
        self.quit()
