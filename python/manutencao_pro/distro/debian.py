from __future__ import annotations

from manutencao_pro.distro.types import DistroProfile, NvidiaStrategy

DEBIAN_PROFILE = DistroProfile(
    key="debian",
    display_name="Debian",
    expected_desktop="gnome",
    nvidia_strategy=NvidiaStrategy.FULL,
    manages_xorg_conf=True,
    manages_nouveau_blacklist=True,
    manages_glx_link=True,
    glx_mismatch_fatal_on_xwayland=True,
    about_summary=(
        "Manutenção diária do Debian: pacotes, DKMS, microcode, firmware e driver NVIDIA."
    ),
)
