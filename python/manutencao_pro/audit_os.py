from __future__ import annotations

import re
from pathlib import Path

from manutencao_pro.audit_model import SystemOrigin
from manutencao_pro.i18n import _

_CODENAME = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
_ARCH = re.compile(r"^[a-z0-9]+$")
_PPA_HOST = ("ppa.launchpad.net", "ppa.launchpadcontent.net")


def parse_os_release(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = _unquote(value.strip())
    return fields


def system_from_release(text: str, architecture: str) -> SystemOrigin | None:
    fields = parse_os_release(text)
    distro = fields.get("ID", "").strip()
    if not distro:
        return None
    arch = architecture.strip()
    if arch and _ARCH.fullmatch(arch) is None:
        arch = ""
    return SystemOrigin(
        distro,
        fields.get("VERSION_ID", ""),
        fields.get("VERSION_CODENAME", ""),
        arch,
    )


def read_system_origin(os_release: Path, architecture: str) -> SystemOrigin | None:
    try:
        text = os_release.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return system_from_release(text, architecture)


def format_system(origin: SystemOrigin) -> str:
    parts = [origin.distro]
    if origin.version_id:
        parts.append(origin.version_id)
    if origin.codename:
        parts.append(f"({origin.codename})")
    if origin.architecture:
        parts.append(origin.architecture)
    return " ".join(parts)


def os_mismatch_warning(source: SystemOrigin | None, target: SystemOrigin | None) -> str:
    if source is None or target is None or not source.distro or not target.distro:
        return ""
    if _compatible(source, target):
        return ""
    return _(
        "A distro ou a versão deste sistema difere do backup ({source} → {target}). "
        "Nomes de pacote, PPAs e repositórios podem não corresponder."
    ).format(source=format_system(source), target=format_system(target))


def is_ubuntu_ppa(content: str) -> bool:
    lowered = content.casefold()
    return any(host in lowered for host in _PPA_HOST)


def rewrite_codename(content: str, source: str, target: str) -> str:
    origin = source.casefold()
    destination = target.casefold()
    if origin == destination or _CODENAME.fullmatch(origin) is None or _CODENAME.fullmatch(destination) is None:
        return content
    pattern = re.compile(rf"\b{re.escape(origin)}(?=-|\b)", re.IGNORECASE)
    return pattern.sub(destination, content)


def _compatible(source: SystemOrigin, target: SystemOrigin) -> bool:
    if source.distro.casefold() != target.distro.casefold():
        return False
    if source.codename and target.codename:
        if source.codename.casefold() != target.codename.casefold():
            return False
    elif source.version_id != target.version_id:
        return False
    if source.architecture and target.architecture and source.architecture != target.architecture:
        return False
    return True


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
