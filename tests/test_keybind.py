from __future__ import annotations

import unittest

from manutencao_pro.keybind import CANDIDATES, choose_binding, normalize


class KeybindTests(unittest.TestCase):
    def test_suggested_binding_when_free(self) -> None:
        self.assertEqual(choose_binding(set()), CANDIDATES[0])

    def test_does_not_pick_a_used_binding(self) -> None:
        used = {"<Control><Alt>m", "<Primary><Alt>comma"}
        chosen = choose_binding(used)
        self.assertEqual(chosen, "<Ctrl><Alt>period")
        self.assertNotIn(normalize(chosen or ""), {normalize(item) for item in used})

    def test_none_when_every_candidate_is_taken(self) -> None:
        self.assertIsNone(choose_binding(set(CANDIDATES)))
