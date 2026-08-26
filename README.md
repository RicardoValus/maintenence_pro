Ordem que roda:

**1. Atualização de pacotes**
- `apt-get update` → atualiza a lista de pacotes dos repositórios (Debian, Nvidia CUDA, Tailscale, Cursor, etc).
- `apt-get dist-upgrade -y` → aplica upgrades, inclusive trocas de dependência quando necessário (diferente de um `upgrade` simples).
- `apt-get autoremove -y` → remove pacotes órfãos que ninguém mais depende.
- `apt-get autoclean`/`apt-get clean` → limpa cache de `.deb` baixados.
- `apt-get --fix-broken install` + `dpkg --configure -a` → conserta dependência quebrada ou pacote que ficou "meio instalado".

**2. Limpeza de logs**
- `journalctl --vacuum-time=30d` → apaga logs do systemd com mais de 30 dias, liberando espaço em `/var/log/journal`.

**3. Checagens específicas da tua GPU NVIDIA (RTX 4060 Ti)**
- **DKMS**: confere se o módulo do driver NVIDIA foi compilado pro kernel atual; se não foi, recompila (`dkms autoinstall`) e atualiza o initramfs.
- **Driver no repo**: compara versão instalada vs. disponível no repositório (no teu caso, o repo CUDA da NVIDIA pra debian13).
- **Driver na nvidia.com**: consulta a página oficial da NVIDIA pra ver se existe versão mais nova fora do repo (só leitura, não instala nada).
- **Blacklist do nouveau**: garante que o driver livre `nouveau` está bloqueado, senão ele entra em conflito com o driver proprietário.
- **Link GLX** (`libglxserver_nvidia.so`): confere se o symlink aponta pra versão certa da lib — quando quebra, é a causa clássica de janela transparente/Xorg bugado.
- **Renderização GLX**: roda `glxinfo` pra confirmar que o OpenGL está de fato saindo pela NVIDIA e não caindo pro Mesa/software rendering.

**4. Microcode e firmware**
- Detecta se é CPU AMD ou Intel e confere se o pacote de microcode (`amd64-microcode` no teu caso) está atualizado.
- Se tiver `fwupd` instalado, confere atualização de firmware de chipset/BIOS (só avisa, não aplica sozinho).

**5. Relatório final**
- Junta tudo isso e decide: se algo que exige reboot mudou (kernel novo, driver NVIDIA atualizado, microcode, DKMS recompilado, nouveau ainda carregado, link GLX recriado) → manda reiniciar e explica o motivo. Se não → confirma "tudo OK, não precisa reiniciar".
