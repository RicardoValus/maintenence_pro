from __future__ import annotations

from gi.repository import Adw, Gio, GLib, Gtk

from manutencao_pro.constants import SCENARIOS
from manutencao_pro.i18n import _
from manutencao_pro.paths import APP_ID, WRAPPER
from manutencao_pro.runner import MaintenanceRunner
from manutencao_pro.state import HistoryStore, RunModel
from manutencao_pro.ui.dialogs import confirm_close, confirm_reboot, present_about, present_shortcuts, show_error
from manutencao_pro.ui.log_panel import LogPanel
from manutencao_pro.ui.result import ResultPage, summary_text, summary_title
from manutencao_pro.ui.running import RunningPage
from manutencao_pro.ui.start import StartPage


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application, title=_("Manutenção Pro"))
        self.set_default_size(480, 680)
        self.set_size_request(360, 420)
        self._demo = False
        self._scenario = "ok"
        self._close_after = False
        self._inhibit_cookie = 0
        self._log_lines: list[str] = []
        self._shortcuts: Gtk.ShortcutsWindow | None = None
        self.model = RunModel()
        self.runner = MaintenanceRunner()
        self.runner.on_line = self._on_line
        self.runner.on_exit = self._on_exit
        self._build()
        self._actions()
        self.connect("close-request", self._on_close_request)

    def set_mode(self, demo: bool, scenario: str) -> None:
        self._demo = demo
        if scenario not in SCENARIOS:
            scenario = "ok"
        self._scenario = scenario
        self.start_page.set_demo(demo, SCENARIOS.index(scenario))

    def start(self) -> None:
        if self.runner.is_running():
            return
        if self._demo:
            self._scenario = self.start_page.scenario_id()
        elif not WRAPPER.is_file():
            show_error(
                self,
                _("Pacote não instalado"),
                _("Instale o pacote para executar a manutenção. O modo demonstração não altera o sistema."),
            )
            return
        self._log_lines = []
        self.log_panel.clear()
        self.model.begin()
        self.running_page.sync(self.model)
        self.stack.set_visible_child_name("running")
        self._sync_log_visibility()
        self.set_title(_("Executando — Manutenção Pro"))
        self._inhibit()
        try:
            if self._demo:
                self.runner.start_demo(self._scenario)
            else:
                self.runner.start_real()
        except GLib.Error as error:
            self._fail_to_start(error.message)
        except OSError as error:
            self._fail_to_start(str(error))

    def _build(self) -> None:
        self.toast = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        menu_button = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            tooltip_text=_("Menu principal"),
            primary=True,
            menu_model=_menu(),
        )
        header.pack_end(menu_button)
        toolbar.add_top_bar(header)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.start_page = StartPage(self.start)
        self.running_page = RunningPage(self._cancel)
        self.result_page = ResultPage(self._copy_log, self._save_log, self.start, self._ask_reboot)
        self.log_panel = LogPanel()
        self.log_panel.set_visible(False)
        self.stack.add_named(self.start_page, "start")
        self.stack.add_named(self.running_page, "running")
        self.stack.add_named(self.result_page, "result")
        self.stack.connect("notify::visible-child-name", lambda *_args: self._sync_log_visibility())
        clamp = Adw.Clamp(maximum_size=720, tightening_threshold=480)
        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page_box.set_margin_top(12)
        page_box.set_margin_bottom(12)
        page_box.set_margin_start(12)
        page_box.set_margin_end(12)
        page_box.append(self.stack)
        page_box.append(self.log_panel)
        clamp.set_child(page_box)
        toolbar.set_content(clamp)
        self.toast.set_child(toolbar)
        self.set_content(self.toast)
        self._breakpoint(page_box)
        self.start_page.refresh()

    def _breakpoint(self, page_box: Gtk.Box) -> None:
        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 450px"))
        breakpoint.add_setter(page_box, "margin-start", 8)
        breakpoint.add_setter(page_box, "margin-end", 8)
        breakpoint.add_setter(self.start_page.button, "hexpand", True)
        breakpoint.add_setter(self.running_page.cancel_button, "hexpand", True)
        for button in self.result_page.action_buttons:
            breakpoint.add_setter(button, "hexpand", True)
        self.add_breakpoint(breakpoint)

    def _actions(self) -> None:
        self._add_window_action("start", self.start)
        self._add_window_action("toggle-log", self._toggle_log)
        self._add_window_action("shortcuts", self._show_shortcuts)
        app = self.get_application()
        if app is None:
            return
        app.set_accels_for_action("win.start", ["<Control>Return"])
        app.set_accels_for_action("win.toggle-log", ["<Control>l"])
        app.set_accels_for_action("win.shortcuts", ["F1"])

    def _add_window_action(self, name: str, callback: object) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", lambda *_args: callback())
        self.add_action(action)

    def _on_line(self, line: str) -> None:
        self._log_lines.append(line)
        self.log_panel.append(line)
        self.model.consume(line)
        self.runner.set_current_step(self.model.current_step_id)
        self.running_page.sync(self.model)

    def _on_exit(self, code: int, term_sig: int | None) -> None:
        self._uninhibit()
        self.model.finish(code, term_sig)
        self.running_page.sync(self.model)
        record = self.model.to_record("\n".join(self._log_lines))
        try:
            HistoryStore().append(record)
        except OSError:
            pass
        self.result_page.show_model(self.model)
        self.start_page.refresh()
        self.stack.set_visible_child_name("result")
        self.set_title(_("Manutenção Pro"))
        self._notify(summary_title(self.model.status), summary_text(self.model))
        if self._close_after:
            self._close_after = False
            self.destroy()

    def _cancel(self) -> None:
        if not self.model.can_cancel:
            return
        self.runner.cancel()

    def _toggle_log(self) -> None:
        if self.stack.get_visible_child_name() == "start" and not self._log_lines:
            return
        self.log_panel.set_visible(True)
        self.log_panel.toggle()

    def _sync_log_visibility(self) -> None:
        visible = self.stack.get_visible_child_name() in {"running", "result"}
        self.log_panel.set_visible(visible or self.log_panel.get_expanded())

    def _copy_log(self) -> None:
        display = self.get_display()
        if display is None:
            return
        display.get_clipboard().set("\n".join(self._log_lines))
        self.toast.add_toast(Adw.Toast(title=_("Log copiado"), timeout=2))

    def _save_log(self) -> None:
        dialog = Gtk.FileDialog(title=_("Salvar log"), initial_name="manutencao-pro.log")
        dialog.save(self, None, self._on_save_chosen, None)

    def _on_save_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult, *_rest: object) -> None:
        try:
            chosen = dialog.save_finish(result)
        except GLib.Error:
            return
        if chosen is None:
            return
        data = ("\n".join(self._log_lines) + "\n").encode("utf-8")
        try:
            chosen.replace_contents(data, None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None)
        except GLib.Error:
            self.toast.add_toast(Adw.Toast(title=_("Não foi possível salvar o log"), timeout=3))
            return
        self.toast.add_toast(Adw.Toast(title=_("Log salvo"), timeout=2))

    def _ask_reboot(self) -> None:
        if not self.model.reboot_reasons:
            return
        confirm_reboot(self, list(self.model.reboot_reasons), self._reboot)

    def _reboot(self) -> None:
        try:
            Gio.Subprocess.new(["systemctl", "reboot"], Gio.SubprocessFlags.NONE)
        except GLib.Error as error:
            show_error(self, _("Não foi possível reiniciar"), error.message)

    def _show_shortcuts(self) -> None:
        self._shortcuts = present_shortcuts(self, self._shortcuts)

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        if not self.runner.is_running():
            return False
        confirm_close(self, self.model.can_cancel, self._cancel_and_close)
        return True

    def _cancel_and_close(self) -> None:
        self._close_after = True
        self.runner.cancel()

    def _inhibit(self) -> None:
        app = self.get_application()
        if app is None:
            return
        self._inhibit_cookie = app.inhibit(
            self,
            Gtk.ApplicationInhibitFlags.LOGOUT | Gtk.ApplicationInhibitFlags.SUSPEND,
            _("Manutenção do sistema em andamento"),
        )

    def _uninhibit(self) -> None:
        app = self.get_application()
        if app is None or not self._inhibit_cookie:
            return
        app.uninhibit(self._inhibit_cookie)
        self._inhibit_cookie = 0

    def _notify(self, title: str, body: str) -> None:
        if self.is_active():
            return
        app = self.get_application()
        if app is None:
            return
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon.new(APP_ID))
        app.send_notification("done", notification)

    def _fail_to_start(self, message: str) -> None:
        self._uninhibit()
        self.stack.set_visible_child_name("start")
        self.set_title(_("Manutenção Pro"))
        show_error(self, _("Não foi possível iniciar"), message)


def _menu() -> Gio.Menu:
    menu = Gio.Menu()
    menu.append(_("_Atalhos de teclado"), "win.shortcuts")
    menu.append(_("_Sobre"), "app.about")
    menu.append(_("_Sair"), "app.sair")
    return menu
