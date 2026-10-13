from __future__ import annotations

from manutencao_pro.audit_model import (
    CARGO_NAME,
    EXT_ID,
    FLATPAK_ID,
    FLATPAK_ORIGIN,
    NPM_NAME,
    PY_NAME,
    SNAP_NAME,
    VERSION,
    ManualItem,
    RemotePackage,
    ToolPackage,
)
from manutencao_pro.audit_plan import PlannedAction, _already, _missing
from manutencao_pro.i18n import _


def _plan_npm(desired, current, tools, actions, skipped, manual) -> None:
    installed = {item.name: item.version for item in current.npm_packages}
    pending = _pending_tools(desired.npm_packages, installed, NPM_NAME, "npm", skipped, manual)
    _emit_tools(pending, tools.get("npm"), "npm", _npm_command, actions, manual, False)


def _plan_pip(desired, current, tools, actions, skipped, manual) -> None:
    installed = {item.name: item.version for item in current.pip_packages}
    pending = _pending_tools(desired.pip_packages, installed, PY_NAME, "pip", skipped, manual)
    _emit_tools(pending, tools.get("python3"), "pip", _pip_command, actions, manual, False)


def _plan_cargo(desired, current, tools, actions, skipped, manual) -> None:
    installed = {item.name: item.version for item in current.cargo_packages}
    pending = _pending_tools(desired.cargo_packages, installed, CARGO_NAME, "cargo", skipped, manual)
    _emit_tools(pending, tools.get("cargo"), "cargo", _cargo_command, actions, manual, False)


def _plan_flatpak(desired, current, tools, actions, skipped, manual) -> None:
    installed = {item.name: item.version for item in current.flatpaks}
    pending: list[RemotePackage] = []
    for package in desired.flatpaks:
        if FLATPAK_ID.fullmatch(package.name) is None or VERSION.fullmatch(package.version) is None:
            manual.append(ManualItem("flatpak", package.name or "?", _("identificador inválido")))
            continue
        if FLATPAK_ORIGIN.fullmatch(package.origin) is None:
            manual.append(ManualItem("flatpak", package.name, _("remote Flatpak ausente")))
            continue
        if _already(installed, package.name, package.version, "flatpak", skipped, manual):
            continue
        pending.append(package)
    binary = tools.get("flatpak")
    if not pending:
        return
    if not binary:
        _missing(manual, "flatpak", len(pending))
        return
    for package in pending:
        argv = (binary, "install", "-y", "--user", "--noninteractive", package.origin, package.name)
        summary = f"flatpak install -y --user {package.origin} {package.name}"
        actions.append(PlannedAction("command", summary, argv, False))


def _plan_snap(desired, current, tools, actions, skipped, manual) -> None:
    installed = {item.name: item.version for item in current.snaps}
    pending: list[RemotePackage] = []
    for package in desired.snaps:
        if SNAP_NAME.fullmatch(package.name) is None or VERSION.fullmatch(package.version) is None:
            manual.append(ManualItem("snap", package.name or "?", _("identificador inválido")))
            continue
        if _already(installed, package.name, package.version, "snap", skipped, manual):
            continue
        pending.append(package)
    binary = tools.get("snap")
    if not pending:
        return
    if not binary:
        _missing(manual, "snap", len(pending))
        return
    for package in pending:
        argv = [binary, "install"]
        if package.classic:
            argv.append("--classic")
        argv.append(package.name)
        classic = " --classic" if package.classic else ""
        summary = _("snap install{classic} {name} (administrador)").format(classic=classic, name=package.name)
        actions.append(PlannedAction("command", summary, tuple(argv), True))


def _plan_extensions(desired, current, tools, actions, skipped, manual) -> None:
    installed = {(item.editor, item.identifier): item.version for item in current.extensions}
    pending: dict[str, list] = {"code": [], "cursor": []}
    for item in desired.extensions:
        if item.editor not in pending or EXT_ID.fullmatch(item.identifier) is None or VERSION.fullmatch(item.version) is None:
            manual.append(ManualItem("extension", item.identifier or "?", _("identificador inválido")))
            continue
        key = (item.editor, item.identifier)
        if key in installed:
            if installed[key] != item.version:
                manual.append(
                    ManualItem(
                        "extension",
                        item.identifier,
                        _("instalado {current}, o backup pede {desired}").format(current=installed[key], desired=item.version),
                    )
                )
            else:
                skipped.append(f"{item.editor} {item.identifier}")
            continue
        pending[item.editor].append(item)
    for editor, items in pending.items():
        if not items:
            continue
        binary = tools.get(editor)
        if not binary:
            _missing(manual, editor, len(items))
            continue
        for item in items:
            spec = f"{item.identifier}@{item.version}"
            summary = _("{editor} --install-extension {spec}").format(editor=editor, spec=spec)
            actions.append(PlannedAction("command", summary, (binary, "--install-extension", spec), False))


def _pending_tools(packages, installed: dict[str, str], pattern, category: str, skipped, manual) -> list[ToolPackage]:
    pending: list[ToolPackage] = []
    for package in packages:
        if pattern.fullmatch(package.name) is None or VERSION.fullmatch(package.version) is None:
            manual.append(ManualItem(category, package.name or "?", _("identificador inválido")))
            continue
        if _already(installed, package.name, package.version, category, skipped, manual):
            continue
        pending.append(package)
    return pending


def _emit_tools(pending, binary: str | None, category: str, command, actions, manual, needs_root: bool) -> None:
    if not pending:
        return
    if not binary:
        _missing(manual, category, len(pending))
        return
    for package in pending:
        argv, summary = command(binary, package)
        actions.append(PlannedAction("command", summary, argv, needs_root))


def _npm_command(binary: str, package: ToolPackage) -> tuple[tuple[str, ...], str]:
    spec = f"{package.name}@{package.version}"
    return (binary, "install", "-g", spec), f"npm install -g {spec}"


def _pip_command(binary: str, package: ToolPackage) -> tuple[tuple[str, ...], str]:
    spec = f"{package.name}=={package.version}"
    argv = (binary, "-m", "pip", "install", "--user", "--disable-pip-version-check", spec)
    return argv, f"python3 -m pip install --user {spec}"


def _cargo_command(binary: str, package: ToolPackage) -> tuple[tuple[str, ...], str]:
    argv = (binary, "install", package.name, "--version", package.version)
    return argv, f"cargo install {package.name} --version {package.version}"


