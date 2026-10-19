from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NvidiaStrategy(str, Enum):
    FULL = "full"
    SYSTEM_MANAGED = "system_managed"


@dataclass(frozen=True)
class DistroProfile:
    key: str
    display_name: str
    expected_desktop: str
    nvidia_strategy: NvidiaStrategy
    manages_xorg_conf: bool
    manages_nouveau_blacklist: bool
    manages_glx_link: bool
    glx_mismatch_fatal_on_xwayland: bool
    about_summary: str

    def glx_mismatch_is_fatal(self, *, display: str, wayland_display: str) -> bool:
        if not self.glx_mismatch_fatal_on_xwayland and _is_xwayland(display, wayland_display):
            return False
        return True


def _is_xwayland(display: str, wayland_display: str) -> bool:
    return bool(display.strip()) and bool(wayland_display.strip())
