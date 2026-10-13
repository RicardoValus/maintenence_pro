from __future__ import annotations

from gi.repository import Gtk

from manutencao_pro.ui.environment_list import FILTERS

_SKIPPED = frozenset({"all", "system"})


class ExportChoices(Gtk.FlowBox):
    def __init__(self) -> None:
        super().__init__(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            column_spacing=16,
            row_spacing=8,
            max_children_per_line=6,
        )
        self.add_css_class("mp-choices")
        self._checks: dict[str, Gtk.CheckButton] = {}
        for key, label in FILTERS:
            if key in _SKIPPED:
                continue
            check = Gtk.CheckButton(label=label, active=True)
            self._checks[key] = check
            self.append(check)

    def selected(self) -> frozenset[str]:
        return frozenset(key for key, check in self._checks.items() if check.get_active())

    def set_interactive(self, enabled: bool) -> None:
        for check in self._checks.values():
            check.set_sensitive(enabled)
