# Manutenção Pro

Interface gráfica para a manutenção diária do Debian 13 (GNOME 48): pacotes, DKMS, microcode, firmware e driver NVIDIA. O script `maintenence_pro.sh` continua sendo a fonte de verdade e ainda roda sozinho no terminal.

O código fica em [github.com/RicardoValus/maintenence_pro](https://github.com/RicardoValus/maintenence_pro), sob a licença MIT. O autor é Ricardo Medlo Valus.

## Instalar

Na pasta do projeto, depois de gerar o pacote:

```bash
sudo apt install ./manutencao-pro_1.0.2_all.deb
```

O aplicativo aparece na busca das Atividades como **Manutenção Pro** e pode ser fixado no dock. A ação **Executar agora** abre a janela e inicia a manutenção.

## Usar

Abra **Manutenção Pro** e clique em **Iniciar manutenção**. O GNOME pede a senha de administrador uma vez (polkit, `auth_admin_keep`). A janela não pede senha e não chama `sudo`.

Durante o apt/dpkg o botão **Cancelar** fica desligado. Nas outras etapas, cancelar envia SIGTERM ao grupo de processos da manutenção. Não há SIGKILL.

O histórico fica em `$XDG_STATE_HOME/manutencao-pro/history.json` (ou `~/.local/state/manutencao-pro/`), com as últimas 30 execuções.

Atalhos da janela: Ctrl+Enter inicia, Ctrl+L mostra ou oculta o log, Ctrl+Q sai.

## Atalho global

É configuração do seu usuário. Não entra na instalação do pacote.

```bash
manutencao-pro-instalar-atalho
manutencao-pro-remover-atalho
```

O atalho sugerido é Ctrl+Alt+M e executa `manutencao-pro --run`. Se essa combinação já existir, outra livre é escolhida. Atalhos já configurados não são sobrescritos.

## Modo demonstração

Não altera o sistema. Os quatro cenários são `ok`, `warnings`, `reboot` e `fail`.

```bash
PYTHONPATH=python python3 -m manutencao_pro --demo
PYTHONPATH=python python3 -m manutencao_pro --demo --scenario=reboot --run
```

Depois de instalar, o `PYTHONPATH` não é necessário:

```bash
python3 -m manutencao_pro --demo --scenario=fail --run
```

## Testar de verdade nesta máquina

1. Instale o `.deb`.
2. Abra **Manutenção Pro** nas Atividades.
3. Clique em **Iniciar manutenção** e autorize no diálogo do sistema.
4. Acompanhe as etapas. Não cancele durante a atualização de pacotes.
5. Se a conferência pedir reinício, **Reiniciar agora** pede confirmação e lista os motivos.

No terminal, o mesmo procedimento de sempre continua valendo:

```bash
sudo ./maintenence_pro.sh
```

Sem `MAINT_GUI=1`, a saída do script é a mesma de antes. Com `MAINT_GUI=1`, o script também emite os marcadores `@@STEP`, `@@RESULT`, `@@REBOOT` e `@@WARN` para a interface. O aplicativo usa a cópia em `/usr/libexec/manutencao-pro/`, não o arquivo da sua pasta pessoal.

## Privilégios e a checagem GLX

O polkit autoriza só `/usr/libexec/manutencao-pro/wrapper` (`auth_admin_keep`, `exec.path` e `exec.allow_gui`). O wrapper e o script instalados pertencem ao root e não são editáveis pelo usuário.

O `pkexec` limpa o ambiente. A anotação `allow_gui` devolve só `DISPLAY` e `XAUTHORITY`, e a página do pkexec desaconselha confiar nisso. Por isso o aplicativo lê `DISPLAY`, `XAUTHORITY` e `WAYLAND_DISPLAY` da sessão e os entrega como argumentos. O wrapper valida de novo (formato, dono e caminho) e só então exporta. Sem argumento válido, essas variáveis são apagadas.

A checagem continua dentro do script (`glxinfo` quando `DISPLAY` está definido). Ela não foi duplicada na interface, para o resultado ser o mesmo do terminal. No GNOME Wayland o GLX usa o XWayland, então o par que importa é `DISPLAY` mais `XAUTHORITY`. `WAYLAND_DISPLAY` é repassado para o ambiente da sessão, mas o script não consulta essa variável.

O wrapper também define `DEBIAN_FRONTEND=noninteractive` e `NEEDRESTART_MODE=a`, e coloca no `PATH` um `sudo` que preserva só essas duas variáveis. Assim o `sudo` que já existe dentro do script não perde o modo não interativo.

## Desinstalar

```bash
sudo apt remove manutencao-pro
```

O histórico em `~/.local/state/manutencao-pro/` permanece, porque é dado do usuário. O atalho global, se tiver sido criado, sai com `manutencao-pro-remover-atalho` antes da remoção, ou depois pelas configurações de teclado do GNOME.

## Gerar o pacote

```bash
sudo apt install meson ninja-build debhelper dh-python
dpkg-buildpackage -us -uc -b
```

O arquivo gerado é `manutencao-pro_1.0.2_all.deb`.

## O que o script faz

**1. Atualização de pacotes**
- `apt-get update` atualiza a lista de pacotes dos repositórios.
- `apt-get dist-upgrade -y` aplica upgrades, inclusive trocas de dependência.
- `apt-get autoremove -y` remove pacotes órfãos.
- `apt-get autoclean` e `apt-get clean` limpam o cache de `.deb`.
- `apt-get --fix-broken install` e `dpkg --configure -a` consertam dependência quebrada ou pacote pela metade.

**2. Limpeza de logs**
- `journalctl --vacuum-time=30d` apaga logs do systemd com mais de 30 dias.

**3. GPU NVIDIA**
- DKMS: confere o módulo do kernel atual e recompila se precisar.
- Driver no repositório e na página da NVIDIA (só consulta, não instala a versão de fora).
- Blacklist do nouveau.
- Link GLX (`libglxserver_nvidia.so`).
- Renderização GLX com `glxinfo`, para não cair no Mesa.

**4. Microcode e firmware**
- Confere o microcode da CPU.
- Com `fwupd`, aplica o UEFI dbx. Firmware de hardware só avisa.

**5. Relatório final**
- Se kernel, driver, microcode, DKMS, nouveau ou o link GLX exigirem reinício, lista o motivo. Senão, confirma que não precisa reiniciar.
