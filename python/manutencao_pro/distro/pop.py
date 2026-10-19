from __future__ import annotations

from manutencao_pro.distro.types import DistroProfile, NvidiaStrategy

POP_PROFILE = DistroProfile(
    key="pop",
    display_name="Pop!_OS",
    expected_desktop="cosmic",
    nvidia_strategy=NvidiaStrategy.SYSTEM_MANAGED,
    manages_xorg_conf=False,
    manages_nouveau_blacklist=False,
    manages_glx_link=False,
    glx_mismatch_fatal_on_xwayland=False,
    about_summary=(
        "Manutenção diária do Pop!_OS: pacotes, DKMS, microcode e firmware. "
        "O driver NVIDIA é gerenciado pelo sistema (apt / COSMIC Store)."
    ),
)
