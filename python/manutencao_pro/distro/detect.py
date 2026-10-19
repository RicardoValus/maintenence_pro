from __future__ import annotations

from pathlib import Path

from manutencao_pro.audit_os import parse_os_release
from manutencao_pro.distro.debian import DEBIAN_PROFILE
from manutencao_pro.distro.pop import POP_PROFILE
from manutencao_pro.distro.types import DistroProfile

_DEFAULT_OS_RELEASE = Path("/etc/os-release")


def profile_from_fields(fields: dict[str, str]) -> DistroProfile:
    distro_id = fields.get("ID", "").strip().casefold()
    like = {part for part in fields.get("ID_LIKE", "").casefold().split() if part}
    if distro_id == "pop" or "pop" in like:
        return POP_PROFILE
    return DEBIAN_PROFILE


def profile_from_os_release_text(text: str) -> DistroProfile:
    return profile_from_fields(parse_os_release(text))


def detect_profile(os_release: Path | None = None) -> DistroProfile:
    path = os_release or _DEFAULT_OS_RELEASE
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return DEBIAN_PROFILE
    return profile_from_os_release_text(text)
