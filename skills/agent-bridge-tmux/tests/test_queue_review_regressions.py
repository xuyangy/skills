"""Readiness and queue-key decisions exclude draft content and redundant waits."""

import os
import unittest
from unittest import mock

from test_agent_bridge import ab, antigravity_screen, ANTIGRAVITY_BUSY, claude_screen, codex_screen, fake_clock


class TestQueueReviewRegressions(unittest.TestCase):
    def test_idle_antigravity_submits_body_with_busy_wording(self):
        for wording in ("Thinking...", "Working...", "esc to cancel", "(30s timeout)"):
            with self.subTest(wording=wording):
                screen = antigravity_screen(
                    f"{wording} {ab.FRAME_END}", above="Task finished\n")
                self.assertEqual(ab.antigravity_queue_key(screen), "Enter")

    def test_wrapped_draft_cannot_hide_busy_state(self):
        draft = "\n".join(["wrapped frame row"] * 20 + [ab.FRAME_END])
        for configured, key in (("M-m", "M-m"), ("Enter", "Enter"), ("", None)):
            with self.subTest(configured=configured), mock.patch.dict(
                    os.environ, {"AGENT_BRIDGE_ANTIGRAVITY_QUEUE_KEY": configured}):
                screen = antigravity_screen(draft, above="Working... esc to interrupt\n",
                                            footer=ANTIGRAVITY_BUSY)
                self.assertEqual(ab.antigravity_queue_key(screen), key)

    def test_finished_task_and_busy_payload_use_idle_footer(self):
        screen = antigravity_screen(
            f"Thinking... {ab.FRAME_END}", above="Task finished\n")
        self.assertEqual(ab.antigravity_queue_key(screen), "Enter")

    def test_confirmed_idle_prompt_does_not_spend_remaining_budget_on_queue_probe(self):
        for screen, expected in ((claude_screen(""), None), (codex_screen(""), "Tab"),
                                 (antigravity_screen(""), None)):
            with self.subTest(screen=screen), fake_clock() as elapsed, \
                    mock.patch.dict(os.environ, {"AGENT_BRIDGE_ANTIGRAVITY_QUEUE_KEY": ""}), \
                    mock.patch.object(ab, "INPUT_MODE", "screen"), \
                    mock.patch.object(ab, "BUSY_MODE", "queue"), \
                    mock.patch.object(ab, "SUBMIT_ATTEMPTS", 4), \
                    mock.patch.object(ab, "pane_exists", return_value=True), \
                    mock.patch.object(ab, "capture_target", return_value=screen), \
                    mock.patch.object(ab, "viewer_open", return_value=None), \
                    mock.patch.object(ab, "queue_ready") as probe:
                self.assertEqual(ab.wait_ready("%2", timeout=1.0), expected)
                probe.assert_not_called()
                self.assertAlmostEqual(elapsed(), ab.STABILITY_PAUSE)
