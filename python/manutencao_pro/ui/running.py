from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from manutencao_pro.constants import STEP_IDS, step_title
from manutencao_pro.i18n import _
from manutencao_pro.state import CANCELLED, ERROR, PENDING, RUNNING, SUCCESS, WARNING, RunModel
from manutencao_pro.ui.motion import ProgressPulse
from manutencao_pro.ui.status_icon import StatusIcon

_KINDS = {
    SUCCESS: "success",
    WARNING: "warning",
    ERROR: "error",
    CANCELLED: "cancelled",
}


class _StepRow:
    def __init__(self, step_id: str) -> None:
        self.step_id = step_id
        self.status = PENDING
        self.row = Adw.ActionRow(title=step_title(step_id))
        self.row.add_css_class("dim-label")
        self.slot = Gtk.Box()
        self.slot.set_size_request(28, 16)
        self.row.add_suffix(self.slot)

    def apply(self, status: str, title: str) -> None:
        self.row.set_title(title)
        if status == self.status:
            return
        self.status = status
        if status == PENDING:
            self.row.add_css_class("dim-label")
        else:
            self.row.remove_css_class("dim-label")
        child = self.slot.get_first_child()
        if child is not None:
            self.slot.remove(child)
        if status == RUNNING:
            self.slot.append(Adw.Spinner())
            return
        kind = _KINDS.get(status)
        if kind is None:
            return
        icon = StatusIcon()
        self.slot.append(icon)
        icon.present(kind)


class RunningPage(Gtk.Box):
    def __init__(self, on_cancel: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.add_css_class("mp-mono")
        self._pulse = ProgressPulse(self.progress)
        self.connect("unrealize", lambda *_args: self._pulse.stop())
        self.group = Adw.PreferencesGroup(title=_("Etapas"))
        self._rows = {step_id: _StepRow(step_id) for step_id in STEP_IDS}
        for step_id in STEP_IDS:
            self.group.add(self._rows[step_id].row)
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vexpand=True,
            child=self.group,
        )
        self.cancel_button = Gtk.Button(label=_("Cancelar"), halign=Gtk.Align.CENTER)
        self.cancel_button.add_css_class("pill")
        self.cancel_button.connect("clicked", lambda *_args: on_cancel())
        self.append(self.progress)
        self.append(scroll)
        self.append(self.cancel_button)

    def sync(self, model: RunModel) -> None:
        for step in model.steps:
            row = self._rows.get(step.step_id)
            if row is None:
                continue
            row.apply(step.status, step.title)
        waiting = model.status == RUNNING and model.fraction <= 0
        if waiting:
            self._pulse.start()
        else:
            self._pulse.stop()
            self.progress.set_fraction(model.fraction)
        index, total = model.progress_index
        self.progress.set_text(_("Etapa {index} de {total}").format(index=index, total=total))
        self.cancel_button.set_sensitive(model.can_cancel)
        if model.can_cancel:
            self.cancel_button.set_tooltip_text(_("Encerra a etapa atual"))
            return
        self.cancel_button.set_tooltip_text(_("A etapa de pacotes não pode ser cancelada"))
