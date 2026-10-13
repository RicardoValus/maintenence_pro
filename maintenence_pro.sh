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
MAINT_TOTAL_STEPS=14
gui_warn() {
    if [ "${MAINT_GUI:-}" = "1" ]; then
        printf '%s\n' "@@WARN $1"
    fi
}
gui_write_step() {
    if [ "${MAINT_GUI:-}" != "1" ] || [ -z "${MAINT_STEP_FILE:-}" ]; then
        return 0
    fi
    python3 -c 'import os,sys
try:
    fd=os.open(sys.argv[1], os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW, 0o644)
except OSError:
    raise SystemExit(0)
os.write(fd, (sys.argv[2]+"\n").encode())
os.close(fd)' "$MAINT_STEP_FILE" "$1" 2>/dev/null || true
}
gui_step() {
    if [ "${MAINT_GUI:-}" != "1" ]; then
        return 0
    fi
    printf '%s\n' "@@STEP $1/${MAINT_TOTAL_STEPS} $2 $3"
    gui_write_step "$2"
}
gui_result() {
    if [ "${MAINT_GUI:-}" = "1" ]; then
        printf '%s\n' "@@RESULT $1=$2"
    fi
}
gui_result_if_set() {
    case "$1" in
        ""|skip) return 0 ;;
    esac
    gui_result "$2" "$1"
}
append_reboot() {
    REBOOT_REASONS="${REBOOT_REASONS}${REBOOT_REASONS:+; }$1"
    if [ "${MAINT_GUI:-}" = "1" ]; then
        printf '%s\n' "@@REBOOT $1"
    fi
}
append_warn() {
    WARNINGS="${WARNINGS}${WARNINGS:+ | }$1"
    gui_warn "$1"
}
apply_uefi_dbx() {
    sudo fwupdmgr refresh --force &> /dev/null
    local json parsed ids other id
    json=$(sudo fwupdmgr get-updates --json 2>/dev/null)
    parsed=$(printf '%s' "$json" | python3 -c 'import json,sys
d=json.load(sys.stdin)
ids, other = [], 0
for x in d.get("Devices") or []:
    is_dbx = x.get("Plugin")=="uefi_dbx" or (x.get("Name") or "").lower()=="uefi dbx"
    if is_dbx and x.get("DeviceId"):
        ids.append(x["DeviceId"])
    elif not is_dbx:
        other += 1
print(" ".join(ids))
print(other)
' 2>/dev/null)
    ids=$(printf '%s\n' "$parsed" | sed -n '1p')
    other=$(printf '%s\n' "$parsed" | sed -n '2p')
    case "$other" in ''|*[!0-9]*) other=0 ;; esac
    if [ -n "$ids" ]; then
        echo "🔐 Aplicando UEFI dbx (Secure Boot)..."
        for id in $ids; do
            sudo fwupdmgr update "$id" -y --no-reboot-check
        done
        append_reboot "UEFI dbx (Secure Boot) atualizado"
    fi
    if [ "$other" -gt 0 ]; then
        FW_STATE="available"
        echo "⚠️  Firmware de hardware disponível (BIOS não é aplicada automaticamente). Rode: sudo fwupdmgr update"
        sudo fwupdmgr get-updates 2>&1
        append_warn "firmware: atualizações além do dbx (não aplicadas)"
    elif [ -n "$ids" ]; then
        FW_STATE="upgraded"
        echo "✅ UEFI dbx aplicado. Chipset/BIOS sem outras atualizações."
    else
        FW_STATE="ok"
        echo "✅ Firmware do sistema (chipset/BIOS) atualizado."
    fi
}
nvidia_lookup_os_id() {
    case "$(uname -m)" in
        aarch64|arm64) echo 124 ;;
        *) echo 12 ;;
    esac
}
parse_nvidia_lookup() {
    python3 -c '
import json
import sys

def branch_version(info):
    raw = info.get("DisplayVersion")
    if isinstance(raw, str):
        return raw.strip()
    return ""

def branch_url(info):
    raw = info.get("DownloadURL")
    if isinstance(raw, str):
        return raw.strip()
    return ""

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)
items = data.get("IDS") if isinstance(data, dict) else None
if not isinstance(items, list):
    sys.exit(1)
prod = ""
nfb = ""
prod_url = ""
nfb_url = ""
for item in items:
    info = item.get("downloadInfo") if isinstance(item, dict) else None
    if not isinstance(info, dict):
        continue
    version = branch_version(info)
    if not version:
        continue
    recommended = str(info.get("IsRecommended")) == "1"
    preview = str(info.get("IsFeaturePreview")) == "1"
    if not prod and recommended:
        prod = version
        prod_url = branch_url(info)
    elif not nfb and preview:
        nfb = version
        nfb_url = branch_url(info)
    if prod and nfb:
        break
if not prod and not nfb:
    sys.exit(1)
sys.stdout.write(prod + "\n" + nfb + "\n" + prod_url + "\n" + nfb_url + "\n")
'
}
fetch_nvidia_unix_versions() {
    NV_PROD=""
    NV_NFB=""
    NV_PROD_URL=""
    NV_NFB_URL=""
    local raw os_id parsed
    os_id=$(nvidia_lookup_os_id)
    local url="https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/AjaxDriverService.php?func=DriverManualLookup&psid=120&lid=1&isWHQL=0&numberOfResults=6&sort1=1&languageCode=1033&osID=${os_id}&pfid=985"
    if command -v curl >/dev/null 2>&1; then
        raw=$(curl -fsSL -A "Mozilla/5.0 (compatible; maintenence-pro/1.0)" --max-time 15 "$url" 2>/dev/null) || raw=""
    elif command -v wget >/dev/null 2>&1; then
        raw=$(wget -qO- --timeout=15 -U "Mozilla/5.0 (compatible; maintenence-pro/1.0)" "$url" 2>/dev/null) || raw=""
    else
        return 1
    fi
    [ -z "$raw" ] && return 1
    command -v python3 >/dev/null 2>&1 || return 1
    parsed=$(printf '%s' "$raw" | parse_nvidia_lookup) || return 1
    NV_PROD=$(printf '%s\n' "$parsed" | sed -n '1p')
    NV_NFB=$(printf '%s\n' "$parsed" | sed -n '2p')
    NV_PROD_URL=$(printf '%s\n' "$parsed" | sed -n '3p')
    NV_NFB_URL=$(printf '%s\n' "$parsed" | sed -n '4p')
    [ -n "$NV_PROD" ] || [ -n "$NV_NFB" ]
}
nvidia_url_ok() {
    local url="$1" version="$2"
    [[ "$version" =~ ^[0-9]+(\.[0-9]+){1,3}$ ]] || return 1
    [[ "$url" =~ ^https://([a-z0-9-]+\.)?download\.nvidia\.com/XFree86/Linux-[A-Za-z0-9_]+/${version}/NVIDIA-Linux-[A-Za-z0-9_.-]+-${version}\.run$ ]]
}
nvidia_run_cached() {
    local dest="$1" size
    [ -f "$dest" ] || return 1
    size=$(stat -c '%s' -- "$dest" 2>/dev/null || echo 0)
    [ "$size" -gt 100000000 ] || return 1
    head -c 9 -- "$dest" | grep -q '^#!/bin/sh'
}
nvidia_download_run() {
    local url="$1" dest="$2" partial="${2}.partial"
    echo "⬇️  Baixando driver NVIDIA..."
    if ! sudo curl -fL --retry 3 --retry-delay 2 -A "Mozilla/5.0 (compatible; maintenence-pro/1.0)" --max-time 900 -o "$partial" "$url"; then
        sudo rm -f -- "$partial"
        return 1
    fi
    sudo mv -f -- "$partial" "$dest"
    sudo chmod 755 -- "$dest"
}
nvidia_waiting_reboot() {
    local latest="$1" recorded mtime btime
    recorded=$(cat /var/lib/manutencao-pro/nvidia-upstream-installed 2>/dev/null || true)
    [ "$recorded" = "$latest" ] || return 1
    mtime=$(stat -c '%Y' -- /var/lib/manutencao-pro/nvidia-upstream-installed 2>/dev/null || echo 0)
    btime=$(awk '/^btime /{print $2}' /proc/stat)
    [ -n "$btime" ] && [ "$mtime" -gt "$btime" ]
}
install_nvidia_upstream() {
    local latest="$1" url="$2" dest
    if ! nvidia_url_ok "$url" "$latest"; then
        NV_UP_STATE="fail"
        echo "⚠️  URL do driver NVIDIA recusada."
        append_warn "NVIDIA Unix: URL inválida ($latest)"
        return 1
    fi
    if nvidia_waiting_reboot "$latest"; then
        NV_UP_STATE="upgraded"
        echo "✅ Driver NVIDIA $latest já instalado. Reinicie para ativar."
        append_reboot "driver NVIDIA $latest instalado"
        return 0
    fi
    sudo mkdir -p /var/cache/manutencao-pro /var/lib/manutencao-pro
    dest="/var/cache/manutencao-pro/NVIDIA-Linux-${latest}.run"
    if ! nvidia_run_cached "$dest" && ! nvidia_download_run "$url" "$dest"; then
        NV_UP_STATE="fail"
        echo "⚠️  Falha ao baixar o driver NVIDIA $latest."
        append_warn "NVIDIA Unix: download falhou ($latest)"
        return 1
    fi
    if ! nvidia_run_cached "$dest"; then
        sudo rm -f -- "$dest"
        NV_UP_STATE="fail"
        echo "⚠️  O arquivo baixado não é o instalador da NVIDIA."
        append_warn "NVIDIA Unix: arquivo inválido ($latest)"
        return 1
    fi
    echo "📦 Instalando driver NVIDIA $latest. A sessão continua no driver antigo até reiniciar."
    if ! sudo sh "$dest" --ui=none --no-questions --no-x-check --skip-module-load --dkms --disable-nouveau --rebuild-initramfs --no-check-for-alternate-installs; then
        NV_UP_STATE="fail"
        echo "⚠️  O instalador da NVIDIA falhou. O arquivo ficou em $dest"
        append_warn "NVIDIA Unix: instalação de $latest falhou"
        return 1
    fi
    printf '%s\n' "$latest" | sudo tee /var/lib/manutencao-pro/nvidia-upstream-installed >/dev/null
    NV_UP_STATE="upgraded"
    echo "✅ Driver NVIDIA $latest instalado. Reinicie para usar."
    append_reboot "driver NVIDIA $latest instalado"
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
        echo "   NVIDIA tem versão mais nova fora do repo: $latest. Ativo: $ativo"
        if [ "$latest" = "$NV_NFB" ]; then
            install_nvidia_upstream "$latest" "$NV_NFB_URL"
        else
            install_nvidia_upstream "$latest" "$NV_PROD_URL"
        fi
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
        gui_result "packages" "ok"
    else
        echo "⚠️  Pacotes: houve falha no apt (update/upgrade/fix). Veja o log acima."
        gui_result "packages" "fail"
    fi
    print_item "$DKMS_STATE" "DKMS NVIDIA"
    gui_result_if_set "$DKMS_STATE" "dkms"
    print_item "$MC_STATE" "Microcode${MC_INSTALLED:+ ($MC_INSTALLED)}"
    gui_result_if_set "$MC_STATE" "microcode"
    print_item "$FW_STATE" "Firmware chipset/BIOS"
    gui_result_if_set "$FW_STATE" "firmware"
    print_item "$NV_REPO_STATE" "Driver NVIDIA no repositório${DRIVER_ATIVO:+ (ativo: $DRIVER_ATIVO)}"
    gui_result_if_set "$NV_REPO_STATE" "nvidia_repo"
    print_item "$NV_UP_STATE" "Driver NVIDIA na NVIDIA.com"
    gui_result_if_set "$NV_UP_STATE" "nvidia_upstream"
    print_item "$NOUVEAU_STATE" "Blacklist nouveau"
    gui_result_if_set "$NOUVEAU_STATE" "nouveau"
    print_item "$GLX_LINK_STATE" "Link GLX"
    gui_result_if_set "$GLX_LINK_STATE" "glx_link"
    print_item "$GLX_RENDER_STATE" "GLX renderizando com NVIDIA"
    gui_result_if_set "$GLX_RENDER_STATE" "glx_render"
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

gui_step 1 apt-update "Atualizando lista de pacotes"
echo "🔄 Atualizando lista de pacotes..."
sudo apt-get update
[ $? -eq 0 ] || APT_UPDATE_OK=false
if [ "$APT_UPDATE_OK" = false ]; then
    gui_warn "falha no apt update"
fi

gui_step 2 apt-upgrade "Fazendo upgrade dos pacotes"
echo "⬆️ Fazendo upgrade dos pacotes..."
sudo apt-get dist-upgrade -y | tee "$UPGRADE_LOG"
[ "${PIPESTATUS[0]}" -eq 0 ] || APT_UPGRADE_OK=false
if [ "$APT_UPGRADE_OK" = false ]; then
    gui_warn "falha no apt upgrade"
fi

gui_step 3 apt-autoremove "Removendo pacotes desnecessários"
echo "🧹 Removendo pacotes desnecessários..."
sudo apt-get autoremove -y

gui_step 4 apt-clean "Limpando cache de pacotes"
echo "🧼 Limpando cache de pacotes..."
sudo apt-get autoclean -y
sudo apt-get clean

gui_step 5 apt-fix "Verificando pacotes quebrados e dependências"
echo "🔍 Verificando pacotes quebrados e dependências..."
sudo apt-get --fix-broken install -y
if [ $? -ne 0 ]; then
    APT_FIX_OK=false
    gui_warn "falha no apt --fix-broken"
fi
sudo dpkg --configure -a
if [ $? -ne 0 ]; then
    APT_FIX_OK=false
    gui_warn "falha no dpkg --configure"
fi

gui_step 6 journal "Limpando logs antigos"
echo "🧠 Limpando logs antigos (journald)..."
sudo journalctl --vacuum-time=30d

gui_step 7 dkms "Verificando módulos DKMS"
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

gui_step 8 microcode "Verificando microcode do processador"
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

gui_step 9 firmware "Verificando firmware do chipset"
echo "🔌 Verificando firmware de chipset/placa-mãe (fwupd)..."
if command -v fwupdmgr &> /dev/null; then
    apply_uefi_dbx
else
    FW_STATE="missing"
    echo "ℹ️  fwupd não instalado. Instale com: sudo apt install fwupd (necessário pra checar firmware de chipset/BIOS)"
    append_warn "fwupd não instalado"
fi

gui_step 10 nvidia "Verificando driver NVIDIA"
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

gui_step 11 nouveau "Verificando blacklist do nouveau"
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

gui_step 12 glx-link "Verificando link do GLX"
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

gui_step 13 glx-render "Verificando renderização GLX"
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

gui_step 14 conferencia "Conferência final"
print_final_report
echo "✅ Manutenção concluída!"
