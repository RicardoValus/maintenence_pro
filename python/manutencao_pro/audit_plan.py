from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from manutencao_pro.audit_model import (
    APT_BATCH_SIZE,
    APT_NAME,
    SOURCE_SESSION,
    USER_SHELL_FILES,
    VERSION,
    EnvironmentSnapshot,
    ManualItem,
    repo_destination,
)
from manutencao_pro.audit_parse import is_local_repository, safe_env_line
from manutencao_pro.i18n import _

LIMITATION = _(
    "Licenças de software e configurações de interface gráfica "
    "(dconf, temas, atalhos) não são migradas por este backup."
)


@dataclass(frozen=True)
class PlannedAction:
    kind: str
    summary: str
    argv: tuple[str, ...] = ()
    needs_root: bool = False
    path: str = ""
    content: str = ""


@dataclass(frozen=True)
class ImportPlan:
    actions: tuple[PlannedAction, ...]
    skipped: tuple[str, ...]
    manual: tuple[ManualItem, ...]


def detect_tools() -> dict[str, str | None]:
    fallbacks = {
        "apt-get": "/usr/bin/apt-get",
        "env": "/usr/bin/env",
        "npm": "/usr/bin/npm",
        "python3": "/usr/bin/python3",
        "cargo": "/usr/bin/cargo",
        "flatpak": "/usr/bin/flatpak",
        "snap": "/usr/bin/snap",
        "code": "/usr/bin/code",
        "cursor": "/usr/bin/cursor",
        "install": "/usr/bin/install",
    }
    found: dict[str, str | None] = {}
    for name, fallback in fallbacks.items():
        located = shutil.which(name)
        if located:
            found[name] = located
        elif Path(fallback).is_file():
            found[name] = fallback
        else:
            found[name] = None
    return found


def build_plan(
    desired: EnvironmentSnapshot,
    current: EnvironmentSnapshot,
    tools: dict[str, str | None] | None = None,
    *,
    apt_batch: int = APT_BATCH_SIZE,
) -> ImportPlan:
    from manutencao_pro.audit_install import (
        _plan_cargo,
        _plan_extensions,
        _plan_flatpak,
        _plan_npm,
        _plan_pip,
        _plan_snap,
    )

    resolved = detect_tools() if tools is None else tools
    actions: list[PlannedAction] = []
    skipped: list[str] = []
    manual = list(desired.manual)
    _plan_repositories(desired, current, actions, skipped, manual)
    _plan_apt(desired, current, resolved, actions, skipped, manual, apt_batch)
    _plan_npm(desired, current, resolved, actions, skipped, manual)
    _plan_pip(desired, current, resolved, actions, skipped, manual)
    _plan_cargo(desired, current, resolved, actions, skipped, manual)
    _plan_flatpak(desired, current, resolved, actions, skipped, manual)
    _plan_snap(desired, current, resolved, actions, skipped, manual)
    _plan_extensions(desired, current, resolved, actions, skipped, manual)
    _plan_env(desired, current, actions, skipped, manual)
    return ImportPlan(tuple(actions), tuple(skipped), tuple(manual))


def format_plan(plan: ImportPlan) -> str:
    lines = [_("Vai executar:")]
    if plan.actions:
        lines.extend(f"{index}. {action.summary}" for index, action in enumerate(plan.actions, start=1))
    else:
        lines.append(_("Nenhuma alteração automática."))
    lines.append("")
    lines.append(_("Já instalado ou configurado:"))
    if plan.skipped:
        lines.extend(f"- {item}" for item in plan.skipped)
    else:
        lines.append(_("Nada a pular."))
    return "\n".join(lines)


def format_manual_report(items: tuple[ManualItem, ...] | list[ManualItem]) -> str:
    if not items:
        body = _("Nenhuma ação manual pendente.")
    else:
        body = "\n".join(f"- [{item.category}] {item.name}: {item.reason}" for item in items)
    return body + "\n\n" + LIMITATION


def _plan_repositories(desired, current, actions, skipped, manual) -> None:
    existing = {item.filename: _normalize(item.content) for item in current.repositories}
    for repo in desired.repositories:
        destination = repo_destination(repo.filename)
        content = _normalize(repo.content)
        if destination is None or not content.strip():
            manual.append(ManualItem("repository", repo.filename or "?", _("arquivo de repositório inválido")))
            continue
        if is_local_repository(content):
            manual.append(ManualItem("repository", repo.filename, _("origem local (file: ou cdrom:); confira o caminho")))
        current_text = existing.get(repo.filename)
        if current_text is None:
            actions.append(
                PlannedAction(
                    "system_write",
                    _("gravar {path} (administrador)").format(path=destination),
                    needs_root=True,
                    path=destination,
                    content=content,
                )
            )
            continue
        if current_text == content:
            skipped.append(_("repositório {name}").format(name=repo.filename))
            continue
        manual.append(ManualItem("repository", repo.filename, _("arquivo já existe com outro conteúdo")))


def _plan_apt(desired, current, tools, actions, skipped, manual, apt_batch: int) -> None:
    installed = {item.name: item.version for item in current.apt_packages}
    pending: list[str] = []
    for package in desired.apt_packages:
        if package.origin == "local":
            manual.append(ManualItem("apt", package.name, _("instalado localmente, sem repositório")))
            continue
        if APT_NAME.fullmatch(package.name) is None or VERSION.fullmatch(package.version) is None:
            manual.append(ManualItem("apt", package.name or "?", _("identificador inválido")))
            continue
        if _already(installed, package.name, package.version, "apt", skipped, manual):
            continue
        pending.append(package.name)
    if not pending and not any(action.kind == "system_write" for action in actions):
        return
    update = _apt_argv(tools, "update")
    if update is None:
        manual.append(ManualItem("apt", "apt-get", _("ferramenta ausente nesta máquina")))
        return
    actions.append(PlannedAction("command", _("apt-get update (administrador)"), update, True))
    for batch in _batches(pending, apt_batch):
        install = _apt_argv(tools, "install", "-y", *batch)
        if install is None:
            continue
        summary = _("apt-get install -y {packages} (administrador)").format(packages=" ".join(batch))
        actions.append(PlannedAction("command", summary, install, True))


def _plan_env(desired, current, actions, skipped, manual) -> None:
    existing = {(item.source, item.name): item for item in current.variables}
    for var in desired.variables:
        if var.source == SOURCE_SESSION or not var.raw_line:
            manual.append(ManualItem("environment", var.name, _("só existe na sessão atual")))
            continue
        if var.source not in USER_SHELL_FILES or not safe_env_line(var.raw_line, var.source):
            manual.append(ManualItem("environment", var.name, _("linha de ambiente inválida")))
            continue
        current_var = existing.get((var.source, var.name))
        if current_var is not None and current_var.value == var.value:
            skipped.append(_("variável {name}").format(name=var.name))
            continue
        if current_var is not None:
            manual.append(ManualItem("environment", var.name, _("já definida com outro valor")))
            continue
        actions.append(
            PlannedAction(
                "user_append",
                _("anexar em {source}: {line}").format(source=var.source, line=var.raw_line),
                path=var.source,
                content=var.raw_line,
            )
        )


def _already(installed: dict[str, str], name: str, version: str, category: str, skipped: list[str], manual: list[ManualItem]) -> bool:
    if name not in installed:
        return False
    if installed[name] != version:
        manual.append(
            ManualItem(
                category,
                name,
                _("instalado {current}, o backup pede {desired}").format(current=installed[name], desired=version),
            )
        )
    else:
        skipped.append(f"{category} {name}")
    return True


def _missing(manual: list[ManualItem], tool: str, count: int) -> None:
    manual.append(
        ManualItem(
            tool,
            tool,
            _("ferramenta ausente; {count} itens não serão instalados").format(count=count),
        )
    )


def _apt_argv(tools: dict[str, str | None], *args: str) -> tuple[str, ...] | None:
    apt = tools.get("apt-get")
    if not apt:
        return None
    env = tools.get("env")
    if env:
        return (env, "DEBIAN_FRONTEND=noninteractive", "NEEDRESTART_MODE=a", apt, *args)
    return (apt, *args)


def _batches(names: list[str], size: int) -> list[list[str]]:
    if size < 1:
        size = APT_BATCH_SIZE
    return [names[index : index + size] for index in range(0, len(names), size)]


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").strip() + "\n"
