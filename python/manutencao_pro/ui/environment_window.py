from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from manutencao_pro.audit_apply import ProductionHooks, apply_plan
from manutencao_pro.audit_collect import collect_environment
from manutencao_pro.audit_model import (
    EnvironmentSnapshot,
    ManualItem,
    SchemaError,
    iter_rows,
    row_matches,
    snapshot_for_export,
)
from manutencao_pro.audit_plan import ImportPlan, build_plan, format_manual_report, format_plan
from manutencao_pro.audit_schema import dumps_snapshot, loads_snapshot
from manutencao_pro.i18n import _
from manutencao_pro.ui.dialogs import confirm_os_mismatch, show_error
from manutencao_pro.ui.environment_choices import ExportChoices
from manutencao_pro.ui.environment_dialogs import ImportDialog, present_open_json, present_save_json
from manutencao_pro.ui.environment_list import FILTERS, AuditItem, column, item_from_row, status_text
from manutencao_pro.ui.motion import ProgressPulse, fade
from manutencao_pro.ui.theme import apply_app_theme


class EnvironmentWindow(Adw.Window):
    def __init__(self, parent: Gtk.Window | None, can_apply: Callable[[], str | None], *, autoload: bool = True) -> None:
        super().__init__(transient_for=parent, destroy_with_parent=True, title=_("Ambiente de desenvolvimento"))
        self.add_css_class("mp-app")
        apply_app_theme()
        self.set_default_size(960, 700)
        if parent is not None and parent.get_application() is not None:
            self.set_application(parent.get_application())
        self._can_apply = can_apply
        self._snapshot: EnvironmentSnapshot | None = None
        self._generation = 0
        self._busy = False
        self._importing = False
        self._closed = False
        self._query = ""
        self._selected = "all"
        self._cookie = 0
        self._dialog: ImportDialog | None = None
        self._build()
        self.connect("close-request", self._on_close_request)
        self.connect("destroy", lambda *_args: self._mark_closed())
        if autoload:
            self.refresh()

    def refresh(self) -> None:
        if self._busy or self._importing:
            return
        self._generation += 1
        generation = self._generation
        self._set_busy(True, _("Lendo pacotes, repositórios e ferramentas…"))
        threading.Thread(target=self._load, args=(generation,), daemon=True).start()

    def display_snapshot(self, snapshot: EnvironmentSnapshot) -> None:
        refreshing = self._list_revealer.get_reveal_child()
        if refreshing:
            self._view.set_opacity(0.45)
        self._snapshot = snapshot
        self._fill(snapshot)
        self._set_busy(False, status_text(snapshot, self._filtered.get_n_items()))
        self._list_revealer.set_reveal_child(True)
        self._choices_revealer.set_reveal_child(True)
        if refreshing:
            fade(self._view, 0.45, 1, 240)

    def _build(self) -> None:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, vexpand=True)
        page.set_margin_top(16)
        page.set_margin_bottom(16)
        page.set_margin_start(16)
        page.set_margin_end(16)
        page.append(self._build_filters())
        page.append(self._build_list())
        page.append(self._build_status())
        page.append(self._build_choices())
        page.append(self._build_buttons())
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(page)
        self.toast = Adw.ToastOverlay()
        self.toast.set_child(toolbar)
        self.set_content(self.toast)

    def _build_filters(self) -> Gtk.Box:
        self.search = Gtk.SearchEntry(placeholder_text=_("Buscar pacote, repositório ou variável"), hexpand=True)
        self.search.connect("search-changed", self._on_search)
        self.category = Gtk.DropDown.new_from_strings([label for _category, label in FILTERS])
        self.category.connect("notify::selected", self._on_category)
        filters = Gtk.Box(spacing=8)
        filters.append(self.search)
        filters.append(self.category)
        return filters

    def _build_list(self) -> Gtk.Box:
        self._store = Gio.ListStore.new(AuditItem)
        self._filter = Gtk.CustomFilter.new(self._match_item)
        self._filtered = Gtk.FilterListModel(model=self._store, filter=self._filter)
        self._filtered.connect("items-changed", lambda *_args: self._on_items_changed())
        self._view = Gtk.ColumnView(model=Gtk.NoSelection(model=self._filtered))
        self._view.add_css_class("mp-audit")
        self._view.set_show_row_separators(False)
        self._view.set_show_column_separators(False)
        for title, attribute in (
            (_("Categoria"), "category"),
            (_("Nome"), "name"),
            (_("Versão"), "version"),
            (_("Detalhe"), "detail"),
        ):
            self._view.append_column(column(title, attribute))
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vexpand=True,
        )
        scroll.add_css_class("mp-card")
        scroll.set_child(self._view)
        self.pulse = Gtk.ProgressBar()
        self.pulse.add_css_class("mp-pulse")
        self.pulse.set_visible(False)
        self._pulse = ProgressPulse(self.pulse)
        self._list_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.CROSSFADE,
            transition_duration=280,
            vexpand=True,
            child=scroll,
        )
        board = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, vexpand=True)
        board.append(self.pulse)
        board.append(self._list_revealer)
        return board

    def _build_status(self) -> Gtk.Box:
        self.spinner = Adw.Spinner()
        self.spinner.set_visible(False)
        self.status = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.status.add_css_class("dim-label")
        self.status.add_css_class("mp-mono")
        row = Gtk.Box(spacing=8)
        row.append(self.spinner)
        row.append(self.status)
        return row

    def _build_choices(self) -> Gtk.Revealer:
        self._choices = ExportChoices()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        caption = Gtk.Label(label=_("Incluir no backup"), xalign=0)
        caption.add_css_class("mp-kicker")
        caption.add_css_class("mp-mono")
        box.append(caption)
        box.append(self._choices)
        self._choices_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            transition_duration=240,
            child=box,
        )
        return self._choices_revealer

    def _build_buttons(self) -> Gtk.Box:
        self.refresh_button = Gtk.Button(label=_("Atualizar"))
        self.refresh_button.add_css_class("pill")
        self.copy_button = Gtk.Button(label=_("Copiar tudo"))
        self.copy_button.add_css_class("pill")
        self.export_button = Gtk.Button(label=_("Exportar"))
        self.export_button.add_css_class("pill")
        self.import_button = Gtk.Button(label=_("Importar"))
        self.import_button.add_css_class("pill")
        self.import_button.add_css_class("suggested-action")
        self.refresh_button.connect("clicked", lambda *_args: self.refresh())
        self.copy_button.connect("clicked", lambda *_args: self._copy_export())
        self.export_button.connect("clicked", lambda *_args: self._export())
        self.import_button.connect("clicked", lambda *_args: self._import())
        self.copy_button.set_sensitive(False)
        self.export_button.set_sensitive(False)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        buttons.append(self.refresh_button)
        buttons.append(self.copy_button)
        buttons.append(self.export_button)
        buttons.append(self.import_button)
        return buttons

    def _load(self, generation: int) -> None:
        try:
            snapshot = collect_environment()
        except Exception as exc:
            GLib.idle_add(self._load_failed, generation, str(exc))
            return
        GLib.idle_add(self._load_done, generation, snapshot)

    def _load_done(self, generation: int, snapshot: EnvironmentSnapshot) -> bool:
        if self._closed or generation != self._generation:
            return False
        self.display_snapshot(snapshot)
        return False

    def _load_failed(self, generation: int, message: str) -> bool:
        if self._closed or generation != self._generation:
            return False
        self._set_busy(False, _("Não foi possível ler o ambiente"))
        show_error(self, _("Não foi possível ler o ambiente"), message)
        return False

    def _fill(self, snapshot: EnvironmentSnapshot) -> None:
        self._store.remove_all()
        for row in iter_rows(snapshot):
            self._store.append(item_from_row(row))

    def _match_item(self, item: AuditItem, *_rest: object) -> bool:
        return row_matches(
            item.category_id,
            item.name,
            item.version,
            item.detail,
            item.category,
            query=self._query,
            selected=self._selected,
        )

    def _on_search(self, entry: Gtk.SearchEntry) -> None:
        self._query = entry.get_text()
        self._filter.changed(Gtk.FilterChange.DIFFERENT)

    def _on_category(self, dropdown: Gtk.DropDown, _param: GObject.ParamSpec) -> None:
        index = dropdown.get_selected()
        self._selected = FILTERS[index][0] if 0 <= index < len(FILTERS) else "all"
        self._filter.changed(Gtk.FilterChange.DIFFERENT)

    def _on_items_changed(self) -> None:
        if self._busy or self._snapshot is None:
            return
        self.status.set_label(status_text(self._snapshot, self._filtered.get_n_items()))

    def _export_snapshot(self) -> EnvironmentSnapshot | None:
        if self._snapshot is None:
            return None
        selected = self._choices.selected()
        if not selected:
            self.toast.add_toast(Adw.Toast(title=_("Marque o que entra no backup"), timeout=3))
            return None
        return snapshot_for_export(self._snapshot, set(selected))

    def _copy_export(self) -> None:
        snapshot = self._export_snapshot()
        display = self.get_display()
        if snapshot is None or display is None:
            return
        display.get_clipboard().set(dumps_snapshot(snapshot))
        self.toast.add_toast(Adw.Toast(title=_("Backup copiado"), timeout=2))

    def _export(self) -> None:
        if self._snapshot is None or self._busy or self._export_snapshot() is None:
            return
        present_save_json(self, self._write_export)

    def _write_export(self, chosen: Gio.File) -> None:
        snapshot = self._export_snapshot()
        if snapshot is None:
            return
        data = dumps_snapshot(snapshot).encode("utf-8")
        try:
            chosen.replace_contents(data, None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None)
        except GLib.Error as error:
            show_error(self, _("Não foi possível exportar"), error.message)
            return
        self.status.set_label(_("Ambiente exportado"))

    def _import(self) -> None:
        if self._busy or self._importing:
            return
        present_open_json(self, self._read_import)

    def _read_import(self, chosen: Gio.File) -> None:
        path = chosen.get_path()
        if not path:
            show_error(self, _("Não foi possível importar"), _("O arquivo escolhido não está no disco local."))
            return
        self._generation += 1
        generation = self._generation
        self._set_busy(True, _("Preparando a importação…"))
        threading.Thread(target=self._prepare_import, args=(generation, path), daemon=True).start()

    def _prepare_import(self, generation: int, path: str) -> None:
        try:
            desired = loads_snapshot(Path(path).read_text(encoding="utf-8"))
            current = collect_environment()
            plan = build_plan(desired, current)
        except (OSError, SchemaError, UnicodeError) as exc:
            GLib.idle_add(self._import_failed, generation, str(exc))
            return
        GLib.idle_add(self._present_plan, generation, plan)

    def _import_failed(self, generation: int, message: str) -> bool:
        if self._closed or generation != self._generation:
            return False
        self._set_busy(False, _("Não foi possível importar"))
        show_error(self, _("Não foi possível importar"), message)
        return False

    def _present_plan(self, generation: int, plan: ImportPlan) -> bool:
        if self._closed or generation != self._generation:
            return False
        self._set_busy(False, _("Conferência pronta"))
        if plan.warning and self._can_apply() is None:
            confirm_os_mismatch(self, plan.warning, lambda: self._open_plan(plan))
            return False
        self._open_plan(plan)
        return False

    def _open_plan(self, plan: ImportPlan) -> None:
        self._dialog = ImportDialog(
            format_plan(plan),
            format_manual_report(plan.manual),
            self._can_apply(),
            lambda: self._start_apply(plan),
            plan.warning or None,
        )
        self._dialog.present(self)

    def _start_apply(self, plan: ImportPlan) -> None:
        if self._importing or self._dialog is None or self._can_apply() is not None:
            return
        self._importing = True
        self._dialog.begin_progress()
        self._inhibit()
        threading.Thread(target=self._apply, args=(plan,), daemon=False).start()

    def _apply(self, plan: ImportPlan) -> None:
        try:
            failures = apply_plan(plan, ProductionHooks(), self._on_apply_event, is_root=os.geteuid() == 0)
            report = format_manual_report(list(plan.manual) + failures)
        except Exception as exc:
            report = format_manual_report([ManualItem("import", _("importação"), str(exc))])
        GLib.idle_add(self._apply_finished, report)

    def _on_apply_event(self, ok: bool, summary: str, detail: str) -> None:
        label = _("ok") if ok else _("falha")
        if detail:
            line = _("{label} — {summary}: {detail}").format(label=label, summary=summary, detail=detail)
        else:
            line = _("{label} — {summary}").format(label=label, summary=summary)
        GLib.idle_add(self._append_log, line)

    def _append_log(self, line: str) -> bool:
        if self._closed or self._dialog is None:
            return False
        self._dialog.append_log(line)
        return False

    def _apply_finished(self, manual_text: str) -> bool:
        self._importing = False
        self._uninhibit()
        if self._dialog is not None and not self._closed:
            self._dialog.finish(manual_text)
        self.refresh()
        return False

    def _set_busy(self, busy: bool, status: str) -> None:
        self._busy = busy
        self.spinner.set_visible(busy)
        self.pulse.set_visible(busy)
        if busy:
            self._pulse.start()
        else:
            self._pulse.stop()
        ready = not busy and self._snapshot is not None
        self.refresh_button.set_sensitive(not busy and not self._importing)
        self.copy_button.set_sensitive(ready)
        self.export_button.set_sensitive(ready)
        self.import_button.set_sensitive(not busy and not self._importing)
        self._choices.set_interactive(not busy and not self._importing)
        self.status.set_label(status)

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        if not self._importing:
            return False
        show_error(self, _("Importação em andamento"), _("Espere a importação terminar para fechar."))
        return True

    def _mark_closed(self) -> None:
        self._closed = True
        self._pulse.stop()

    def _inhibit(self) -> None:
        app = self.get_application()
        if app is None:
            return
        self._cookie = app.inhibit(
            self,
            Gtk.ApplicationInhibitFlags.LOGOUT | Gtk.ApplicationInhibitFlags.SUSPEND,
            _("Importação do ambiente em andamento"),
        )

    def _uninhibit(self) -> None:
        app = self.get_application()
        if app is None or not self._cookie:
            return
        app.uninhibit(self._cookie)
        self._cookie = 0
