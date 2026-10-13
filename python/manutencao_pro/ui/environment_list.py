from __future__ import annotations

from gi.repository import GObject, Gtk, Pango

from manutencao_pro.audit_model import AuditRow, EnvironmentSnapshot
from manutencao_pro.i18n import _

FILTERS = (
    ("all", _("Tudo")),
    ("apt", _("Pacotes apt")),
    ("repository", _("Repositórios")),
    ("npm", "npm"),
    ("pip", "pip"),
    ("cargo", "cargo"),
    ("flatpak", "Flatpak"),
    ("snap", "Snap"),
    ("environment", _("Variáveis")),
    ("extension", _("Extensões")),
    ("manual", _("Ação manual")),
)


class AuditItem(GObject.Object):
    __gtype_name__ = "ManutencaoProAuditItem"

    def __init__(self, category_id: str, category: str, name: str, version: str, detail: str) -> None:
        super().__init__()
        self.category_id = category_id
        self.category = category
        self.name = name
        self.version = version
        self.detail = detail


def column(title: str, attribute: str) -> Gtk.ColumnViewColumn:
    factory = Gtk.SignalListItemFactory()

    def setup(_factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
        label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, hexpand=True)
        item.set_child(label)

    def bind(_factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
        row = item.get_item()
        child = item.get_child()
        if isinstance(row, AuditItem) and isinstance(child, Gtk.Label):
            child.set_label(str(getattr(row, attribute)))

    factory.connect("setup", setup)
    factory.connect("bind", bind)
    view_column = Gtk.ColumnViewColumn(title=title, factory=factory)
    view_column.set_expand(attribute in {"name", "detail"})
    view_column.set_resizable(True)
    return view_column


def item_from_row(row: AuditRow) -> AuditItem:
    detail = _("sessão") if row.category_id == "environment" and row.detail == "session" else row.detail
    return AuditItem(row.category_id, category_label(row.category_id), row.name, row.version, detail)


def category_label(category_id: str) -> str:
    for key, label in FILTERS:
        if key == category_id:
            return label
    return category_id


def status_text(snapshot: EnvironmentSnapshot, visible: int) -> str:
    text = _("{count} itens").format(count=visible)
    if snapshot.unavailable:
        missing = ", ".join(snapshot.unavailable)
        text = _("{count} itens. Não encontrados: {missing}").format(count=visible, missing=missing)
    return text
