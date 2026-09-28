from __future__ import annotations

import os
import unittest

os.environ["MAINT_DEMO_DELAY"] = "0"

from gi.repository import GLib

from manutencao_pro.runner import MaintenanceRunner


class RunnerTests(unittest.TestCase):
    def test_demo_stream_is_read_without_blocking(self) -> None:
        loop = GLib.MainLoop()
        lines: list[str] = []
        finished: list[tuple[int, int | None]] = []
        runner = MaintenanceRunner()
        runner.on_line = lines.append

        def on_exit(code: int, term_sig: int | None) -> None:
            finished.append((code, term_sig))
            loop.quit()

        runner.on_exit = on_exit
        runner.start_demo("warnings")
        GLib.timeout_add_seconds(20, loop.quit)
        loop.run()
        self.assertEqual(finished, [(0, None)])
        self.assertTrue(any(line.startswith("@@RESULT nvidia_upstream=newer") for line in lines))
        self.assertTrue(any(line.startswith("@@WARN ") for line in lines))
        self.assertFalse(runner.is_running())
