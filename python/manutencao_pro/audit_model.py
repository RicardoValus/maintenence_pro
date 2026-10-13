from __future__ import annotations

import re
from dataclasses import dataclass

SCHEMA_VERSION = 1
SOURCE_SESSION = "session"
USER_SHELL_FILES = (".bashrc", ".zshrc", ".profile", ".pam_environment")
APT_BATCH_SIZE = 80
MAX_REPO_CHARS = 256 * 1024
MAX_ENV_LINE = 1024

APT_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+~:_-]*$")
NPM_NAME = re.compile(r"^(@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$")
PY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CARGO_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SNAP_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FLATPAK_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")
FLATPAK_ORIGIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
EXT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+$")
REPO_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(?:list|sources)$")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CATEGORIES = (
    "all",
    "apt",
    "repository",
    "npm",
    "pip",
    "cargo",
    "flatpak",
    "snap",
    "environment",
    "extension",
    "manual",
)


class SchemaError(ValueError):
    pass


@dataclass(frozen=True)
class AptPackage:
    name: str
    version: str
    origin: str


@dataclass(frozen=True)
class Repository:
    filename: str
    content: str


@dataclass(frozen=True)
class ToolPackage:
    name: str
    version: str


@dataclass(frozen=True)
class RemotePackage:
    name: str
    version: str
    origin: str
    classic: bool = False


@dataclass(frozen=True)
class EnvVariable:
    name: str
    value: str
    source: str
    raw_line: str


@dataclass(frozen=True)
class Extension:
    editor: str
    identifier: str
    version: str


@dataclass(frozen=True)
class ManualItem:
    category: str
    name: str
    reason: str


@dataclass(frozen=True)
class AuditRow:
    category_id: str
    name: str
    version: str
    detail: str


@dataclass(frozen=True)
class SystemOrigin:
    distro: str
    version_id: str
    codename: str
    architecture: str


@dataclass(frozen=True)
class EnvironmentSnapshot:
    apt_packages: tuple[AptPackage, ...] = ()
    repositories: tuple[Repository, ...] = ()
    npm_packages: tuple[ToolPackage, ...] = ()
    pip_packages: tuple[ToolPackage, ...] = ()
    cargo_packages: tuple[ToolPackage, ...] = ()
    flatpaks: tuple[RemotePackage, ...] = ()
    snaps: tuple[RemotePackage, ...] = ()
    variables: tuple[EnvVariable, ...] = ()
    extensions: tuple[Extension, ...] = ()
    manual: tuple[ManualItem, ...] = ()
    unavailable: tuple[str, ...] = ()
    system: SystemOrigin | None = None
    schema_version: int = SCHEMA_VERSION


def canonicalize(snapshot: EnvironmentSnapshot) -> EnvironmentSnapshot:
    return EnvironmentSnapshot(
        apt_packages=_unique(snapshot.apt_packages, lambda item: item.name),
        repositories=_unique(snapshot.repositories, lambda item: item.filename),
        npm_packages=_unique(snapshot.npm_packages, lambda item: item.name),
        pip_packages=_unique(snapshot.pip_packages, lambda item: item.name),
        cargo_packages=_unique(snapshot.cargo_packages, lambda item: item.name),
        flatpaks=_unique(snapshot.flatpaks, lambda item: item.name),
        snaps=_unique(snapshot.snaps, lambda item: item.name),
        variables=_unique(snapshot.variables, lambda item: (item.source, item.name)),
        extensions=_unique(snapshot.extensions, lambda item: (item.editor, item.identifier)),
        manual=_unique(snapshot.manual, lambda item: (item.category, item.name, item.reason)),
        unavailable=tuple(sorted(set(snapshot.unavailable))),
        system=snapshot.system,
        schema_version=snapshot.schema_version,
    )


def iter_rows(snapshot: EnvironmentSnapshot) -> tuple[AuditRow, ...]:
    rows: list[AuditRow] = []
    if snapshot.system is not None and snapshot.system.distro:
        rows.append(
            AuditRow(
                "system",
                snapshot.system.distro,
                snapshot.system.version_id,
                f"{snapshot.system.codename} {snapshot.system.architecture}".strip(),
            )
        )
    for item in snapshot.apt_packages:
        rows.append(AuditRow("apt", item.name, item.version, item.origin))
    for item in snapshot.repositories:
        rows.append(AuditRow("repository", item.filename, "", _first_line(item.content)))
    for item in snapshot.npm_packages:
        rows.append(AuditRow("npm", item.name, item.version, "npm"))
    for item in snapshot.pip_packages:
        rows.append(AuditRow("pip", item.name, item.version, "pip"))
    for item in snapshot.cargo_packages:
        rows.append(AuditRow("cargo", item.name, item.version, "cargo"))
    for item in snapshot.flatpaks:
        rows.append(AuditRow("flatpak", item.name, item.version, item.origin))
    for item in snapshot.snaps:
        detail = item.origin + (" classic" if item.classic else "")
        rows.append(AuditRow("snap", item.name, item.version, detail.strip()))
    for item in snapshot.variables:
        rows.append(AuditRow("environment", item.name, item.value, item.source))
    for item in snapshot.extensions:
        rows.append(AuditRow("extension", item.identifier, item.version, item.editor))
    for item in snapshot.manual:
        rows.append(AuditRow("manual", item.name, "", item.reason))
    return tuple(rows)


def row_matches(category_id: str, name: str, version: str, detail: str, label: str, *, query: str, selected: str) -> bool:
    if selected != "all" and category_id != selected:
        return False
    folded = query.casefold().strip()
    if not folded:
        return True
    haystack = f"{label} {name} {version} {detail}".casefold()
    return folded in haystack


def repo_destination(filename: str) -> str | None:
    if filename == "sources.list":
        return "/etc/apt/sources.list"
    if REPO_NAME.fullmatch(filename) is None:
        return None
    return f"/etc/apt/sources.list.d/{filename}"


def is_repo_path(path: str) -> bool:
    if path == "/etc/apt/sources.list":
        return True
    parent, _slash, name = path.rpartition("/")
    return parent == "/etc/apt/sources.list.d" and REPO_NAME.fullmatch(name) is not None


def normalize_apt_name(name: str) -> str:
    if ":" not in name:
        return name
    base, arch = name.rsplit(":", 1)
    if arch and APT_NAME.fullmatch(base):
        return base
    return name


def _unique(items: tuple, key) -> tuple:
    chosen = {}
    for item in items:
        chosen[key(item)] = item
    return tuple(chosen[name] for name in sorted(chosen, key=lambda value: str(value).casefold()))


def _first_line(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:160]
    return ""
