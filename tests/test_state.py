from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from manutencao_pro.demo import lines_for
from manutencao_pro.state import ERROR, SUCCESS, WARNING, HistoryStore, RunModel, RunRecord


def _finish(scenario: str, code: int = 0) -> RunModel:
    model = RunModel()
    model.begin()
    for line in lines_for(scenario):
        model.consume(line)
    model.finish(code, None)
    return model


class ScenarioTests(unittest.TestCase):
    def test_ok(self) -> None:
        model = _finish("ok")
        self.assertEqual(model.status, "ok")
        self.assertEqual(model.results["packages"], "ok")
        self.assertFalse(model.reboot_reasons)
        self.assertTrue(all(step.status == SUCCESS for step in model.steps))

    def test_warnings(self) -> None:
        model = _finish("warnings")
        self.assertEqual(model.status, "warning")
        self.assertEqual(model.results["nvidia_upstream"], "newer")
        nvidia = next(step for step in model.steps if step.step_id == "nvidia")
        self.assertEqual(nvidia.status, WARNING)

    def test_reboot(self) -> None:
        model = _finish("reboot")
        self.assertEqual(model.status, "reboot")
        self.assertIn("kernel atualizado (6.12.41 → 6.12.48)", model.reboot_reasons)
        self.assertTrue(model.steps[-1].status == SUCCESS)

    def test_apt_failure_marks_only_the_warned_step(self) -> None:
        model = _finish("fail")
        self.assertEqual(model.status, "error")
        upgrade = next(step for step in model.steps if step.step_id == "apt-upgrade")
        update = next(step for step in model.steps if step.step_id == "apt-update")
        self.assertEqual(upgrade.status, ERROR)
        self.assertEqual(update.status, SUCCESS)

    def test_cancel_during_journal(self) -> None:
        model = RunModel()
        model.begin()
        model.consume("@@STEP 6/14 journal Limpando logs antigos")
        self.assertTrue(model.can_cancel)
        model.finish(143, 15)
        self.assertEqual(model.status, "cancelled")
        journal = next(step for step in model.steps if step.step_id == "journal")
        self.assertEqual(journal.status, "cancelled")

    def test_apt_step_cannot_be_cancelled(self) -> None:
        model = RunModel()
        model.begin()
        model.consume("@@STEP 1/14 apt-update Atualizando lista de pacotes")
        self.assertFalse(model.can_cancel)


class HistoryTests(unittest.TestCase):
    def test_keeps_last_30(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            store = HistoryStore(Path(raw))
            for index in range(35):
                store.append(
                    RunRecord(
                        started_at=f"2026-09-28T10:{index:02d}:00-03:00",
                        finished_at="2026-09-28T10:00:01-03:00",
                        duration_seconds=1,
                        status="ok",
                        warnings=[],
                        reboot_reasons=[],
                        results={"packages": "ok"},
                        log=f"log {index}",
                    )
                )
            runs = store.load()
            self.assertEqual(len(runs), 30)
            self.assertEqual(runs[0].log, "log 34")
            self.assertEqual(oct(store.path.stat().st_mode & 0o777), "0o600")
            self.assertEqual(oct(Path(raw).stat().st_mode & 0o777), "0o700")

    def test_corrupt_file_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "history.json").write_text("{", encoding="utf-8")
            self.assertEqual(HistoryStore(directory).load(), [])


class StateDirTests(unittest.TestCase):
    def test_uses_xdg_state_home(self) -> None:
        from manutencao_pro.state import state_dir

        previous = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = "/tmp/manutencao-state"
        try:
            self.assertEqual(state_dir(), Path("/tmp/manutencao-state/manutencao-pro"))
        finally:
            if previous is None:
                os.environ.pop("XDG_STATE_HOME", None)
            else:
                os.environ["XDG_STATE_HOME"] = previous
