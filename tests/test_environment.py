from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from manutencao_pro.audit_apply import append_user_line, apply_plan, privileged_argv, write_root_file
from manutencao_pro.audit_collect import CommandResult, collect_environment
from manutencao_pro.audit_schema import dumps_snapshot, loads_snapshot
from manutencao_pro.audit_model import (
    SCHEMA_VERSION,
    AptPackage,
    EnvVariable,
    EnvironmentSnapshot,
    Extension,
    ManualItem,
    RemotePackage,
    Repository,
    SchemaError,
    ToolPackage,
    row_matches,
)
from manutencao_pro.audit_parse import parse_apt_policy, parse_extension_listing, parse_npm_list, parse_shell_file
from manutencao_pro.audit_plan import ImportPlan, PlannedAction, build_plan, format_manual_report, format_plan

APT_POLICY = """\
git:
  Installed: 1:2.47.3-0+deb13u1
  Candidate: 1:2.47.3-0+deb13u1
  Version table:
 *** 1:2.47.3-0+deb13u1 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages
        100 /var/lib/dpkg/status
code:
  Installed: 1.94.0
  Candidate: 1.94.0
  Version table:
 *** 1.94.0 100
        100 /var/lib/dpkg/status
absent:
  Installed: (none)
  Candidate: 1.0
  Version table:
     1.0 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages
"""

TOOLS = {
    "apt-get": "/usr/bin/apt-get",
    "env": "/usr/bin/env",
    "npm": "/usr/bin/npm",
    "python3": "/usr/bin/python3",
    "cargo": "/usr/bin/cargo",
    "flatpak": "/usr/bin/flatpak",
    "snap": "/usr/bin/snap",
    "code": "/usr/bin/code",
    "cursor": "/usr/bin/cursor",
    "install": "/usr/bin/install",
}


class ParseTests(unittest.TestCase):
    def test_apt_policy_keeps_installed_origin(self) -> None:
        packages = {item.name: item for item in parse_apt_policy(APT_POLICY)}
        self.assertEqual(packages["git"].origin, "deb.debian.org trixie/main")
        self.assertEqual(packages["code"].origin, "local")
        self.assertNotIn("absent", packages)

    def test_npm_json_with_prefix_and_shell_secrets(self) -> None:
        packages = parse_npm_list('npm warn\n{"dependencies": {"typescript": {"version": "5.6.2"}}}')
        self.assertEqual(packages, (ToolPackage("typescript", "5.6.2"),))
        text = '\n'.join(
            [
                'export EDITOR="nvim"',
                'export PATH="$HOME/.local/bin:$PATH"',
                'export NPM_TOKEN="super-secret-value"',
                "export BUILD_DATE=$(date)",
                "FOO=bar",
            ]
        )
        variables, manual = parse_shell_file(".bashrc", text)
        names = {item.name: item for item in variables}
        self.assertEqual(names["EDITOR"].raw_line, 'export EDITOR="nvim"')
        self.assertIn("$HOME", names["PATH"].raw_line)
        self.assertEqual(names["FOO"].raw_line, 'export FOO="bar"')
        self.assertNotIn("NPM_TOKEN", names)
        self.assertNotIn("BUILD_DATE", names)
        self.assertTrue(any(item.name == "NPM_TOKEN" for item in manual))
        self.assertNotIn("super-secret-value", " ".join(item.reason for item in manual))

    def test_extension_listing(self) -> None:
        items = parse_extension_listing("code", "ms-python.python@2024.12.0\n")
        self.assertEqual(items, (Extension("code", "ms-python.python", "2024.12.0"),))


class SnapshotTests(unittest.TestCase):
    def test_roundtrip_keeps_schema_and_drops_secret(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "apt_packages": [{"name": "git:amd64", "version": "1:2.0", "origin": "debian"}],
            "environment": [
                {
                    "name": "NPM_TOKEN",
                    "value": "super-secret-value",
                    "source": ".bashrc",
                    "line": 'export NPM_TOKEN="super-secret-value"',
                }
            ],
        }
        snapshot = loads_snapshot(json.dumps(payload))
        self.assertEqual(snapshot.apt_packages, (AptPackage("git", "1:2.0", "debian"),))
        self.assertEqual(snapshot.variables, ())
        text = dumps_snapshot(snapshot)
        self.assertTrue(text.startswith('{\n  "schema_version": 1'))
        self.assertNotIn("super-secret-value", text)

    def test_rejects_other_schema(self) -> None:
        with self.assertRaises(SchemaError):
            loads_snapshot('{"schema_version": 2}')

    def test_row_filter(self) -> None:
        self.assertTrue(row_matches("apt", "git", "2", "debian", "Pacotes apt", query="git", selected="all"))
        self.assertFalse(row_matches("apt", "git", "2", "debian", "Pacotes apt", query="git", selected="npm"))
        self.assertTrue(row_matches("npm", "leftpad", "1", "npm", "npm", query="", selected="npm"))


class CollectTests(unittest.TestCase):
    def test_collect_reads_files_and_marks_missing_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            apt = root / "apt"
            (apt / "sources.list.d").mkdir(parents=True)
            (apt / "sources.list").write_text("deb http://deb.debian.org/debian trixie main\n", encoding="utf-8")
            home.mkdir()
            (home / ".bashrc").write_text('export NPM_TOKEN="super-secret-value"\nexport EDITOR="nvim"\n', encoding="utf-8")
            extensions = home / ".cursor" / "extensions" / "ms-python.python-2024.12.0"
            extensions.mkdir(parents=True)
            calls: list[list[str]] = []

            def runner(argv: list[str], timeout: float = 180) -> CommandResult:
                calls.append(list(argv))
                program = Path(argv[0]).name
                if program == "apt-cache":
                    return CommandResult(0, APT_POLICY, "")
                if program == "python3":
                    return CommandResult(0, '[{"name": "black", "version": "24.1.0"}]', "")
                if program == "cargo":
                    return CommandResult(0, "ripgrep v14.1.0:\n    rg\n", "")
                if program == "flatpak":
                    return CommandResult(0, "org.mozilla.firefox\t131.0\tflathub\n", "")
                if program == "snap":
                    return CommandResult(0, "Name Version Rev Tracking Publisher Notes\ncode 1.94 172 latest vscode classic\n", "")
                return CommandResult(127, "", "não encontrado")

            snapshot = collect_environment(
                runner,
                home=home,
                apt_dir=apt,
                environ={"EDITOR": "nvim", "PATH": "/usr/bin", "NPM_TOKEN": "super-secret-value"},
            )
        self.assertEqual(snapshot.apt_packages[0].name, "code")
        self.assertIn("npm", snapshot.unavailable)
        self.assertEqual(snapshot.pip_packages, (ToolPackage("black", "24.1.0"),))
        self.assertEqual(snapshot.cargo_packages, (ToolPackage("ripgrep", "14.1.0"),))
        self.assertEqual(snapshot.snaps[0].classic, True)
        self.assertEqual(snapshot.extensions, (Extension("cursor", "ms-python.python", "2024.12.0"),))
        self.assertTrue(any(item.name == "EDITOR" and item.source == ".bashrc" for item in snapshot.variables))
        self.assertTrue(any(item.name == "PATH" and item.source == "session" for item in snapshot.variables))
        text = dumps_snapshot(snapshot)
        self.assertNotIn("super-secret-value", text)
        self.assertTrue(all(argv[0] != "sudo" for argv in calls))


class PlanTests(unittest.TestCase):
    def test_plan_orders_repos_before_apt_and_skips_what_exists(self) -> None:
        desired = EnvironmentSnapshot(
            apt_packages=(
                AptPackage("curl", "8.0", "deb.debian.org trixie/main"),
                AptPackage("git", "2.0", "deb.debian.org trixie/main"),
                AptPackage("wget", "1.21", "deb.debian.org trixie/main"),
                AptPackage("code", "1.94", "local"),
                AptPackage("git;rm -rf /", "1", "debian"),
            ),
            repositories=(
                Repository("demo.list", "deb http://example.test trixie main\n"),
                Repository("cdrom.list", "deb cdrom:[Debian] trixie main\n"),
                Repository("same.list", "deb http://same.test trixie main\n"),
                Repository("other.list", "deb http://new.test trixie main\n"),
                Repository("../evil.list", "deb http://evil.test trixie main\n"),
            ),
            npm_packages=(ToolPackage("typescript", "5.6.2"), ToolPackage("leftpad", "1.0.0")),
            variables=(
                EnvVariable("EDITOR", "nvim", ".bashrc", 'export EDITOR="nvim"'),
                EnvVariable("PATH", "/usr/bin", "session", ""),
            ),
            manual=(ManualItem("environment", "NPM_TOKEN", "variável sensível; o valor não entra no backup"),),
        )
        current = EnvironmentSnapshot(
            apt_packages=(AptPackage("git", "1.0", "deb.debian.org trixie/main"),),
            repositories=(
                Repository("same.list", "deb http://same.test trixie main\n"),
                Repository("other.list", "deb http://old.test trixie main\n"),
            ),
            npm_packages=(ToolPackage("typescript", "5.6.2"),),
            variables=(EnvVariable("EDITOR", "vim", ".bashrc", 'export EDITOR="vim"'),),
        )
        plan = build_plan(desired, current, TOOLS, apt_batch=1)
        summaries = [action.summary for action in plan.actions]
        update_at = next(index for index, summary in enumerate(summaries) if "apt-get update" in summary)
        install_at = [index for index, summary in enumerate(summaries) if "apt-get install" in summary]
        write_at = [index for index, action in enumerate(plan.actions) if action.kind == "system_write"]
        self.assertTrue(write_at)
        self.assertLess(max(write_at), update_at)
        self.assertTrue(install_at)
        self.assertLess(update_at, min(install_at))
        self.assertTrue(any("curl" in action.summary for action in plan.actions))
        self.assertFalse(any("git;rm" in action.summary or any(";" in part for part in action.argv) for action in plan.actions))
        self.assertFalse(any(action.summary.startswith("apt-get install") and "git " in action.summary for action in plan.actions))
        self.assertTrue(any(item.name == "code" for item in plan.manual))
        self.assertTrue(any(item.name == "git" for item in plan.manual))
        self.assertTrue(any("cdrom" in item.reason or item.name == "cdrom.list" for item in plan.manual))
        self.assertTrue(any("npm typescript" == item or item == "npm typescript" for item in plan.skipped) or any("typescript" in item for item in plan.skipped))
        npm = next(action for action in plan.actions if "leftpad" in action.summary)
        self.assertFalse(npm.needs_root)
        self.assertNotIn("pkexec", npm.argv)
        apt = next(action for action in plan.actions if action.summary.startswith("apt-get install"))
        self.assertTrue(apt.needs_root)
        self.assertIn("DEBIAN_FRONTEND=noninteractive", apt.argv)
        self.assertIn("-y", apt.argv)
        self.assertNotIn("pkexec", apt.argv)
        report = format_manual_report(plan.manual)
        preview = format_plan(plan)
        self.assertIn("Licenças de software", report)
        self.assertIn("NPM_TOKEN", report)
        self.assertNotIn("super-secret", report)
        self.assertNotIn("NPM_TOKEN", preview)
        self.assertTrue(any(item.name == "EDITOR" for item in plan.manual))
        self.assertTrue(any(item.name == "PATH" for item in plan.manual))
        self.assertFalse(any(action.kind == "user_append" and "EDITOR" in action.summary for action in plan.actions))

    def test_missing_tool_is_manual(self) -> None:
        desired = EnvironmentSnapshot(
            flatpaks=(RemotePackage("org.mozilla.firefox", "131.0", "flathub"),),
            snaps=(RemotePackage("code", "1.94", "", True),),
            extensions=(Extension("cursor", "ms-python.python", "2024.12.0"),),
            npm_packages=(ToolPackage("leftpad", "1.0.0"),),
        )
        tools = dict(TOOLS)
        tools["npm"] = None
        tools["cursor"] = None
        plan = build_plan(desired, EnvironmentSnapshot(), tools)
        self.assertTrue(any(action.summary.startswith("flatpak install") and "--user" in action.argv for action in plan.actions))
        snap = next(action for action in plan.actions if "snap install" in action.summary)
        self.assertIn("--classic", snap.argv)
        self.assertTrue(snap.needs_root)
        self.assertTrue(any(item.name == "npm" for item in plan.manual))
        self.assertTrue(any(item.name == "cursor" for item in plan.manual))
        self.assertFalse(any("leftpad" in action.summary for action in plan.actions))


class ApplyTests(unittest.TestCase):
    def test_failure_does_not_stop_later_steps_and_pkexec_is_selective(self) -> None:
        seen: list[list[str]] = []

        class Hooks:
            def run(self, argv: list[str]) -> CommandResult:
                seen.append(argv)
                if "update" in argv:
                    return CommandResult(1, "", "erro de rede")
                return CommandResult(0, "", "")

            def write_root(self, path: str, content: str) -> CommandResult:
                seen.append(["write", path])
                return CommandResult(1, "", "falhou")

            def append_user(self, path: str, line: str) -> CommandResult:
                seen.append(["append", path, line])
                return CommandResult(0, "", "")

        plan = ImportPlan(
            actions=(
                PlannedAction("system_write", "gravar", path="/etc/apt/sources.list.d/demo.list", content="deb http://example.test trixie main\n", needs_root=True),
                PlannedAction("command", "apt-get update (administrador)", ("/usr/bin/env", "DEBIAN_FRONTEND=noninteractive", "/usr/bin/apt-get", "update"), True),
                PlannedAction("command", "npm install -g leftpad@1.0.0", ("/usr/bin/npm", "install", "-g", "leftpad@1.0.0"), False),
                PlannedAction("user_append", "anexar", path=".bashrc", content='export EDITOR="nvim"'),
            ),
            skipped=(),
            manual=(),
        )
        events: list[bool] = []
        failures = apply_plan(plan, Hooks(), lambda ok, _summary, _detail: events.append(ok), is_root=False)
        self.assertEqual(events, [False, False, True, True])
        self.assertEqual(len(failures), 2)
        self.assertEqual(seen[1][0], "pkexec")
        self.assertEqual(seen[2][0], "/usr/bin/npm")
        self.assertEqual(seen[3][0], "append")
        rooted = privileged_argv(("/usr/bin/apt-get", "update"), True, True)
        self.assertEqual(rooted[0], "/usr/bin/apt-get")

    def test_env_append_is_idempotent_and_refuses_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            first = append_user_line(".bashrc", 'export EDITOR="nvim"', home=home)
            self.assertEqual(first.code, 0)
            text = (home / ".bashrc").read_text(encoding="utf-8")
            second = append_user_line(".bashrc", 'export EDITOR="vim"', home=home)
            self.assertEqual(second.stdout, "já existia")
            self.assertEqual((home / ".bashrc").read_text(encoding="utf-8"), text)
            self.assertEqual(append_user_line("../.bashrc", 'export EDITOR="nvim"', home=home).code, 1)
            self.assertEqual(append_user_line(".bashrc", "export FOO=$(date)", home=home).code, 1)
            self.assertNotIn("FOO", (home / ".bashrc").read_text(encoding="utf-8"))

    def test_root_write_uses_pkexec_only_for_apt_sources(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str], timeout: float = 180) -> CommandResult:
            calls.append(argv)
            return CommandResult(0, "", "")

        rejected = write_root_file("/tmp/evil.list", "deb http://example.test trixie main\n", is_root=False, runner=runner)
        self.assertEqual(rejected.code, 1)
        self.assertEqual(calls, [])
        accepted = write_root_file(
            "/etc/apt/sources.list.d/demo.list",
            "deb http://example.test trixie main\n",
            is_root=False,
            runner=runner,
        )
        self.assertEqual(accepted.code, 0)
        self.assertEqual(calls[0][0], "pkexec")
        self.assertEqual(calls[0][-1], "/etc/apt/sources.list.d/demo.list")
        self.assertNotIn("sudo", calls[0])
