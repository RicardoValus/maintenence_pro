from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from manutencao_pro.distro import (
    DEBIAN_PROFILE,
    POP_PROFILE,
    NvidiaStrategy,
    desktop_environment,
    detect_profile,
    profile_from_os_release_text,
    shell_exports,
    supports_gnome_keybind_schemas,
)
from manutencao_pro.keybind import install_shortcut, remove_shortcut

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "maintenence_pro.sh"

POP_OS_RELEASE = """\
NAME="Pop!_OS"
VERSION="24.04 LTS"
ID=pop
ID_LIKE="ubuntu debian"
PRETTY_NAME="Pop!_OS 24.04 LTS"
VERSION_ID="24.04"
VERSION_CODENAME=noble
"""

DEBIAN_OS_RELEASE = """\
PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
NAME="Debian GNU/Linux"
VERSION_ID="13"
VERSION="13 (trixie)"
VERSION_CODENAME=trixie
ID=debian
"""


class DistroProfileTests(unittest.TestCase):
    def test_pop_os_release_selects_pop_profile(self) -> None:
        profile = profile_from_os_release_text(POP_OS_RELEASE)
        self.assertEqual(profile, POP_PROFILE)
        self.assertEqual(profile.key, "pop")
        self.assertEqual(profile.expected_desktop, "cosmic")
        self.assertEqual(profile.nvidia_strategy, NvidiaStrategy.SYSTEM_MANAGED)
        self.assertFalse(profile.manages_xorg_conf)
        self.assertFalse(profile.manages_nouveau_blacklist)
        self.assertFalse(profile.manages_glx_link)
        self.assertFalse(profile.glx_mismatch_fatal_on_xwayland)

    def test_debian_os_release_selects_debian_profile(self) -> None:
        profile = profile_from_os_release_text(DEBIAN_OS_RELEASE)
        self.assertEqual(profile, DEBIAN_PROFILE)
        self.assertEqual(profile.nvidia_strategy, NvidiaStrategy.FULL)
        self.assertTrue(profile.manages_xorg_conf)
        self.assertTrue(profile.manages_nouveau_blacklist)
        self.assertTrue(profile.manages_glx_link)
        self.assertTrue(profile.glx_mismatch_fatal_on_xwayland)

    def test_id_like_pop_without_id_pop(self) -> None:
        text = 'ID=custom\nID_LIKE="pop ubuntu debian"\nVERSION_ID="24.04"\n'
        self.assertEqual(profile_from_os_release_text(text).key, "pop")

    def test_unknown_defaults_to_debian(self) -> None:
        text = 'ID=fedora\nVERSION_ID="42"\n'
        self.assertEqual(profile_from_os_release_text(text), DEBIAN_PROFILE)

    def test_detect_profile_reads_mock_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "os-release"
            path.write_text(POP_OS_RELEASE, encoding="utf-8")
            self.assertEqual(detect_profile(path).key, "pop")

    def test_detect_profile_missing_file_defaults_to_debian(self) -> None:
        missing = Path("/tmp/manutencao-pro-missing-os-release-does-not-exist")
        self.assertEqual(detect_profile(missing), DEBIAN_PROFILE)

    def test_glx_mismatch_fatal_rules(self) -> None:
        self.assertTrue(
            DEBIAN_PROFILE.glx_mismatch_is_fatal(display=":0", wayland_display="wayland-0")
        )
        self.assertFalse(
            POP_PROFILE.glx_mismatch_is_fatal(display=":0", wayland_display="wayland-0")
        )
        self.assertTrue(POP_PROFILE.glx_mismatch_is_fatal(display=":0", wayland_display=""))

    def test_shell_exports_pop(self) -> None:
        text = shell_exports(POP_PROFILE)
        self.assertIn("export MAINT_PROFILE_KEY=pop", text)
        self.assertIn("export MAINT_NVIDIA_STRATEGY=system_managed", text)
        self.assertIn("export MAINT_MANAGES_XORG_CONF=0", text)
        self.assertIn("export MAINT_MANAGES_NOUVEAU=0", text)
        self.assertIn("export MAINT_MANAGES_GLX_LINK=0", text)
        self.assertIn("export MAINT_GLX_FATAL_ON_XWAYLAND=0", text)

    def test_shell_exports_debian(self) -> None:
        text = shell_exports(DEBIAN_PROFILE)
        self.assertIn("export MAINT_PROFILE_KEY=debian", text)
        self.assertIn("export MAINT_NVIDIA_STRATEGY=full", text)
        self.assertIn("export MAINT_MANAGES_XORG_CONF=1", text)

    def test_desktop_environment_detection(self) -> None:
        self.assertEqual(desktop_environment({"XDG_CURRENT_DESKTOP": "COSMIC"}), "cosmic")
        self.assertEqual(desktop_environment({"XDG_CURRENT_DESKTOP": "GNOME"}), "gnome")
        self.assertEqual(desktop_environment({"XDG_CURRENT_DESKTOP": "pop:GNOME"}), "gnome")
        self.assertEqual(desktop_environment({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}), "gnome")
        self.assertFalse(supports_gnome_keybind_schemas({"XDG_CURRENT_DESKTOP": "COSMIC"}))
        self.assertTrue(supports_gnome_keybind_schemas({"XDG_CURRENT_DESKTOP": "GNOME"}))


class KeybindDesktopTests(unittest.TestCase):
    def test_cosmic_skips_install_with_message(self) -> None:
        buffer = io.StringIO()
        with mock.patch("sys.stderr", buffer):
            code = install_shortcut({"XDG_CURRENT_DESKTOP": "COSMIC"})
        self.assertEqual(code, 1)
        self.assertIn("indisponível neste desktop por enquanto", buffer.getvalue())

    def test_cosmic_skips_remove_with_message(self) -> None:
        buffer = io.StringIO()
        with mock.patch("sys.stderr", buffer):
            code = remove_shortcut({"XDG_CURRENT_DESKTOP": "COSMIC"})
        self.assertEqual(code, 1)
        self.assertIn("indisponível neste desktop por enquanto", buffer.getvalue())


class ShellProfileBranchTests(unittest.TestCase):
    def test_bash_loads_pop_from_mock_os_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "os-release"
            path.write_text(POP_OS_RELEASE, encoding="utf-8")
            script = f"""
set -euo pipefail
export PYTHONPATH={ROOT / "python"}
export MAINT_OS_RELEASE={path}
source <(sed -n '/^load_distro_profile()/,/^}}/p; /^is_xwayland_session()/,/^}}/p; /^glx_mismatch_is_fatal()/,/^}}/p' {SCRIPT})
load_distro_profile
test "$MAINT_PROFILE_KEY" = "pop"
test "$MAINT_NVIDIA_STRATEGY" = "system_managed"
test "$MAINT_MANAGES_NOUVEAU" = "0"
test "$MAINT_MANAGES_GLX_LINK" = "0"
test "$MAINT_MANAGES_XORG_CONF" = "0"
DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 glx_mismatch_is_fatal && exit 1 || true
DISPLAY=:0 WAYLAND_DISPLAY= glx_mismatch_is_fatal
"""
            result = subprocess.run(
                ["bash", "-c", script],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONPATH": str(ROOT / "python")},
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_bash_loads_debian_from_mock_os_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "os-release"
            path.write_text(DEBIAN_OS_RELEASE, encoding="utf-8")
            script = f"""
set -euo pipefail
export PYTHONPATH={ROOT / "python"}
export MAINT_OS_RELEASE={path}
source <(sed -n '/^load_distro_profile()/,/^}}/p; /^is_xwayland_session()/,/^}}/p; /^glx_mismatch_is_fatal()/,/^}}/p' {SCRIPT})
load_distro_profile
test "$MAINT_PROFILE_KEY" = "debian"
test "$MAINT_NVIDIA_STRATEGY" = "full"
test "$MAINT_MANAGES_NOUVEAU" = "1"
DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 glx_mismatch_is_fatal
"""
            result = subprocess.run(
                ["bash", "-c", script],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONPATH": str(ROOT / "python")},
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_system_managed_install_is_noop(self) -> None:
        script = f"""
set -euo pipefail
export PYTHONPATH={ROOT / "python"}
NV_UP_STATE=skip
append_warn() {{ :; }}
append_reboot() {{ :; }}
source <(sed -n '/^install_nvidia_upstream()/,/^}}/p' {SCRIPT})
MAINT_NVIDIA_STRATEGY=system_managed
MAINT_PROFILE_NAME='Pop!_OS'
install_nvidia_upstream "999.0" "https://us.download.nvidia.com/XFree86/Linux-x86_64/999.0/NVIDIA-Linux-x86_64-999.0.run"
test "$NV_UP_STATE" = "skip"
"""
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("desabilitada", result.stdout)
        self.assertNotIn("Baixando", result.stdout)
