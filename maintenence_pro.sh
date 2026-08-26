#!/bin/bash

KERNEL_ANTES=$(uname -r)
UPGRADE_LOG="/tmp/maintenence-dist-upgrade.log"
APT_UPDATE_OK=true
APT_UPGRADE_OK=true
APT_FIX_OK=true
DKMS_STATE="ok"
MC_STATE="skip"
FW_STATE="skip"
NV_REPO_STATE="skip"
NV_UP_STATE="skip"
NOUVEAU_STATE="skip"
GLX_LINK_STATE="skip"
GLX_RENDER_STATE="skip"
REBOOT_REASONS=""
WARNINGS=""
append_reboot() {
    REBOOT_REASONS="${REBOOT_REASONS}${REBOOT_REASONS:+; }$1"
}
append_warn() {
    WARNINGS="${WARNINGS}${WARNINGS:+ | }$1"
}
fetch_nvidia_unix_versions() {
    NV_PROD=""
    NV_NFB=""
    local raw section arch_key="Linux x86"
    case "$(uname -m)" in
        aarch64|arm64) arch_key="Linux aarch64" ;;
    esac
    if command -v curl >/dev/null 2>&1; then
        raw=$(curl -fsSL -A "Mozilla/5.0 (compatible; maintenence-pro/1.0)" --max-time 15 "https://www.nvidia.com/en-us/drivers/unix.md" 2>/dev/null) || raw=""
    elif command -v wget >/dev/null 2>&1; then
        raw=$(wget -qO- --timeout=15 -U "Mozilla/5.0 (compatible; maintenence-pro/1.0)" "https://www.nvidia.com/en-us/drivers/unix.md" 2>/dev/null) || raw=""
    else
        return 1
    fi
    [ -z "$raw" ] && return 1
    section=$(printf '%s\n' "$raw" | awk -v k="$arch_key" '
        index($0, "**" k) {p=1; next}
        p && /^\*\*/ {exit}
        p {print}
    ')
    NV_PROD=$(printf '%s\n' "$section" | sed -n 's/.*Production Branch Version:[[:space:]]*\[\([0-9][0-9.]*\)\].*/\1/p' | head -1)
    NV_NFB=$(printf '%s\n' "$section" | sed -n 's/.*New Feature Branch Version:[[:space:]]*\[\([0-9][0-9.]*\)\].*/\1/p' | head -1)
    [ -n "$NV_PROD" ] || [ -n "$NV_NFB" ]
}
nvidia_ver_gt() {
    [ -n "$1" ] && [ -n "$2" ] && [ "$1" != "$2" ] &&
        [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]
}
report_nvidia_upstream() {
    local ativo="$1" latest
    if ! fetch_nvidia_unix_versions; then
        NV_UP_STATE="fail"
        echo "ℹ️  Não foi possível consultar a versão mais nova da NVIDIA (fora do repo)."
        echo "   Fonte: https://www.nvidia.com/en-us/drivers/unix/"
        append_warn "NVIDIA Unix: consulta falhou"
        return
    fi
    latest=$(printf '%s\n%s\n' "$NV_PROD" "$NV_NFB" | grep -v '^$' | sort -V | tail -1)
    echo "   NVIDIA Unix: New Feature Branch ${NV_NFB:-?} | Production Branch ${NV_PROD:-?}"
    if [ "$ativo" = "$latest" ]; then
        NV_UP_STATE="ok"
        echo "✅ Driver ativo ($ativo) já é o mais novo da NVIDIA."
    elif nvidia_ver_gt "$latest" "$ativo"; then
        NV_UP_STATE="newer"
        echo "⚠️  NVIDIA tem versão mais nova fora do repo: $latest. Ativo: $ativo"
        echo "   Fonte: https://www.nvidia.com/en-us/drivers/unix/"
        append_warn "NVIDIA Unix: $latest disponível (ativo $ativo)"
    else
        NV_UP_STATE="ahead"
        echo "ℹ️  Driver ativo ($ativo) está à frente da página Unix da NVIDIA ($latest)."
    fi
}
print_item() {
    case "$1" in
        skip|"") return ;;
        ok|rebuilt|fixed|upgraded|ahead) echo "✅ $2" ;;
        missing|no_display|fail|no_pkg) echo "ℹ️  $2" ;;
        loaded|wrong|broken) echo "🚨 $2" ;;
        *) echo "⚠️  $2" ;;
    esac
}
print_final_report() {
    echo ""
    echo "📋 Conferência final"
    if [ "$APT_UPDATE_OK" = true ] && [ "$APT_UPGRADE_OK" = true ] && [ "$APT_FIX_OK" = true ]; then
        echo "✅ Pacotes: update, upgrade e dependências ok"
    else
        echo "⚠️  Pacotes: houve falha no apt (update/upgrade/fix). Veja o log acima."
    fi
    print_item "$DKMS_STATE" "DKMS NVIDIA"
    print_item "$MC_STATE" "Microcode${MC_INSTALLED:+ ($MC_INSTALLED)}"
    print_item "$FW_STATE" "Firmware chipset/BIOS"
    print_item "$NV_REPO_STATE" "Driver NVIDIA no repositório${DRIVER_ATIVO:+ (ativo: $DRIVER_ATIVO)}"
    print_item "$NV_UP_STATE" "Driver NVIDIA na NVIDIA.com"
    print_item "$NOUVEAU_STATE" "Blacklist nouveau"
    print_item "$GLX_LINK_STATE" "Link GLX"
    print_item "$GLX_RENDER_STATE" "GLX renderizando com NVIDIA"
    echo ""
    if [ -n "$REBOOT_REASONS" ]; then
        echo "🔁 REINICIE O SISTEMA pra evitar problemas."
        echo "   Motivos: $REBOOT_REASONS"
        echo "   Depois de reiniciar, rode este script de novo pra confirmar o OK."
    elif [ -n "$WARNINGS" ]; then
        echo "✅ Não precisa reiniciar."
        echo "   Avisos: $WARNINGS"
    else
        echo "✅ Tudo OK. Não precisa reiniciar."
    fi
}

echo "🔄 Atualizando lista de pacotes..."
sudo apt update
[ $? -eq 0 ] || APT_UPDATE_OK=false

echo "⬆️ Fazendo upgrade dos pacotes..."
sudo apt dist-upgrade -y | tee "$UPGRADE_LOG"
[ "${PIPESTATUS[0]}" -eq 0 ] || APT_UPGRADE_OK=false

echo "🧹 Removendo pacotes desnecessários..."
sudo apt autoremove -y

echo "🧼 Limpando cache de pacotes..."
sudo apt autoclean -y
sudo apt clean

echo "🔍 Verificando pacotes quebrados e dependências..."
sudo apt --fix-broken install -y
[ $? -eq 0 ] || APT_FIX_OK=false
sudo dpkg --configure -a
[ $? -eq 0 ] || APT_FIX_OK=false

echo "🧠 Limpando logs antigos (journald)..."
sudo journalctl --vacuum-time=30d

echo "🎮 Verificando módulos DKMS (NVIDIA)..."
DKMS_STATUS=$(sudo dkms status 2>/dev/null)
if echo "$DKMS_STATUS" | grep -qiE "error|broken"; then
    DKMS_STATE="broken"
    echo "⚠️  Módulos DKMS com erro. Tente: sudo dkms autoinstall"
    append_warn "DKMS com erro"
elif echo "$DKMS_STATUS" | grep -q "added"; then
    echo "⚠️  Módulos DKMS não compilados. Reconstruindo..."
    sudo dkms autoinstall
    sudo update-initramfs -u
    DKMS_STATE="rebuilt"
    append_reboot "módulos DKMS reconstruídos"
elif [ -n "$DKMS_STATUS" ]; then
    echo "✅ Módulos DKMS ok."
else
    DKMS_STATE="skip"
fi

echo "🧮 Verificando microcode do processador..."
MICROCODE_PKG=""
grep -qi "GenuineIntel" /proc/cpuinfo && MICROCODE_PKG="intel-microcode"
grep -qi "AuthenticAMD" /proc/cpuinfo && MICROCODE_PKG="amd64-microcode"

if [ -n "$MICROCODE_PKG" ]; then
    MC_INSTALLED=$(dpkg-query -W -f='${Version}' "$MICROCODE_PKG" 2>/dev/null)
    MC_CANDIDATE=$(apt-cache policy "$MICROCODE_PKG" 2>/dev/null | awk '/Candidate:/{print $2}')
    if [ -z "$MC_INSTALLED" ]; then
        MC_STATE="missing"
        echo "ℹ️  Pacote $MICROCODE_PKG não instalado. Instale com: sudo apt install $MICROCODE_PKG"
        append_warn "microcode $MICROCODE_PKG não instalado"
    elif grep -qiE "^(Inst|Conf) $MICROCODE_PKG" "$UPGRADE_LOG" 2>/dev/null; then
        MC_STATE="upgraded"
        echo "✅ $MICROCODE_PKG atualizado nesta execução ($MC_INSTALLED)"
        append_reboot "microcode atualizado ($MICROCODE_PKG)"
    elif [ "$MC_INSTALLED" = "$MC_CANDIDATE" ]; then
        MC_STATE="ok"
        echo "✅ $MICROCODE_PKG atualizado ($MC_INSTALLED)"
    else
        MC_STATE="outdated"
        echo "⚠️  $MICROCODE_PKG desatualizado: instalado $MC_INSTALLED, disponível $MC_CANDIDATE"
        append_warn "microcode desatualizado"
    fi
fi

echo "🔌 Verificando firmware de chipset/placa-mãe (fwupd)..."
if command -v fwupdmgr &> /dev/null; then
    sudo fwupdmgr refresh --force &> /dev/null
    FWUPD_OUT=$(sudo fwupdmgr get-updates 2>&1)
    if echo "$FWUPD_OUT" | grep -qi "no updatable devices\|no updates available"; then
        FW_STATE="ok"
        echo "✅ Firmware do sistema (chipset/BIOS) atualizado."
    else
        FW_STATE="available"
        echo "⚠️  Atualizações de firmware disponíveis. Rode: sudo fwupdmgr update"
        echo "$FWUPD_OUT"
        append_warn "firmware: atualizações disponíveis (não aplicadas)"
    fi
else
    FW_STATE="missing"
    echo "ℹ️  fwupd não instalado. Instale com: sudo apt install fwupd (necessário pra checar firmware de chipset/BIOS)"
    append_warn "fwupd não instalado"
fi

echo "🎮 Verificando versão do driver NVIDIA..."
if command -v nvidia-smi &> /dev/null; then
    DRIVER_ATIVO=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader)
    NVIDIA_PKG=$(dpkg -l | awk '/^ii\s+(nvidia-driver|nvidia-open)\s/{print $2; exit}')
    if [ -n "$NVIDIA_PKG" ]; then
        NV_INSTALLED=$(apt-cache policy "$NVIDIA_PKG" 2>/dev/null | awk '/Installed:/{print $2}')
        NV_CANDIDATE=$(apt-cache policy "$NVIDIA_PKG" 2>/dev/null | awk '/Candidate:/{print $2}')
        if [ "$NV_INSTALLED" = "$NV_CANDIDATE" ]; then
            NV_REPO_STATE="ok"
            echo "✅ Driver NVIDIA ($NVIDIA_PKG) atualizado nos repositórios configurados. Ativo: $DRIVER_ATIVO"
        else
            NV_REPO_STATE="outdated"
            echo "⚠️  Nova versão de $NVIDIA_PKG disponível: $NV_INSTALLED → $NV_CANDIDATE (ativo agora: $DRIVER_ATIVO)"
            append_warn "NVIDIA repo: $NV_INSTALLED → $NV_CANDIDATE"
        fi
    else
        NV_REPO_STATE="no_pkg"
        echo "ℹ️  Pacote nvidia-driver/nvidia-open não encontrado via dpkg. Driver ativo: $DRIVER_ATIVO"
        append_warn "pacote nvidia-driver/nvidia-open não encontrado"
    fi
    report_nvidia_upstream "$DRIVER_ATIVO"
else
    NV_REPO_STATE="no_smi"
    echo "⚠️  nvidia-smi não encontrado — driver NVIDIA pode não estar instalado."
    append_warn "nvidia-smi não encontrado"
fi

if grep -qiE "^(Inst|Conf) (nvidia-driver|nvidia-open|nvidia-kernel)" "$UPGRADE_LOG" 2>/dev/null; then
    append_reboot "driver NVIDIA atualizado"
fi

echo "🚫 Verificando blacklist do driver nouveau..."
if command -v nvidia-smi &> /dev/null; then
    BLACKLIST_FILE="/etc/modprobe.d/blacklist-nouveau.conf"
    if [ ! -f "$BLACKLIST_FILE" ] || ! grep -q "^blacklist nouveau" "$BLACKLIST_FILE" 2>/dev/null; then
        echo "⚠️  Blacklist do nouveau ausente/incompleta. Criando $BLACKLIST_FILE..."
        printf 'blacklist nouveau\noptions nouveau modeset=0\n' | sudo tee "$BLACKLIST_FILE" > /dev/null
        sudo update-initramfs -u
        echo "✅ Blacklist criada e initramfs regenerado."
        NOUVEAU_STATE="fixed"
        append_reboot "blacklist nouveau/initramfs atualizados"
    else
        NOUVEAU_STATE="ok"
        echo "✅ Blacklist do nouveau ok."
    fi
    if lsmod | grep -q "^nouveau"; then
        echo "🚨 nouveau está carregado AGORA mesmo com blacklist — só aplica depois de reiniciar."
        NOUVEAU_STATE="loaded"
        append_reboot "nouveau ainda carregado"
    fi
fi

echo "🔗 Verificando link simbólico do GLX da NVIDIA (libglxserver_nvidia.so)..."
if command -v nvidia-smi &> /dev/null; then
    GLX_VERSIONED=$(find /usr/lib -iname "libglxserver_nvidia.so.*" 2>/dev/null | sort -V | tail -1)
    if [ -z "$GLX_VERSIONED" ]; then
        GLX_LINK_STATE="missing"
        echo "⚠️  Nenhum libglxserver_nvidia.so.* encontrado no sistema — pacote NVIDIA pode estar incompleto."
        [ -n "$NVIDIA_PKG" ] && echo "   Tente: sudo apt install --reinstall $NVIDIA_PKG"
        append_warn "GLX: biblioteca versionada ausente"
    else
        GLX_DIR=$(dirname "$GLX_VERSIONED")
        GLX_LINK="$GLX_DIR/libglxserver_nvidia.so"
        if [ ! -e "$GLX_LINK" ] || [ "$(readlink -f "$GLX_LINK" 2>/dev/null)" != "$(readlink -f "$GLX_VERSIONED")" ]; then
            echo "⚠️  Link $GLX_LINK ausente ou apontando pra versão errada. Recriando -> $GLX_VERSIONED..."
            sudo ln -sf "$GLX_VERSIONED" "$GLX_LINK"
            echo "✅ Link do GLX corrigido: $GLX_LINK -> $GLX_VERSIONED"
            GLX_LINK_STATE="fixed"
            append_reboot "link GLX recriado"
        else
            GLX_LINK_STATE="ok"
            echo "✅ Link do GLX ok -> $GLX_VERSIONED"
        fi
    fi
fi

echo "🖥️  Verificando se o GLX está renderizando com a NVIDIA (e não caindo pro Mesa/swrast)..."
if command -v glxinfo &> /dev/null && [ -n "$DISPLAY" ]; then
    GL_RENDERER=$(glxinfo 2>/dev/null | grep "OpenGL renderer")
    if echo "$GL_RENDERER" | grep -qi "nvidia"; then
        GLX_RENDER_STATE="ok"
        echo "✅ GLX renderizando com a NVIDIA: $GL_RENDERER"
    else
        GLX_RENDER_STATE="wrong"
        echo "🚨 GLX NÃO está usando a NVIDIA (renderizador atual: $GL_RENDERER)."
        echo "   Sintoma das janelas transparentes. Confira o link GLX e: sudo grep -iE \"EE|WW\" /var/log/Xorg.0.log | tail -30"
        append_reboot "GLX não está na NVIDIA"
    fi
elif command -v nvidia-smi &> /dev/null; then
    GLX_RENDER_STATE="no_display"
    echo "ℹ️  Sem sessão gráfica (ou glxinfo ausente — sudo apt install mesa-utils). Depois de logar: glxinfo | grep \"OpenGL renderer\""
fi

KERNEL_NOVO=$(ls /boot/vmlinuz-* | sort -V | tail -1 | sed 's|/boot/vmlinuz-||')
if [ "$KERNEL_ANTES" != "$KERNEL_NOVO" ]; then
    append_reboot "kernel atualizado ($KERNEL_ANTES → $KERNEL_NOVO)"
fi

print_final_report
echo "✅ Manutenção concluída!"
