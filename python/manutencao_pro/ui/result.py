from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from manutencao_pro.constants import RESULT_ORDER, result_title, state_label, status_label
from manutencao_pro.i18n import _
from manutencao_pro.state import RunModel, classify

_PAGE_ICONS = {
    "ok": "object-select-symbolic",
    "warning": "dialog-warning-symbolic",
    "reboot": "system-reboot-symbolic",
    "error": "dialog-error-symbolic",
    "cancelled": "process-stop-symbolic",
}
_ROW_ICONS = {
    "success": "object-select-symbolic",
    "warning": "dialog-warning-symbolic",
    "error": "dialog-error-symbolic",
    "info": "dialog-information-symbolic",
}


class ResultPage(Gtk.Box):
    def __init__(
        self,
        on_copy: Callable[[], None],
        on_save: Callable[[], None],
        on_again: Callable[[], None],
        on_reboot: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12, vexpand=True)
        self.status_icon = Gtk.Image(pixel_size=28)
        self.status_title = Gtk.Label(halign=Gtk.Align.CENTER, justify=Gtk.Justification.CENTER, wrap=True)
        self.status_title.add_css_class("title-2")
        self.status_description = Gtk.Label(
            halign=Gtk.Align.CENTER,
            justify=Gtk.Justification.CENTER,
            wrap=True,
            max_width_chars=42,
        )
        self.status_description.add_css_class("dim-label")
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, halign=Gtk.Align.CENTER)
        header.append(self.status_icon)
        header.append(self.status_title)
        header.append(self.status_description)
        self.group = Adw.PreferencesGroup(title=_("Conferência final"))
        self.reboot_button = _button(_("Reiniciar agora"), "destructive-action", on_reboot)
        self.reboot_button.set_visible(False)
        self.reboot_button.set_hexpand(True)
        again = _button(_("Executar novamente"), "suggested-action", on_again)
        again.set_hexpand(True)
        copy_log = _button(_("Copiar log"), None, on_copy)
        save_log = _button(_("Salvar log"), None, on_save)
        secondary = Gtk.Box(spacing=8, homogeneous=True)
        secondary.append(copy_log)
        secondary.append(save_log)
        self.buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.buttons.append(secondary)
        self.buttons.append(again)
        self.buttons.append(self.reboot_button)
        self.action_buttons = [copy_log, save_log, again, self.reboot_button]
        self._rows: list[Adw.ActionRow] = []
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vexpand=True,
            child=self.group,
        )
        self.append(header)
        self.append(scroll)
        self.append(self.buttons)

    def show_model(self, model: RunModel) -> None:
        self.status_icon.set_from_icon_name(_PAGE_ICONS.get(model.status, "dialog-information-symbolic"))
        self.status_title.set_label(_heading(model.status))
        self.status_description.set_label(_description(model))
        for row in self._rows:
            self.group.remove(row)
        self._rows.clear()
        for key in RESULT_ORDER:
            if key not in model.results:
                continue
            state = model.results[key]
            kind = classify(key, state)
            row = Adw.ActionRow(title=result_title(key), subtitle=state_label(state))
            row.add_suffix(
                Gtk.Image(
                    icon_name=_ROW_ICONS.get(kind, "dialog-information-symbolic"),
                    pixel_size=16,
                )
            )
            self.group.add(row)
            self._rows.append(row)
        self.reboot_button.set_visible(bool(model.reboot_reasons))


def summary_text(model: RunModel) -> str:
    return _description(model)


def summary_title(status: str) -> str:
    return _heading(status)


def _heading(status: str) -> str:
    headings = {
        "ok": _("Tudo certo"),
        "warning": _("Concluído com avisos"),
        "reboot": _("Reinício necessário"),
        "error": _("A manutenção falhou"),
        "cancelled": _("Manutenção cancelada"),
    }
    return headings.get(status, status_label(status))


def _description(model: RunModel) -> str:
    if model.status == "cancelled":
        return _("A execução foi interrompida.")
    if model.status == "error" and not model.results and model.exit_code == 126:
        return _("Autorização recusada.")
    if model.status == "error" and not model.results and model.exit_code == 127:
        return _("Não foi possível iniciar a manutenção.")
    if model.status == "error":
        return _("Houve falha na manutenção. Veja o log.")
    if model.status == "reboot":
        return _("Motivos: {reasons}").format(reasons="; ".join(model.reboot_reasons))
    if model.status == "warning":
        return _("Avisos: {warnings}").format(warnings=" | ".join(model.warnings))
    return _("Não precisa reiniciar.")


def _button(label: str, style: str | None, callback: Callable[[], None]) -> Gtk.Button:
    button = Gtk.Button(label=label)
    button.add_css_class("pill")
    if style is not None:
        button.add_css_class(style)
    button.connect("clicked", lambda *_args: callback())
    return button

