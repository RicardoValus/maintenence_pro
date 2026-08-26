#!/bin/bash

KERNEL_ANTES=$(uname -r)

echo "🔄 Atualizando lista de pacotes..."
sudo apt update

echo "⬆️ Fazendo upgrade dos pacotes..."
sudo apt dist-upgrade -y   # mais completo que upgrade, resolve dependências novas

echo "🧹 Removendo pacotes desnecessários..."
sudo apt autoremove -y

echo "🧼 Limpando cache de pacotes..."
sudo apt autoclean -y
sudo apt clean

echo "🔍 Verificando pacotes quebrados..."
sudo apt --fix-broken install -y

echo "📦 Verificando dependências..."
sudo dpkg --configure -a

echo "🧠 Limpando logs antigos (journald)..."
sudo journalctl --vacuum-time=30d

echo "🎮 Verificando módulos DKMS (NVIDIA)..."
DKMS_STATUS=$(sudo dkms status 2>/dev/null)

if echo "$DKMS_STATUS" | grep -q "added"; then
    echo "⚠️  Módulos DKMS não compilados. Reconstruindo..."
    sudo dkms autoinstall
    sudo update-initramfs -u
fi

# Checa se um novo kernel foi instalado (ainda não está rodando)
KERNEL_NOVO=$(ls /boot/vmlinuz-* | sort -V | tail -1 | sed 's|/boot/vmlinuz-||')

if [ "$KERNEL_ANTES" != "$KERNEL_NOVO" ]; then
    echo ""
    echo "🔁 KERNEL ATUALIZADO: $KERNEL_ANTES → $KERNEL_NOVO"
    echo "   ⚠️  REINICIE O SISTEMA antes de usar a NVIDIA!"
else
    echo "✅ Kernel sem mudança ($KERNEL_ANTES). Tudo OK."
fi

echo "✅ Manutenção concluída!"
