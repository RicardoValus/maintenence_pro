from __future__ import annotations

import gettext
import os

_DOMAIN = "manutencao-pro"


def install() -> None:
    localedir = os.environ.get("MANUTENCAO_PRO_LOCALEDIR", "/usr/share/locale")
    gettext.bindtextdomain(_DOMAIN, localedir)
    gettext.textdomain(_DOMAIN)


def _(message: str) -> str:
    return gettext.gettext(message)
