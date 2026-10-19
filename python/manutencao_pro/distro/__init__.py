from __future__ import annotations

from manutencao_pro.distro.debian import DEBIAN_PROFILE
from manutencao_pro.distro.desktop import desktop_environment, supports_gnome_keybind_schemas
from manutencao_pro.distro.detect import detect_profile, profile_from_fields, profile_from_os_release_text
from manutencao_pro.distro.pop import POP_PROFILE
from manutencao_pro.distro.shell import shell_exports, shell_exports_from_environ
from manutencao_pro.distro.types import DistroProfile, NvidiaStrategy

__all__ = [
    "DEBIAN_PROFILE",
    "POP_PROFILE",
    "DistroProfile",
    "NvidiaStrategy",
    "desktop_environment",
    "detect_profile",
    "profile_from_fields",
    "profile_from_os_release_text",
    "shell_exports",
    "shell_exports_from_environ",
    "supports_gnome_keybind_schemas",
]
