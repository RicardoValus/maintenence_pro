from __future__ import annotations

import json
import re

from manutencao_pro.audit_model import (
    APT_NAME,
    CARGO_NAME,
    EXT_ID,
    FLATPAK_ID,
    MAX_REPO_CHARS,
    NPM_NAME,
    PY_NAME,
    SCHEMA_VERSION,
    SNAP_NAME,
    VERSION,
    AptPackage,
    EnvVariable,
    EnvironmentSnapshot,
    Extension,
    ManualItem,
    RemotePackage,
    Repository,
    SchemaError,
    SystemOrigin,
    ToolPackage,
    canonicalize,
    normalize_apt_name,
    repo_destination,
)
from manutencao_pro.i18n import _


def dumps_snapshot(snapshot: EnvironmentSnapshot) -> str:
    payload = {
        "schema_version": snapshot.schema_version,
        "system": _system_dict(snapshot.system) if snapshot.system is not None else None,
        "apt_packages": [_apt_dict(item) for item in snapshot.apt_packages],
        "repositories": [_repo_dict(item) for item in snapshot.repositories],
        "npm_packages": [_tool_dict(item) for item in snapshot.npm_packages],
        "pip_packages": [_tool_dict(item) for item in snapshot.pip_packages],
        "cargo_packages": [_tool_dict(item) for item in snapshot.cargo_packages],
        "flatpaks": [_remote_dict(item) for item in snapshot.flatpaks],
        "snaps": [_snap_dict(item) for item in snapshot.snaps],
        "environment": [_env_dict(item) for item in snapshot.variables],
        "extensions": [_ext_dict(item) for item in snapshot.extensions],
        "manual": [_manual_dict(item) for item in snapshot.manual],
        "unavailable": list(snapshot.unavailable),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def loads_snapshot(text: str) -> EnvironmentSnapshot:
    try:
        payload = json.loads(text.lstrip("\ufeff"))
    except json.JSONDecodeError as exc:
        raise SchemaError(_("JSON inválido")) from exc
    if not isinstance(payload, dict):
        raise SchemaError(_("O arquivo precisa ser um objeto JSON."))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SchemaError(_("schema_version incompatível"))
    manual = _load_manual(payload)
    apt, apt_manual = _load_apt(payload)
    manual.extend(apt_manual)
    repos, repo_manual = _load_repos(payload)
    manual.extend(repo_manual)
    return canonicalize(
        EnvironmentSnapshot(
            apt_packages=tuple(apt),
            repositories=tuple(repos),
            npm_packages=_load_tools(payload, "npm_packages", manual, "npm"),
            pip_packages=_load_tools(payload, "pip_packages", manual, "pip"),
            cargo_packages=_load_tools(payload, "cargo_packages", manual, "cargo"),
            flatpaks=_load_flatpaks(payload, manual),
            snaps=_load_snaps(payload, manual),
            variables=_load_env(payload, manual),
            extensions=_load_extensions(payload, manual),
            manual=tuple(manual),
            unavailable=_load_strings(payload, "unavailable"),
            system=_load_system(payload),
        )
    )


def _system_dict(item: SystemOrigin) -> dict[str, str]:
    return {
        "id": item.distro,
        "version_id": item.version_id,
        "version_codename": item.codename,
        "architecture": item.architecture,
    }


def _load_system(payload: dict[str, object]) -> SystemOrigin | None:
    raw = payload.get("system")
    if not isinstance(raw, dict):
        return None
    distro = _text(raw, "id")
    if not distro:
        return None
    return SystemOrigin(distro, _text(raw, "version_id"), _text(raw, "version_codename"), _text(raw, "architecture"))


def _apt_dict(item: AptPackage) -> dict[str, str]:
    return {"name": item.name, "version": item.version, "origin": item.origin}


def _repo_dict(item: Repository) -> dict[str, str]:
    return {"filename": item.filename, "content": item.content}


def _tool_dict(item: ToolPackage) -> dict[str, str]:
    return {"name": item.name, "version": item.version}


def _remote_dict(item: RemotePackage) -> dict[str, str]:
    return {"name": item.name, "version": item.version, "origin": item.origin}


def _snap_dict(item: RemotePackage) -> dict[str, object]:
    return {"name": item.name, "version": item.version, "origin": item.origin, "classic": item.classic}


def _env_dict(item: EnvVariable) -> dict[str, str]:
    return {"name": item.name, "value": item.value, "source": item.source, "line": item.raw_line}


def _ext_dict(item: Extension) -> dict[str, str]:
    return {"editor": item.editor, "id": item.identifier, "version": item.version}


def _manual_dict(item: ManualItem) -> dict[str, str]:
    return {"category": item.category, "name": item.name, "reason": item.reason}


def _records(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise SchemaError(_("campo {name} inválido").format(name=key))
    return value


def _load_strings(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SchemaError(_("campo {name} inválido").format(name=key))
    return tuple(value)


def _load_manual(payload: dict[str, object]) -> list[ManualItem]:
    items: list[ManualItem] = []
    for entry in _records(payload, "manual"):
        parsed = _manual_entry(entry)
        if parsed is not None:
            items.append(parsed)
    return items


def _manual_entry(entry: object) -> ManualItem | None:
    if not isinstance(entry, dict):
        return ManualItem("manual", "?", _("entrada inválida"))
    category = entry.get("category")
    name = entry.get("name")
    reason = entry.get("reason")
    if not all(isinstance(item, str) and item for item in (category, name, reason)):
        return ManualItem("manual", "?", _("entrada inválida"))
    return ManualItem(str(category), str(name), str(reason))


def _load_apt(payload: dict[str, object]) -> tuple[list[AptPackage], list[ManualItem]]:
    packages: list[AptPackage] = []
    manual: list[ManualItem] = []
    for entry in _records(payload, "apt_packages"):
        if not isinstance(entry, dict):
            manual.append(ManualItem("apt", "?", _("entrada inválida")))
            continue
        name = normalize_apt_name(_text(entry, "name"))
        version = _text(entry, "version")
        origin = _text(entry, "origin") or "desconhecida"
        if APT_NAME.fullmatch(name) is None or VERSION.fullmatch(version) is None:
            manual.append(ManualItem("apt", name or "?", _("entrada inválida")))
            continue
        packages.append(AptPackage(name, version, origin))
    return packages, manual


def _load_repos(payload: dict[str, object]) -> tuple[list[Repository], list[ManualItem]]:
    repos: list[Repository] = []
    manual: list[ManualItem] = []
    for entry in _records(payload, "repositories"):
        if not isinstance(entry, dict):
            manual.append(ManualItem("repository", "?", _("entrada inválida")))
            continue
        filename = _text(entry, "filename")
        content = entry.get("content")
        if not isinstance(content, str) or "\x00" in content or len(content) > MAX_REPO_CHARS:
            manual.append(ManualItem("repository", filename or "?", "arquivo de repositório inválido"))
            continue
        if repo_destination(filename) is None:
            manual.append(ManualItem("repository", filename or "?", "nome de arquivo inválido"))
            continue
        repos.append(Repository(filename, content))
    return repos, manual


def _load_tools(payload: dict[str, object], key: str, manual: list[ManualItem], category: str) -> tuple[ToolPackage, ...]:
    packages: list[ToolPackage] = []
    pattern = {"npm": NPM_NAME, "pip": PY_NAME, "cargo": CARGO_NAME}[category]
    for entry in _records(payload, key):
        if not isinstance(entry, dict):
            manual.append(ManualItem(category, "?", _("entrada inválida")))
            continue
        name = _text(entry, "name")
        version = _text(entry, "version")
        if pattern.fullmatch(name) is None or VERSION.fullmatch(version) is None:
            manual.append(ManualItem(category, name or "?", _("entrada inválida")))
            continue
        packages.append(ToolPackage(name, version))
    return tuple(packages)


def _load_flatpaks(payload: dict[str, object], manual: list[ManualItem]) -> tuple[RemotePackage, ...]:
    packages: list[RemotePackage] = []
    for entry in _records(payload, "flatpaks"):
        parsed = _remote(entry, FLATPAK_ID, "flatpak", manual)
        if parsed is not None:
            packages.append(parsed)
    return tuple(packages)


def _load_snaps(payload: dict[str, object], manual: list[ManualItem]) -> tuple[RemotePackage, ...]:
    packages: list[RemotePackage] = []
    for entry in _records(payload, "snaps"):
        parsed = _remote(entry, SNAP_NAME, "snap", manual)
        if parsed is None:
            continue
        classic = bool(entry.get("classic")) if isinstance(entry, dict) else False
        packages.append(RemotePackage(parsed.name, parsed.version, parsed.origin, classic))
    return tuple(packages)


def _remote(entry: object, pattern: re.Pattern[str], category: str, manual: list[ManualItem]) -> RemotePackage | None:
    if not isinstance(entry, dict):
        manual.append(ManualItem(category, "?", _("entrada inválida")))
        return None
    name = _text(entry, "name")
    version = _text(entry, "version")
    origin = _text(entry, "origin")
    if pattern.fullmatch(name) is None or VERSION.fullmatch(version) is None:
        manual.append(ManualItem(category, name or "?", _("entrada inválida")))
        return None
    return RemotePackage(name, version, origin)


def _load_extensions(payload: dict[str, object], manual: list[ManualItem]) -> tuple[Extension, ...]:
    items: list[Extension] = []
    for entry in _records(payload, "extensions"):
        if not isinstance(entry, dict):
            manual.append(ManualItem("extension", "?", _("entrada inválida")))
            continue
        editor = _text(entry, "editor")
        identifier = _text(entry, "id")
        version = _text(entry, "version")
        if editor not in {"code", "cursor"} or EXT_ID.fullmatch(identifier) is None or VERSION.fullmatch(version) is None:
            manual.append(ManualItem("extension", identifier or "?", _("entrada inválida")))
            continue
        items.append(Extension(editor, identifier, version))
    return tuple(items)


def _load_env(payload: dict[str, object], manual: list[ManualItem]) -> tuple[EnvVariable, ...]:
    from manutencao_pro.audit_parse import stored_variable

    items: list[EnvVariable] = []
    for entry in _records(payload, "environment"):
        if not isinstance(entry, dict):
            manual.append(ManualItem("environment", "?", _("entrada inválida")))
            continue
        stored = stored_variable(_text(entry, "name"), _text(entry, "value"), _text(entry, "source"), _text(entry, "line"))
        if isinstance(stored, ManualItem):
            manual.append(stored)
            continue
        items.append(stored)
    return tuple(items)


def _text(entry: dict[str, object], key: str) -> str:
    value = entry.get(key, "")
    if not isinstance(value, str):
        return ""
    return value
