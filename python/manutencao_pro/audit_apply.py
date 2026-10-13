from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from manutencao_pro.audit_collect import CommandResult, run_command
from manutencao_pro.audit_model import MAX_REPO_CHARS, USER_SHELL_FILES, ManualItem, is_repo_path
from manutencao_pro.audit_parse import assigned_name, assignment_exists, safe_env_line
from manutencao_pro.audit_plan import ImportPlan, PlannedAction
from manutencao_pro.i18n import _

APPLY_TIMEOUT = 1800
EventCallback = Callable[[bool, str, str], None]


class ApplyHooks:
    def run(self, argv: list[str]) -> CommandResult:
        raise NotImplementedError

    def write_root(self, path: str, content: str) -> CommandResult:
        raise NotImplementedError

    def append_user(self, path: str, line: str) -> CommandResult:
        raise NotImplementedError


class ProductionHooks(ApplyHooks):
    def run(self, argv: list[str]) -> CommandResult:
        return run_command(argv, timeout=APPLY_TIMEOUT)

    def write_root(self, path: str, content: str) -> CommandResult:
        return write_root_file(path, content)

    def append_user(self, path: str, line: str) -> CommandResult:
        return append_user_line(path, line)


def privileged_argv(argv: tuple[str, ...] | list[str], needs_root: bool, is_root: bool) -> list[str]:
    command = list(argv)
    if needs_root and not is_root:
        return ["pkexec", *command]
    return command


def apply_plan(plan: ImportPlan, hooks: ApplyHooks, on_event: EventCallback, *, is_root: bool = False) -> list[ManualItem]:
    failures: list[ManualItem] = []
    for action in plan.actions:
        try:
            result = _execute(action, hooks, is_root)
        except Exception as exc:
            detail = str(exc)
            on_event(False, action.summary, detail)
            failures.append(ManualItem(action.kind, action.summary, detail))
            continue
        detail = _brief(result.stderr or result.stdout)
        ok = result.code == 0
        on_event(ok, action.summary, detail)
        if not ok:
            failures.append(ManualItem(action.kind, action.summary, detail or _("falhou")))
    return failures


def append_user_line(relative: str, line: str, *, home: Path | None = None) -> CommandResult:
    if relative not in USER_SHELL_FILES or not safe_env_line(line, relative):
        return CommandResult(1, "", _("recusado"))
    name = assigned_name(line)
    if name is None:
        return CommandResult(1, "", _("recusado"))
    root = (home or Path.home()).resolve()
    path = (root / relative).resolve()
    try:
        if not path.is_relative_to(root):
            return CommandResult(1, "", _("recusado"))
        existing = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        if assignment_exists(existing, name):
            return CommandResult(0, _("já existia"), "")
        prefix = "\n" if existing and not existing.endswith("\n") else ""
        path.write_text(existing + prefix + line + "\n", encoding="utf-8")
    except OSError as exc:
        return CommandResult(1, "", str(exc))
    return CommandResult(0, "", "")


def write_root_file(
    path: str,
    content: str,
    *,
    is_root: bool | None = None,
    runner: Callable[..., CommandResult] | None = None,
) -> CommandResult:
    if not is_repo_path(path) or "\x00" in content or len(content) > MAX_REPO_CHARS:
        return CommandResult(1, "", _("arquivo recusado"))
    root = os.geteuid() == 0 if is_root is None else is_root
    if root:
        return _write_as_root(path, content)
    return _install_with_pkexec(path, content, runner or run_command)


def _execute(action: PlannedAction, hooks: ApplyHooks, is_root: bool) -> CommandResult:
    if action.kind == "system_write":
        return hooks.write_root(action.path, action.content)
    if action.kind == "user_append":
        return hooks.append_user(action.path, action.content)
    return hooks.run(privileged_argv(action.argv, action.needs_root, is_root))


def _write_as_root(path: str, content: str) -> CommandResult:
    try:
        Path(path).write_text(content, encoding="utf-8")
        os.chmod(path, 0o644)
    except OSError as exc:
        return CommandResult(1, "", str(exc))
    return CommandResult(0, "", "")


def _install_with_pkexec(path: str, content: str, runner: Callable[..., CommandResult]) -> CommandResult:
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="manutencao-pro-", delete=False)
    temp = handle.name
    try:
        handle.write(content)
        handle.close()
        os.chmod(temp, 0o644)
        install = shutil.which("install") or "/usr/bin/install"
        return runner(["pkexec", install, "-m", "644", temp, path], timeout=300)
    except OSError as exc:
        return CommandResult(1, "", str(exc))
    finally:
        try:
            os.unlink(temp)
        except OSError:
            pass


def _brief(detail: str) -> str:
    text = " ".join(detail.split())
    if len(text) > 300:
        return text[:300] + "…"
    return text
