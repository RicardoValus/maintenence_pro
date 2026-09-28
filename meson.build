project(
  'manutencao-pro',
  version: '1.0.2',
  meson_version: '>= 0.60.0',
  license: 'MIT',
  default_options: ['warning_level=0'],
)

py = import('python').find_installation('python3', pure: true)

subdir('python')

install_data(
  'bin/manutencao-pro',
  'bin/manutencao-pro-instalar-atalho',
  'bin/manutencao-pro-remover-atalho',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

libexec = get_option('libexecdir') / 'manutencao-pro'
install_data('libexec/wrapper', install_dir: libexec, install_mode: 'rwxr-xr-x')
install_data('maintenence_pro.sh', install_dir: libexec, install_mode: 'rwxr-xr-x')
install_data(
  'data/dev.ricardo.ManutencaoPro.desktop',
  install_dir: get_option('datadir') / 'applications',
)
install_data(
  'data/dev.ricardo.ManutencaoPro.metainfo.xml',
  install_dir: get_option('datadir') / 'metainfo',
)
install_data(
  'data/dev.ricardo.ManutencaoPro.policy',
  install_dir: get_option('datadir') / 'polkit-1' / 'actions',
)
install_data(
  'data/shortcuts.ui',
  install_dir: get_option('datadir') / 'manutencao-pro',
)
install_data(
  'data/icons/hicolor/scalable/apps/dev.ricardo.ManutencaoPro.svg',
  install_dir: get_option('datadir') / 'icons' / 'hicolor' / 'scalable' / 'apps',
)
install_data(
  'data/icons/hicolor/symbolic/apps/dev.ricardo.ManutencaoPro-symbolic.svg',
  install_dir: get_option('datadir') / 'icons' / 'hicolor' / 'symbolic' / 'apps',
)
install_man(
  'man/manutencao-pro.1',
  'man/manutencao-pro-instalar-atalho.1',
  'man/manutencao-pro-remover-atalho.1',
)

test_env = environment()
test_env.prepend('PYTHONPATH', meson.project_source_root() / 'python')
test_env.set('MAINT_DEMO_DELAY', '0')
test(
  'unit',
  py,
  args: ['-m', 'unittest', 'discover', '-s', meson.project_source_root() / 'tests', '-v'],
  env: test_env,
  timeout: 90,
)
