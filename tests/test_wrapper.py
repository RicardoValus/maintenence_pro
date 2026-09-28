from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "libexec" / "wrapper"
SCRIPT = ROOT / "maintenence_pro.sh"


class WrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("não exercitar o wrapper como root")

    def test_rejects_unknown_argument(self) -> None:
        result = _run(["--rm", "-rf", "/"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("não permitido", result.stderr)
        self.assertNotIn("apt-get", result.stdout + result.stderr)

    def test_rejects_bad_display(self) -> None:
        result = _run(["--display", "evil;reboot"])
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Manutenção concluída", result.stdout)

    def test_valid_display_does_not_run_the_script(self) -> None:
        result = _run(["--display", ":0", "--wayland-display", "wayland-0"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("pkexec", result.stderr)
        self.assertNotIn("@@STEP", result.stdout)

    def test_session_reaches_the_script_after_setsid(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            probe = directory / "probe.sh"
            probe.write_text(
                "#!/bin/bash\nprintf 'DISPLAY=[%s]\\n' \"${DISPLAY-}\"\n",
                encoding="utf-8",
            )
            probe.chmod(0o755)
            wrapped = directory / "wrapper"
            text = WRAPPER.read_text(encoding="utf-8")
            text = text.replace(
                'SCRIPT="/usr/libexec/manutencao-pro/maintenence_pro.sh"',
                f'SCRIPT="{probe}"',
                1,
            )
            text = text.replace(
                """if [ "$(id -u)" -ne 0 ] || [ -z "${PKEXEC_UID:-}" ]; then
    printf '%s\\n' "Este wrapper só pode ser executado via pkexec." >&2
    exit 1
fi""",
                'export PKEXEC_UID="${PKEXEC_UID:-$(id -u)}"',
                1,
            )
            self.assertNotIn("maintenence_pro.sh", text)
            self.assertNotIn("só pode ser executado via pkexec", text)
            wrapped.write_text(text, encoding="utf-8")
            wrapped.chmod(0o755)
            result = subprocess.run(
                ["bash", str(wrapped), "--display", ":0"],
                check=False,
                capture_output=True,
                text=True,
                env={"PATH": "/usr/bin:/bin", "PKEXEC_UID": str(os.getuid())},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DISPLAY=[:0]", result.stdout)

    def test_script_syntax_and_step_ids(self) -> None:
        syntax = subprocess.run(["bash", "-n", str(SCRIPT)], check=False, capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        text = SCRIPT.read_text(encoding="utf-8")
        from manutencao_pro.constants import STEP_IDS

        found = []
        for line in text.splitlines():
            parts = line.split()
            if parts and parts[0] == "gui_step":
                found.append(parts[2])
        self.assertEqual(tuple(found), STEP_IDS)


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WRAPPER), *args],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PKEXEC_UID": ""},
    )
