from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from gi.repository import Adw, Gtk

from manutencao_pro.constants import SCENARIOS, status_label
from manutencao_pro.i18n import _
from manutencao_pro.paths import APP_ID
from manutencao_pro.state import HistoryStore, RunRecord


class StartPage(Gtk.Box):
    def __init__(self, on_start: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._page = Adw.StatusPage(icon_name=APP_ID, title=_("Manutenção Pro"), vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        self.scenario = Gtk.DropDown.new_from_strings(
            [
                _("Tudo certo"),
                _("Avisos"),
                _("Reinício necessário"),
                _("Falha no apt"),
            ]
        )
        self.scenario.set_visible(False)
        self.button = Gtk.Button(halign=Gtk.Align.CENTER)
        self.button.set_child(
            Adw.ButtonContent(
                icon_name="media-playback-start-symbolic",
                label=_("Iniciar manutenção"),
            )
        )
        self.button.add_css_class("suggested-action")
        self.button.add_css_class("pill")
        self.button.connect("clicked", lambda *_args: on_start())
        box.append(self.scenario)
        box.append(self.button)
        self._page.set_child(box)
        self.append(self._page)
        self._demo = False

    def set_demo(self, enabled: bool, scenario_index: int) -> None:
        self._demo = enabled
        self.scenario.set_visible(enabled)
        if enabled:
            self.scenario.set_selected(scenario_index)
        self.refresh()

    def scenario_id(self) -> str:
        index = self.scenario.get_selected()
        if index < 0 or index >= len(SCENARIOS):
            return "ok"
        return SCENARIOS[index]

    def refresh(self) -> None:
        text = _last_run_text(HistoryStore().latest())
        if self._demo:
            text = _("Modo demonstração. Nenhuma alteração será feita no sistema.") + "\n" + text
        self._page.set_description(text)


def _last_run_text(record: RunRecord | None) -> str:
    if record is None or not record.started_at:
        return _("Nenhuma execução registrada")
    try:
        when = datetime.fromisoformat(record.started_at).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        when = record.started_at
    return _("Última execução: {when} — {result}").format(
        when=when,
        result=status_label(record.status),
    )
