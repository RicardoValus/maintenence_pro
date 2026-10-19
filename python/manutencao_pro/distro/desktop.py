from __future__ import annotations

import os
from collections.abc import Mapping


def desktop_environment(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    raw = env.get("XDG_CURRENT_DESKTOP", "")
    parts = []
    for chunk in raw.replace(":", ";").split(";"):
        name = chunk.strip().casefold()
        if name:
            parts.append(name)
    if "cosmic" in parts:
        return "cosmic"
    if "gnome" in parts:
        return "gnome"
    if len(parts) == 1:
        return parts[0]
    if parts:
        return parts[0]
    session = env.get("XDG_SESSION_DESKTOP", "").strip().casefold()
    if session:
        return session
    return "unknown"


def supports_gnome_keybind_schemas(environ: Mapping[str, str] | None = None) -> bool:
    return desktop_environment(environ) == "gnome"
