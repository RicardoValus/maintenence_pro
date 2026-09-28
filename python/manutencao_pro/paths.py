from __future__ import annotations

from pathlib import Path

APP_ID = "dev.ricardo.ManutencaoPro"
LIBEXEC = Path("/usr/libexec/manutencao-pro")
WRAPPER = LIBEXEC / "wrapper"
SCRIPT = LIBEXEC / "maintenence_pro.sh"
SHORTCUTS_UI = Path("/usr/share/manutencao-pro/shortcuts.ui")


def project_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "data").is_dir() and (candidate / "libexec").is_dir():
        return candidate
    return None


def shortcuts_ui() -> Path | None:
    if SHORTCUTS_UI.is_file():
        return SHORTCUTS_UI
    root = project_root()
    if root is None:
        return None
    path = root / "data" / "shortcuts.ui"
    if path.is_file():
        return path
    return None


def icon_theme_dir() -> Path | None:
    root = project_root()
    if root is None:
        return None
    icons = root / "data" / "icons"
    if icons.is_dir():
        return icons
    return None
