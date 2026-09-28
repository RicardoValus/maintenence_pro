from __future__ import annotations

import unittest

from manutencao_pro.parser import RebootMarker, ResultMarker, StepMarker, TextLine, WarnMarker, parse_line


class ParserTests(unittest.TestCase):
    def test_step(self) -> None:
        marker = parse_line("@@STEP 2/14 apt-upgrade Fazendo upgrade dos pacotes")
        self.assertEqual(marker, StepMarker(2, 14, "apt-upgrade", "Fazendo upgrade dos pacotes"))

    def test_result_reboot_and_warn(self) -> None:
        self.assertEqual(parse_line("@@RESULT packages=fail"), ResultMarker("packages", "fail"))
        self.assertEqual(parse_line("@@REBOOT kernel atualizado"), RebootMarker("kernel atualizado"))
        self.assertEqual(parse_line("@@WARN falha no apt upgrade"), WarnMarker("falha no apt upgrade"))

    def test_human_line_stays_text(self) -> None:
        marker = parse_line("✅ Tudo OK. Não precisa reiniciar.")
        self.assertEqual(marker, TextLine("✅ Tudo OK. Não precisa reiniciar."))

    def test_broken_marker_stays_text(self) -> None:
        self.assertIsInstance(parse_line("@@STEP incompleto"), TextLine)
