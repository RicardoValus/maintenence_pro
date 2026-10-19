from __future__ import annotations

import os
import shlex
from pathlib import Path

from manutencao_pro.distro.detect import detect_profile
from manutencao_pro.distro.types import DistroProfile


def shell_exports(profile: DistroProfile | None = None, os_release: Path | None = None) -> str:
    resolved = profile if profile is not None else detect_profile(os_release)
    pairs = (
        ("MAINT_PROFILE_KEY", resolved.key),
        ("MAINT_PROFILE_NAME", resolved.display_name),
        ("MAINT_EXPECTED_DESKTOP", resolved.expected_desktop),
        ("MAINT_NVIDIA_STRATEGY", resolved.nvidia_strategy.value),
        ("MAINT_MANAGES_XORG_CONF", _flag(resolved.manages_xorg_conf)),
        ("MAINT_MANAGES_NOUVEAU", _flag(resolved.manages_nouveau_blacklist)),
        ("MAINT_MANAGES_GLX_LINK", _flag(resolved.manages_glx_link)),
        ("MAINT_GLX_FATAL_ON_XWAYLAND", _flag(resolved.glx_mismatch_fatal_on_xwayland)),
    )
    lines = [f"export {key}={shlex.quote(value)}" for key, value in pairs]
    return "\n".join(lines) + "\n"


def shell_exports_from_environ() -> str:
    override = os.environ.get("MAINT_OS_RELEASE", "").strip()
    path = Path(override) if override else None
    return shell_exports(os_release=path)


def _flag(value: bool) -> str:
    return "1" if value else "0"
