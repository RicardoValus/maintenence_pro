from __future__ import annotations

import sys

from gi.repository import Gio

SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
COMMAND = "manutencao-pro --run"
BINDING_NAME = "Manutenção Pro"
CANDIDATES = ("<Ctrl><Alt>m", "<Ctrl><Alt>comma", "<Ctrl><Alt>period", "<Ctrl><Shift>m")
_KNOWN_COMMANDS = frozenset({COMMAND, "manutencao-pro"})


def normalize(binding: str) -> str:
    value = binding.strip().lower().replace(" ", "")
    return value.replace("<primary>", "<control>").replace("<ctrl>", "<control>")


def choose_binding(used: set[str]) -> str | None:
    normalized = {normalize(item) for item in used}
    for candidate in CANDIDATES:
        if normalize(candidate) not in normalized:
            return candidate
    return None


def install_shortcut() -> int:
    settings = _settings()
    if settings is None:
        return 1
    paths = list(settings.get_strv("custom-keybindings"))
    existing = _existing_binding(paths)
    if existing is not None:
        print(f"Atalho já configurado: {existing}")
        return 0
    chosen = choose_binding(set(_collect_bindings(settings, paths)))
    if chosen is None:
        print("Não há atalho livre sem sobrescrever os existentes.", file=sys.stderr)
        return 1
    if normalize(chosen) != normalize(CANDIDATES[0]):
        print(f"{CANDIDATES[0]} já está em uso. Usando {chosen}.")
    slot = _free_slot(paths)
    path = f"/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom{slot}/"
    child = Gio.Settings.new_with_path(CUSTOM_SCHEMA, path)
    child.set_string("name", BINDING_NAME)
    child.set_string("command", COMMAND)
    child.set_string("binding", chosen)
    settings.set_strv("custom-keybindings", [*paths, path])
    print(f"Atalho {chosen} registrado para {COMMAND}.")
    return 0


def remove_shortcut() -> int:
    settings = _settings()
    if settings is None:
        return 1
    paths = list(settings.get_strv("custom-keybindings"))
    kept: list[str] = []
    removed = False
    for path in paths:
        child = Gio.Settings.new_with_path(CUSTOM_SCHEMA, path)
        if child.get_string("command") in _KNOWN_COMMANDS:
            child.reset("name")
            child.reset("command")
            child.reset("binding")
            removed = True
            continue
        kept.append(path)
    settings.set_strv("custom-keybindings", kept)
    if removed:
        print("Atalho removido.")
    else:
        print("Nenhum atalho da Manutenção Pro estava configurado.")
    return 0


def _settings() -> Gio.Settings | None:
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(SCHEMA, True) is None:
        print("O atalho personalizado só está disponível no GNOME.", file=sys.stderr)
        return None
    return Gio.Settings.new(SCHEMA)


def _existing_binding(paths: list[str]) -> str | None:
    for path in paths:
        child = Gio.Settings.new_with_path(CUSTOM_SCHEMA, path)
        if child.get_string("command") in _KNOWN_COMMANDS:
            return child.get_string("binding")
    return None


def _collect_bindings(settings: Gio.Settings, paths: list[str]) -> list[str]:
    found: list[str] = []
    for key in settings.list_keys():
        value = settings.get_value(key)
        if value.get_type_string() != "s":
            continue
        text = value.get_string()
        if text.startswith("<"):
            found.append(text)
    for path in paths:
        child = Gio.Settings.new_with_path(CUSTOM_SCHEMA, path)
        binding = child.get_string("binding")
        if binding:
            found.append(binding)
    return found


def _free_slot(paths: list[str]) -> int:
    used: set[int] = set()
    for path in paths:
        name = path.rstrip("/").rsplit("/", maxsplit=1)[-1]
        suffix = name.removeprefix("custom")
        if name.startswith("custom") and suffix.isdigit():
            used.add(int(suffix))
    for index in range(30):
        if index not in used:
            return index
    print("Limite de atalhos personalizados atingido.", file=sys.stderr)
    raise SystemExit(1)
