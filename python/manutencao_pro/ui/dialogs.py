from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from manutencao_pro import __version__
from manutencao_pro.i18n import _
from manutencao_pro.paths import shortcuts_ui


def show_error(parent: Gtk.Window, heading: str, body: str) -> None:
    dialog = Adw.AlertDialog(heading=heading, body=body)
    dialog.add_response("close", _("Fechar"))
    dialog.present(parent)


def confirm_close(parent: Gtk.Window, can_cancel: bool, on_cancel: Callable[[], None]) -> None:
    if can_cancel:
        dialog = Adw.AlertDialog(
            heading=_("Interromper a manutenção?"),
            body=_("A etapa atual será encerrada. Etapas de pacotes não são interrompidas."),
        )
        dialog.add_response("keep", _("Continuar"))
        dialog.add_response("cancel", _("Cancelar e fechar"))
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("keep")
        dialog.set_close_response("keep")
    else:
        dialog = Adw.AlertDialog(
            heading=_("Manutenção em andamento"),
            body=_("A etapa de pacotes não pode ser interrompida. Espere ela terminar para fechar."),
        )
        dialog.add_response("keep", _("Continuar"))
        dialog.set_default_response("keep")
        dialog.set_close_response("keep")

    def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
        if response == "cancel":
            on_cancel()

    dialog.connect("response", on_response)
    dialog.present(parent)


def confirm_reboot(parent: Gtk.Window, reasons: list[str], on_confirm: Callable[[], None]) -> None:
    dialog = Adw.AlertDialog(heading=_("Reiniciar agora?"), body="\n".join(reasons))
    dialog.add_response("cancel", _("Cancelar"))
    dialog.add_response("reboot", _("Reiniciar"))
    dialog.set_response_appearance("reboot", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")

    def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
        if response == "reboot":
            on_confirm()

    dialog.connect("response", on_response)
    dialog.present(parent)


def present_shortcuts(parent: Gtk.Window, current: Gtk.ShortcutsWindow | None) -> Gtk.ShortcutsWindow | None:
    if current is not None:
        current.present()
        return current
    path = shortcuts_ui()
    if path is None:
        show_error(parent, _("Atalhos indisponíveis"), _("O arquivo de atalhos não foi encontrado."))
        return None
    builder = Gtk.Builder()
    builder.add_from_file(str(path))
    window = builder.get_object("shortcuts")
    if not isinstance(window, Gtk.ShortcutsWindow):
        return None
    window.set_transient_for(parent)
    window.set_hide_on_close(True)
    window.present()
    return window


def present_about(parent: Gtk.Window) -> None:
    dialog = Adw.AboutDialog(
        application_name=_("Manutenção Pro"),
        application_icon="dev.ricardo.ManutencaoPro",
        version=__version__,
        developer_name="Ricardo Medlo Valus",
        copyright="© 2026 Ricardo Medlo Valus",
        website="https://github.com/RicardoValus/maintenence_pro",
        license_type=Gtk.License.MIT_X11,
        comments=_("Manutenção diária do Debian: pacotes, DKMS, microcode, firmware e driver NVIDIA."),
    )
    dialog.present(parent)
