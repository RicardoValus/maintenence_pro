from __future__ import annotations

import re

from manutencao_pro.audit_model import (
    MAX_ENV_LINE,
    SOURCE_SESSION,
    USER_SHELL_FILES,
    AptPackage,
    EnvVariable,
    Extension,
    ManualItem,
    RemotePackage,
    ToolPackage,
)
from manutencao_pro.i18n import _

_SECRET_NAME = re.compile(
    r"(?:^|_)(?:TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API_KEY|PRIVATE_KEY|AUTH)(?:_|$)|(?:^|_)KEY$",
    re.IGNORECASE,
)
_ASSIGNMENT = re.compile(
    r"""^(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>\S*))\s*$"""
)
_PAM = re.compile(
    r"""^(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\s+DEFAULT)?=(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>\S*))\s*$"""
)
_SHELL_LINE = re.compile(
    r"""^export [A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S+)$"""
)
_PAM_LINE = re.compile(
    r"""^[A-Za-z_][A-Za-z0-9_]*(?:\s+DEFAULT)?=(?:"[^"]*"|'[^']*'|\S+)$"""
)
_EXT_DIR = re.compile(r"^(?P<ident>[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z0-9][A-Za-z0-9.-]*)-(?P<version>\d.*)$")
_LOCAL_REPO = re.compile(r"(?mi)^(?:deb(?:-src)?\s+(?:\[[^\]]*\]\s+)?|URIs:\s*)(?:file:|cdrom:)")


def is_secret_name(name: str) -> bool:
    return _SECRET_NAME.search(name) is not None


def is_local_repository(content: str) -> bool:
    return _LOCAL_REPO.search(content) is not None


def safe_env_line(line: str, source: str) -> bool:
    if "\n" in line or "\x00" in line or "$(" in line or "`" in line or len(line) > MAX_ENV_LINE:
        return False
    if source == ".pam_environment":
        return _PAM_LINE.fullmatch(line) is not None
    if source in USER_SHELL_FILES:
        return _SHELL_LINE.fullmatch(line) is not None
    return False


def assigned_name(line: str) -> str | None:
    match = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)(?:\s+DEFAULT)?=", line)
    if match is None:
        return None
    return match.group(1)


def assignment_exists(text: str, name: str) -> bool:
    pattern = re.compile(rf"(?m)^\s*(?:export\s+)?{re.escape(name)}(?:\s+DEFAULT)?=")
    return pattern.search(text) is not None


def canonical_assignment(name: str, value: str, *, export: bool) -> str:
    body = f'{name}="{value}"'
    if export:
        return f"export {body}"
    return body


def stored_variable(name: str, value: str, source: str, line: str) -> EnvVariable | ManualItem:
    if is_secret_name(name):
        return ManualItem("environment", name or "?", _("variável sensível; o valor não entra no backup"))
    if source == SOURCE_SESSION:
        if not name or "\n" in value:
            return ManualItem("environment", name or "?", _("entrada inválida"))
        return EnvVariable(name, value, SOURCE_SESSION, "")
    if source not in USER_SHELL_FILES:
        return ManualItem("environment", name or "?", _("arquivo de shell desconhecido"))
    chosen = line or _canonical_for(name, value, source)
    if not safe_env_line(chosen, source) or assigned_name(chosen) != name:
        return ManualItem("environment", name or "?", _("linha de ambiente inválida"))
    parsed = _value_of(chosen, source)
    if parsed is None:
        return ManualItem("environment", name, _("linha de ambiente inválida"))
    return EnvVariable(name, parsed, source, chosen)


def parse_apt_policy(text: str) -> tuple[AptPackage, ...]:
    packages: list[AptPackage] = []
    name: str | None = None
    installed = ""
    origin = ""
    in_installed = False

    def flush() -> None:
        nonlocal name, installed, origin, in_installed
        if name and installed and installed != "(none)":
            packages.append(AptPackage(name, installed, origin or "local"))
        name = None
        installed = ""
        origin = ""
        in_installed = False

    for raw in text.splitlines():
        if raw and not raw.startswith((" ", "\t")) and raw.endswith(":"):
            flush()
            name = raw[:-1].strip()
            continue
        if name is None:
            continue
        stripped = raw.strip()
        if stripped.startswith("Installed:"):
            installed = stripped.split(":", 1)[1].strip()
            in_installed = False
            continue
        if stripped.startswith("***"):
            in_installed = True
            origin = ""
            continue
        if in_installed and not origin and stripped[:1].isdigit():
            origin = _policy_origin(stripped)
            in_installed = False
    flush()
    return tuple(packages)


def parse_dpkg_query(text: str) -> tuple[AptPackage, ...]:
    packages: list[AptPackage] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, version, status = parts
        if not _installed_status(status) or not name or not version:
            continue
        packages.append(AptPackage(name, version, "desconhecida"))
    return tuple(packages)


def _installed_status(status: str) -> bool:
    text = status.strip()
    return text == "installed" or text.endswith(" installed")


def parse_npm_list(text: str) -> tuple[ToolPackage, ...]:
    import json

    payload = _json_value(text)
    if not isinstance(payload, dict):
        raise ValueError("npm")
    dependencies = payload.get("dependencies", {})
    if not isinstance(dependencies, dict):
        raise ValueError("npm")
    packages: list[ToolPackage] = []
    for name, info in dependencies.items():
        if not isinstance(name, str) or not isinstance(info, dict):
            continue
        version = info.get("version", "")
        if isinstance(version, str) and version:
            packages.append(ToolPackage(name, version))
    return tuple(packages)


def parse_pip_list(text: str) -> tuple[ToolPackage, ...]:
    payload = _json_value(text)
    if not isinstance(payload, list):
        raise ValueError("pip")
    packages: list[ToolPackage] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        version = item.get("version", "")
        if isinstance(name, str) and isinstance(version, str) and name and version:
            packages.append(ToolPackage(name, version))
    return tuple(packages)


def parse_cargo_list(text: str) -> tuple[ToolPackage, ...]:
    packages: list[ToolPackage] = []
    for line in text.splitlines():
        match = re.fullmatch(r"([A-Za-z0-9_-]+) v([A-Za-z0-9.+_-]+):", line.strip())
        if match is None:
            continue
        packages.append(ToolPackage(match.group(1), match.group(2)))
    return tuple(packages)


def parse_flatpak_list(text: str) -> tuple[RemotePackage, ...]:
    packages: list[RemotePackage] = []
    for line in text.splitlines():
        parts = [item.strip() for item in line.split("\t")]
        if len(parts) < 2 or not parts[0] or parts[0] == "Application":
            continue
        origin = parts[2] if len(parts) > 2 else ""
        packages.append(RemotePackage(parts[0], parts[1], origin))
    return tuple(packages)


def parse_snap_list(text: str) -> tuple[RemotePackage, ...]:
    packages: list[RemotePackage] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] == "Name":
            continue
        classic = "classic" in parts[-1]
        packages.append(RemotePackage(parts[0], parts[1], "", classic))
    return tuple(packages)


def parse_extension_listing(editor: str, text: str) -> tuple[Extension, ...]:
    items: list[Extension] = []
    for line in text.splitlines():
        stripped = line.strip()
        if "@" not in stripped:
            continue
        identifier, version = stripped.rsplit("@", 1)
        if identifier and version:
            items.append(Extension(editor, identifier, version))
    return tuple(items)


def parse_extension_dirname(editor: str, dirname: str) -> Extension | None:
    match = _EXT_DIR.fullmatch(dirname)
    if match is None:
        return None
    return Extension(editor, match.group("ident"), match.group("version"))


def parse_shell_file(source: str, text: str) -> tuple[tuple[EnvVariable, ...], tuple[ManualItem, ...]]:
    variables: list[EnvVariable] = []
    manual: list[ManualItem] = []
    pattern = _PAM if source == ".pam_environment" else _ASSIGNMENT
    for raw in text.splitlines():
        stripped = _strip_comment(raw).strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = pattern.fullmatch(stripped)
        if match is None:
            continue
        _keep_assignment(source, stripped, match, variables, manual)
    return tuple(variables), tuple(manual)


def _keep_assignment(source: str, line: str, match: re.Match[str], variables: list[EnvVariable], manual: list[ManualItem]) -> None:
    name = match.group("name")
    if is_secret_name(name):
        manual.append(ManualItem("environment", name, _("variável sensível; o valor não entra no backup")))
        return
    if "$(" in line or "`" in line:
        manual.append(ManualItem("environment", name, _("a atribuição executa um comando")))
        return
    if len(line) > MAX_ENV_LINE:
        manual.append(ManualItem("environment", name, _("linha longa demais")))
        return
    value = _groups_value(match)
    raw = line if safe_env_line(line, source) else _canonical_for(name, value, source)
    if not safe_env_line(raw, source):
        manual.append(ManualItem("environment", name, _("linha de ambiente inválida")))
        return
    variables.append(EnvVariable(name, value, source, raw))


def _groups_value(match: re.Match[str]) -> str:
    for group in ("double", "single", "bare"):
        if match.start(group) >= 0:
            return match.group(group) or ""
    return ""


def _canonical_for(name: str, value: str, source: str) -> str:
    if '"' in value or "\\" in value or "\n" in value:
        return ""
    return canonical_assignment(name, value, export=source != ".pam_environment")


def _value_of(line: str, source: str) -> str | None:
    pattern = _PAM if source == ".pam_environment" else _ASSIGNMENT
    match = pattern.fullmatch(line)
    if match is None:
        return None
    return _groups_value(match)


def _policy_origin(line: str) -> str:
    parts = line.split()
    if len(parts) < 2 or parts[1].startswith("/"):
        return "local"
    host = parts[1].split("//", 1)[-1].split("/", 1)[0]
    suite = parts[2] if len(parts) > 2 else ""
    if suite:
        return f"{host} {suite}"
    return host


def _json_value(text: str) -> object:
    import json

    start_object = text.find("{")
    start_array = text.find("[")
    starts = [index for index in (start_object, start_array) if index >= 0]
    if not starts:
        raise ValueError("json")
    payload, _end = json.JSONDecoder().raw_decode(text[min(starts) :])
    return payload


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
    return line
