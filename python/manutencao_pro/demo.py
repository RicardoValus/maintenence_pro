from __future__ import annotations

import os
import sys
import time

SCENARIOS = ("ok", "warnings", "reboot", "fail")

_STEPS = (
    (1, "apt-update", "Atualizando lista de pacotes"),
    (2, "apt-upgrade", "Fazendo upgrade dos pacotes"),
    (3, "apt-autoremove", "Removendo pacotes desnecessários"),
    (4, "apt-clean", "Limpando cache de pacotes"),
    (5, "apt-fix", "Verificando pacotes quebrados e dependências"),
    (6, "journal", "Limpando logs antigos"),
    (7, "dkms", "Verificando módulos DKMS"),
    (8, "microcode", "Verificando microcode do processador"),
    (9, "firmware", "Verificando firmware do chipset"),
    (10, "nvidia", "Verificando driver NVIDIA"),
    (11, "nouveau", "Verificando blacklist do nouveau"),
    (12, "glx-link", "Verificando link do GLX"),
    (13, "glx-render", "Verificando renderização GLX"),
    (14, "conferencia", "Conferência final"),
)


def lines_for(scenario: str) -> list[str]:
    if scenario not in SCENARIOS:
        raise ValueError(scenario)
    rows: list[str] = []
    for index, step_id, title in _STEPS:
        rows.append(f"@@STEP {index}/14 {step_id} {title}")
        rows.extend(_step_lines(scenario, step_id))
    return rows


def stream_main(argv: list[str]) -> int:
    scenario = argv[0] if argv else "ok"
    if scenario not in SCENARIOS:
        print("cenário inválido", file=sys.stderr)
        return 2
    delay = _delay()
    try:
        for line in lines_for(scenario):
            print(line, flush=True)
            if delay > 0:
                time.sleep(delay)
    except BrokenPipeError:
        return 0
    return 0


def _delay() -> float:
    raw = os.environ.get("MAINT_DEMO_DELAY", "0.12")
    try:
        value = float(raw)
    except ValueError:
        return 0.12
    if value < 0:
        return 0.0
    return value


def _step_lines(scenario: str, step_id: str) -> list[str]:
    if step_id == "apt-upgrade" and scenario == "fail":
        return [
            "⬆️ Fazendo upgrade dos pacotes...",
            "E: Falha simulada ao baixar pacotes",
            "@@WARN falha no apt upgrade",
        ]
    if step_id == "nvidia" and scenario == "warnings":
        return [
            "🎮 Verificando versão do driver NVIDIA...",
            "✅ Driver NVIDIA (nvidia-driver) atualizado nos repositórios configurados. Ativo: 550.163.01",
            "⚠️  NVIDIA tem versão mais nova fora do repo: 590.44. Ativo: 550.163.01",
            "@@WARN NVIDIA Unix: 590.44 disponível (ativo 550.163.01)",
        ]
    if step_id == "glx-render" and scenario == "reboot":
        return [
            "🖥️  Verificando se o GLX está renderizando com a NVIDIA...",
            "✅ GLX renderizando com a NVIDIA: OpenGL renderer string: NVIDIA GeForce",
            "@@REBOOT kernel atualizado (6.12.41 → 6.12.48)",
        ]
    if step_id == "conferencia":
        return _final_lines(scenario)
    return [f"... {step_id}"]


def _final_lines(scenario: str) -> list[str]:
    if scenario == "fail":
        return [
            "",
            "📋 Conferência final",
            "⚠️  Pacotes: houve falha no apt (update/upgrade/fix). Veja o log acima.",
            "@@RESULT packages=fail",
            "@@RESULT dkms=ok",
            "@@RESULT microcode=ok",
            "@@RESULT firmware=ok",
            "@@RESULT nvidia_repo=ok",
            "@@RESULT nvidia_upstream=ok",
            "@@RESULT nouveau=ok",
            "@@RESULT glx_link=ok",
            "@@RESULT glx_render=ok",
            "✅ Manutenção concluída!",
        ]
    if scenario == "warnings":
        return [
            "",
            "📋 Conferência final",
            "✅ Pacotes: update, upgrade e dependências ok",
            "@@RESULT packages=ok",
            "@@RESULT dkms=ok",
            "@@RESULT microcode=ok",
            "@@RESULT firmware=ok",
            "@@RESULT nvidia_repo=ok",
            "⚠️  Driver NVIDIA na NVIDIA.com",
            "@@RESULT nvidia_upstream=newer",
            "@@RESULT nouveau=ok",
            "@@RESULT glx_link=ok",
            "@@RESULT glx_render=ok",
            "✅ Não precisa reiniciar.",
            "   Avisos: NVIDIA Unix: 590.44 disponível (ativo 550.163.01)",
            "✅ Manutenção concluída!",
        ]
    if scenario == "reboot":
        return [
            "",
            "📋 Conferência final",
            "✅ Pacotes: update, upgrade e dependências ok",
            "@@RESULT packages=ok",
            "@@RESULT dkms=ok",
            "@@RESULT microcode=ok",
            "@@RESULT firmware=ok",
            "@@RESULT nvidia_repo=ok",
            "@@RESULT nvidia_upstream=ok",
            "@@RESULT nouveau=ok",
            "@@RESULT glx_link=ok",
            "@@RESULT glx_render=ok",
            "🔁 REINICIE O SISTEMA pra evitar problemas.",
            "   Motivos: kernel atualizado (6.12.41 → 6.12.48)",
            "✅ Manutenção concluída!",
        ]
    return [
        "",
        "📋 Conferência final",
        "✅ Pacotes: update, upgrade e dependências ok",
        "@@RESULT packages=ok",
        "@@RESULT dkms=ok",
        "@@RESULT microcode=ok",
        "@@RESULT firmware=ok",
        "@@RESULT nvidia_repo=ok",
        "@@RESULT nvidia_upstream=ok",
        "@@RESULT nouveau=ok",
        "@@RESULT glx_link=ok",
        "@@RESULT glx_render=ok",
        "✅ Tudo OK. Não precisa reiniciar.",
        "✅ Manutenção concluída!",
    ]
