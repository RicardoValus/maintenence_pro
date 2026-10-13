from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "maintenence_pro.sh"

FIXTURE = {
    "IDS": [
        {"downloadInfo": {"DisplayVersion": "615.78.08", "IsRecommended": "0", "IsFeaturePreview": "1"}},
        {"downloadInfo": {"DisplayVersion": "595.104.02", "IsRecommended": "1", "IsFeaturePreview": "0"}},
        {"downloadInfo": {"DisplayVersion": "615.71.09", "IsRecommended": "0", "IsFeaturePreview": "1"}},
        {"downloadInfo": {"DisplayVersion": "595.91.07", "IsRecommended": "1", "IsFeaturePreview": "0"}},
        {"downloadInfo": {"DisplayVersion": "610.57.04", "IsRecommended": "0", "IsFeaturePreview": "1"}},
        {"downloadInfo": {"DisplayVersion": "", "Version": "999.1", "IsRecommended": "1", "IsFeaturePreview": "0"}},
    ]
}


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _parser_source() -> str:
    match = re.search(r"parse_nvidia_lookup\(\) \{\n    python3 -c '\n(.*?)\n'\n\}", _script(), re.S)
    if match is None:
        raise AssertionError("parser da consulta NVIDIA não encontrado")
    return match.group(1)


def _parse(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-c", _parser_source()],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


class NvidiaLookupTests(unittest.TestCase):
    def test_lookup_uses_driver_service_not_stale_markdown(self) -> None:
        text = _script()
        self.assertNotIn("drivers/unix.md", text)
        self.assertIn("AjaxDriverService.php", text)

    def test_selects_current_branches_not_older_entries(self) -> None:
        result = _parse(FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "595.104.02\n615.78.08\n")

    def test_rejects_payload_without_versions(self) -> None:
        result = _parse({"IDS": [{"downloadInfo": {"DisplayVersion": "", "IsRecommended": "1"}}]})
        self.assertEqual(result.returncode, 1)

    def test_installed_feature_branch_is_behind_current_one(self) -> None:
        match = re.search(r"nvidia_ver_gt\(\) \{.*?\n\}", _script(), re.S)
        if match is None:
            raise AssertionError("nvidia_ver_gt não encontrado")
        script = f"""
{match.group(0)}
latest=$(printf '%s\\n%s\\n' '595.104.02' '615.78.08' | grep -v '^$' | sort -V | tail -1)
ativo=615.71.09
if [ "$ativo" = "$latest" ]; then
    echo ok
elif nvidia_ver_gt "$latest" "$ativo"; then
    echo newer
else
    echo ahead
fi
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "newer")
