from __future__ import annotations

from manutencao_pro.i18n import _

APP_ID = "dev.ricardo.ManutencaoPro"
SCENARIOS = ("ok", "warnings", "reboot", "fail")
MAX_HISTORY = 30

STEP_IDS = (
    "apt-update",
    "apt-upgrade",
    "apt-autoremove",
    "apt-clean",
    "apt-fix",
    "journal",
    "dkms",
    "microcode",
    "firmware",
    "nvidia",
    "nouveau",
    "glx-link",
    "glx-render",
    "conferencia",
)

APT_STEP_IDS = frozenset(
    {"apt-update", "apt-upgrade", "apt-autoremove", "apt-clean", "apt-fix"}
)

RESULT_STEPS = {
    "dkms": "dkms",
    "microcode": "microcode",
    "firmware": "firmware",
    "nvidia_repo": "nvidia",
    "nvidia_upstream": "nvidia",
    "nouveau": "nouveau",
    "glx_link": "glx-link",
    "glx_render": "glx-render",
}

RESULT_ORDER = (
    "packages",
    "dkms",
    "microcode",
    "firmware",
    "nvidia_repo",
    "nvidia_upstream",
    "nouveau",
    "glx_link",
    "glx_render",
)


def step_title(step_id: str) -> str:
    titles = {
        "apt-update": _("Atualizando lista de pacotes"),
        "apt-upgrade": _("Fazendo upgrade dos pacotes"),
        "apt-autoremove": _("Removendo pacotes desnecessários"),
        "apt-clean": _("Limpando cache de pacotes"),
        "apt-fix": _("Verificando pacotes quebrados e dependências"),
        "journal": _("Limpando logs antigos"),
        "dkms": _("Verificando módulos DKMS"),
        "microcode": _("Verificando microcode do processador"),
        "firmware": _("Verificando firmware do chipset"),
        "nvidia": _("Verificando driver NVIDIA"),
        "nouveau": _("Verificando blacklist do nouveau"),
        "glx-link": _("Verificando link do GLX"),
        "glx-render": _("Verificando renderização GLX"),
        "conferencia": _("Conferência final"),
    }
    return titles.get(step_id, step_id)


def result_title(key: str) -> str:
    titles = {
        "packages": _("Pacotes"),
        "dkms": _("DKMS NVIDIA"),
        "microcode": _("Microcode"),
        "firmware": _("Firmware chipset/BIOS"),
        "nvidia_repo": _("Driver NVIDIA no repositório"),
        "nvidia_upstream": _("Driver NVIDIA na NVIDIA.com"),
        "nouveau": _("Blacklist nouveau"),
        "glx_link": _("Link GLX"),
        "glx_render": _("GLX renderizando com NVIDIA"),
    }
    return titles.get(key, key)


def state_label(state: str) -> str:
    labels = {
        "ok": _("Atualizado"),
        "rebuilt": _("Reconstruído"),
        "fixed": _("Corrigido"),
        "upgraded": _("Atualizado nesta execução"),
        "ahead": _("À frente da página da NVIDIA"),
        "missing": _("Ausente"),
        "no_display": _("Sem sessão gráfica"),
        "fail": _("Falhou"),
        "no_pkg": _("Pacote não encontrado"),
        "no_smi": _("nvidia-smi não encontrado"),
        "loaded": _("Ainda carregado"),
        "wrong": _("Renderizador incorreto"),
        "broken": _("Com erro"),
        "newer": _("Versão mais nova fora do repositório"),
        "outdated": _("Desatualizado"),
        "available": _("Atualização disponível"),
        "skip": _("Ignorado"),
    }
    return labels.get(state, state)


def status_label(status: str) -> str:
    labels = {
        "ok": _("Tudo certo"),
        "warning": _("Concluído com avisos"),
        "reboot": _("Reinício necessário"),
        "error": _("Falhou"),
        "cancelled": _("Cancelada"),
    }
    return labels.get(status, status)
