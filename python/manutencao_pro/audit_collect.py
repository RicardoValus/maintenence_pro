from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from manutencao_pro.audit_model import (
    APT_BATCH_SIZE,
    SOURCE_SESSION,
    USER_SHELL_FILES,
    AptPackage,
    EnvVariable,
    EnvironmentSnapshot,
    Extension,
    ManualItem,
    Repository,
    canonicalize,
)
from manutencao_pro.audit_os import read_system_origin
from manutencao_pro.audit_parse import (
    is_secret_name,
    parse_apt_policy,
    parse_cargo_list,
    parse_dpkg_query,
    parse_extension_dirname,
    parse_extension_listing,
    parse_flatpak_list,
    parse_npm_list,
    parse_pip_list,
    parse_shell_file,
    parse_snap_list,
)
from manutencao_pro.i18n import _

_DEV_ENV_NAMES = frozenset(
    {
        "EDITOR",
        "VISUAL",
        "PAGER",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "PATH",
        "GOPATH",
        "GOROOT",
        "GOBIN",
        "CARGO_HOME",
        "RUSTUP_HOME",
        "NPM_CONFIG_PREFIX",
        "NODE_PATH",
        "PYENV_ROOT",
        "NVM_DIR",
        "SDKMAN_DIR",
        "JAVA_HOME",
        "ANDROID_HOME",
        "ANDROID_SDK_ROOT",
        "FLUTTER_ROOT",
        "DENO_INSTALL",
        "PNPM_HOME",
        "BUN_INSTALL",
        "DOCKER_HOST",
        "KUBECONFIG",
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "PIP_INDEX_URL",
    }
)
_EDITOR_DIRS = {"code": ".vscode/extensions", "cursor": ".cursor/extensions"}


@dataclass(frozen=True)
class CommandResult:
    code: int
    stdout: str
    stderr: str


def run_command(argv: list[str], timeout: float = 180) -> CommandResult:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return CommandResult(127, "", "não encontrado")
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", "tempo esgotado")
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def collect_environment(
    runner: Callable[..., CommandResult] | None = None,
    *,
    home: Path | None = None,
    apt_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
    os_release: Path | None = None,
) -> EnvironmentSnapshot:
    execute = runner or run_command
    root = home or Path.home()
    sources = apt_dir or Path("/etc/apt")
    release = os_release or Path("/etc/os-release")
    env = os.environ if environ is None else environ
    manual: list[ManualItem] = []
    unavailable: list[str] = []
    variables, shell_manual = _collect_variables(root, env)
    manual.extend(shell_manual)
    repos, repo_manual = _collect_repositories(sources)
    manual.extend(repo_manual)
    return canonicalize(
        EnvironmentSnapshot(
            apt_packages=_collect_apt(execute, manual),
            repositories=repos,
            npm_packages=_collect_tool(
                execute,
                _npm_argv(root, env),
                "npm",
                parse_npm_list,
                unavailable,
                manual,
            ),
            pip_packages=_collect_tool(
                execute,
                ["python3", "-m", "pip", "list", "--user", "--format=json"],
                "pip",
                parse_pip_list,
                unavailable,
                manual,
            ),
            cargo_packages=_collect_tool(
                execute,
                [_command(root, env, "cargo"), "install", "--list"],
                "cargo",
                parse_cargo_list,
                unavailable,
                manual,
            ),
            flatpaks=_collect_flatpak(execute, unavailable, manual),
            snaps=_collect_snap(execute, unavailable, manual),
            variables=variables,
            extensions=_collect_extensions(execute, root, unavailable, manual),
            manual=tuple(manual),
            unavailable=tuple(unavailable),
            system=_collect_system(execute, release),
        )
    )


def _collect_system(runner: Callable[..., CommandResult], os_release: Path):
    result = runner(["dpkg", "--print-architecture"], timeout=15)
    architecture = ""
    if result.code == 0 and result.stdout.strip():
        architecture = result.stdout.split()[0]
    return read_system_origin(os_release, architecture)


def _collect_apt(runner: Callable[..., CommandResult], manual: list[ManualItem]) -> tuple:
    listed = runner(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${db:Status-Status}\n"], timeout=60)
    if listed.code != 0 or not listed.stdout.strip():
        manual.append(ManualItem("apt", "apt", _("não foi possível listar os pacotes")))
        return ()
    packages = parse_dpkg_query(listed.stdout)
    origins = _apt_origins(runner, [item.name for item in packages])
    return tuple(AptPackage(item.name, item.version, origins.get(item.name, "desconhecida")) for item in packages)


def _apt_origins(runner: Callable[..., CommandResult], names: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for offset in range(0, len(names), APT_BATCH_SIZE):
        batch = names[offset : offset + APT_BATCH_SIZE]
        result = runner(["apt-cache", "policy", *batch], timeout=180)
        if result.code != 0 or not result.stdout.strip():
            continue
        for item in parse_apt_policy(result.stdout):
            found[item.name] = item.origin
    return found


def _command(home: Path, env: Mapping[str, str], name: str) -> str:
    found = _on_path(env.get("PATH", ""), name)
    if found:
        return found
    if name == "npm":
        npm = _nvm_npm(home)
        if npm is not None:
            return str(npm)
    if name == "cargo":
        cargo = home / ".cargo" / "bin" / "cargo"
        if cargo.is_file():
            return str(cargo)
    return name


def _on_path(path: str, name: str) -> str:
    for entry in path.split(":"):
        if not entry:
            continue
        candidate = Path(entry) / name
        if candidate.is_file():
            return str(candidate)
    return ""


def _npm_argv(home: Path, env: Mapping[str, str]) -> list[str]:
    npm = _command(home, env, "npm")
    node = Path(npm).with_name("node")
    if node.is_file():
        return [str(node), npm, "list", "-g", "--depth=0", "--json"]
    return [npm, "list", "-g", "--depth=0", "--json"]


def _nvm_npm(home: Path) -> Path | None:
    binaries = _nvm_binaries(home)
    if not binaries:
        return None
    matched = [item for item in binaries if _version_matches(item, _nvm_alias(home))]
    if matched:
        return matched[-1]
    return binaries[-1]


def _nvm_binaries(home: Path) -> list[Path]:
    root = home / ".nvm" / "versions" / "node"
    if not root.is_dir():
        return []
    return sorted(path for path in root.glob("*/bin/npm") if path.is_file())


def _nvm_alias(home: Path) -> str:
    alias = home / ".nvm" / "alias" / "default"
    if not alias.is_file():
        return ""
    version = alias.read_text(encoding="utf-8").strip()
    if not version or "/" in version:
        return ""
    return version if version.startswith("v") else f"v{version}"


def _version_matches(npm: Path, alias: str) -> bool:
    if not alias:
        return False
    name = npm.parents[1].name
    return name == alias or name.startswith(f"{alias}.")


def _collect_tool(runner, argv: list[str], category: str, parser, unavailable: list[str], manual: list[ManualItem]):
    result = runner(argv, timeout=60)
    if result.code == 127:
        unavailable.append(category)
        return ()
    if not result.stdout.strip():
        if result.code != 0:
            unavailable.append(category)
        return ()
    try:
        return parser(result.stdout)
    except ValueError:
        manual.append(ManualItem(category, category, _("não foi possível ler a lista")))
        return ()


def _collect_flatpak(runner, unavailable: list[str], manual: list[ManualItem]):
    return _collect_tool(
        runner,
        ["flatpak", "list", "--app", "--columns=application,version,origin"],
        "flatpak",
        parse_flatpak_list,
        unavailable,
        manual,
    )


def _collect_snap(runner, unavailable: list[str], manual: list[ManualItem]):
    return _collect_tool(runner, ["snap", "list"], "snap", parse_snap_list, unavailable, manual)


def _collect_repositories(apt_dir: Path) -> tuple[tuple[Repository, ...], tuple[ManualItem, ...]]:
    manual: list[ManualItem] = []
    repos: list[Repository] = []
    main = apt_dir / "sources.list"
    if main.is_file():
        _append_repo(main, "sources.list", repos, manual)
    extra = apt_dir / "sources.list.d"
    if extra.is_dir():
        for path in sorted(extra.iterdir()):
            if path.is_file() and path.suffix in {".list", ".sources"}:
                _append_repo(path, path.name, repos, manual)
    return tuple(repos), tuple(manual)


def _append_repo(path: Path, filename: str, repos: list[Repository], manual: list[ManualItem]) -> None:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        manual.append(ManualItem("repository", filename, str(exc)))
        return
    repos.append(Repository(filename, content))


def _collect_variables(home: Path, environ: Mapping[str, str]) -> tuple[tuple[EnvVariable, ...], tuple[ManualItem, ...]]:
    variables: list[EnvVariable] = []
    manual: list[ManualItem] = []
    declared: set[str] = set()
    hidden: set[str] = set()
    for filename in USER_SHELL_FILES:
        path = home / filename
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            manual.append(ManualItem("environment", filename, str(exc)))
            continue
        found, problems = parse_shell_file(filename, text)
        variables.extend(found)
        manual.extend(problems)
        declared.update(item.name for item in found)
        hidden.update(item.name for item in problems)
    variables.extend(_session_variables(environ, declared, hidden, manual))
    return tuple(variables), tuple(manual)


def _session_variables(environ: Mapping[str, str], declared: set[str], hidden: set[str], manual: list[ManualItem]) -> list[EnvVariable]:
    found: list[EnvVariable] = []
    for name in sorted(_DEV_ENV_NAMES):
        if name in declared or name in hidden or name not in environ:
            continue
        if is_secret_name(name):
            manual.append(ManualItem("environment", name, _("variável sensível; o valor não entra no backup")))
            continue
        value = environ[name]
        if "\n" in value or "\x00" in value:
            continue
        found.append(EnvVariable(name, value, SOURCE_SESSION, ""))
    return found


def _collect_extensions(runner, home: Path, unavailable: list[str], manual: list[ManualItem]) -> tuple[Extension, ...]:
    items: list[Extension] = []
    for editor in ("code", "cursor"):
        items.extend(_collect_editor(runner, home, editor, unavailable, manual))
    return tuple(items)


def _collect_editor(runner, home: Path, editor: str, unavailable: list[str], manual: list[ManualItem]) -> tuple[Extension, ...]:
    for argv in _editor_commands(home, editor):
        result = runner(argv, timeout=30)
        if result.code == 127:
            continue
        if not result.stdout.strip():
            if result.code == 0:
                return ()
            continue
        try:
            return parse_extension_listing(editor, result.stdout)
        except ValueError:
            manual.append(ManualItem("extension", editor, _("não foi possível ler as extensões")))
            return ()
    scanned = _scan_extensions(home, editor)
    if scanned is None:
        unavailable.append(editor)
        return ()
    return scanned


def _editor_commands(home: Path, editor: str) -> list[list[str]]:
    commands = [[editor, "--list-extensions", "--show-versions"]]
    for candidate in (Path(f"/usr/bin/{editor}"), home / ".local/bin" / editor, Path(f"/snap/bin/{editor}")):
        if candidate.is_file():
            commands.append([str(candidate), "--list-extensions", "--show-versions"])
    return commands


def _scan_extensions(home: Path, editor: str) -> tuple[Extension, ...] | None:
    directory = home / _EDITOR_DIRS[editor]
    if not directory.is_dir():
        return None
    items: list[Extension] = []
    for path in sorted(directory.iterdir()):
        if not path.is_dir():
            continue
        parsed = parse_extension_dirname(editor, path.name)
        if parsed is not None:
            items.append(parsed)
    return tuple(items)
