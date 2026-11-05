"""Explicit target bindings enable Antigravity queueing without UI mode hints."""

import os
from unittest import mock

from test_agent_bridge import ab, antigravity_screen, ANTIGRAVITY_BUSY, ANTIGRAVITY_IDLE, fake_clock, make_identity
from test_busy_queue import BusyQueueCase

SETTING = "AGENT_BRIDGE_ANTIGRAVITY_QUEUE_KEY"


class AntigravityCase(BusyQueueCase):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.dict(os.environ))
        os.environ.pop(SETTING, None)
        # Footer text observed in live 1.4.11 captures and the user's 1.5.1 screenshots.
        self.footer = ANTIGRAVITY_BUSY
        self.screen = lambda draft, **kwargs: antigravity_screen(draft, footer=self.footer, **kwargs)


class TestAntigravityQueueConfig(AntigravityCase):

    def test_unset_key_waits_before_pasting_into_busy_antigravity(self):
        with fake_clock(), self.assertRaises(ab.PeerNotReady):
            self.start()
        self.assertEqual(self.typed, [])
        self.assertEqual(self.keys, [])
        self.assertIsNone(ab.load_state(make_identity(self.root, "%1")))

    def test_explicit_enter_queues_without_delivery_hint(self):
        os.environ[SETTING] = "Enter"
        with fake_clock() as elapsed:
            _, result = self.start()
        self.assertLess(elapsed(), 5)
        self.assertEqual(self.keys, ["Enter"])
        self.assertEqual(result["delivery"], "delivered")
        self.assertEqual(len(self.typed), 1)

    def test_explicit_alt_m_queues_without_delivery_hint(self):
        os.environ[SETTING] = "M-m"
        with fake_clock():
            _, result = self.start()
        self.assertEqual(self.keys, ["M-m"])
        self.assertEqual(result["delivery"], "delivered")

    def test_rebound_key_is_sent_literally_instead_of_enter(self):
        os.environ[SETTING] = "C-q"
        with fake_clock():
            self.start()
        self.assertEqual(self.keys, ["C-q"])

    def test_invalid_binding_refuses_before_paste(self):
        os.environ[SETTING] = "alt+m"
        with fake_clock(), self.assertRaisesRegex(ab.PeerNotReady, "invalid AGENT_BRIDGE"):
            self.start()
        self.assertEqual(self.typed, [])
        self.assertEqual(self.keys, [])

    def test_only_documented_single_key_tokens_are_accepted(self):
        for value in ("Enter", "Tab", "M-m", "C-q", "M-Enter"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {SETTING: value}):
                self.assertEqual(ab.antigravity_configured_key(), value)
        for value in ("alt+m", "Enter Tab", "-t", "M-m\nEnter", "C-x C-s"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {SETTING: value}):
                with self.assertRaises(ab.PeerNotReady):
                    ab.antigravity_configured_key()

    def test_finished_task_uses_enter_with_busy_words_in_payload(self):
        os.environ[SETTING] = "M-m"
        self.draft = f"Thinking... esc to cancel (30s timeout) {ab.FRAME_END}"
        self.footer = ANTIGRAVITY_IDLE
        self.assertEqual(ab.antigravity_queue_key(self.capture().stdout), "Enter")

    def test_footer_controls_activity_despite_wrapped_draft(self):
        os.environ[SETTING] = "M-m"
        self.draft = "\n".join(["frame row"] * 20 + [ab.FRAME_END])
        self.assertEqual(ab.antigravity_queue_key(self.capture().stdout), "M-m")

    def test_idle_footer_ignores_busy_wording_quoted_in_transcript(self):
        self.footer = ANTIGRAVITY_IDLE
        self.transcript = lambda: 'The previous reply quoted "esc to cancel".\n'
        with fake_clock():
            _, result = self.start()
        self.assertEqual(self.keys, ["Enter"])
        self.assertEqual(result["delivery"], "delivered")

    def test_missing_footer_does_not_imply_idle(self):
        self.footer = ""
        self.transcript = lambda: "Reading file...\nTip: In /diff, press c to add inline comments.\n"
        with fake_clock(), self.assertRaises(ab.PeerNotReady):
            self.start()
        self.assertEqual(self.typed, [])

    def test_explicit_key_handles_working_state_without_footer(self):
        os.environ[SETTING] = "M-m"
        self.footer = ""
        self.transcript = lambda: "Reading file...\nTip: In /diff, press c to add inline comments.\n"
        with fake_clock():
            self.start()
        self.assertEqual(self.keys, ["M-m"])

    def test_unknown_composer_after_submit_is_uncertain_without_retyping(self):
        os.environ[SETTING] = "M-m"
        self.unreadable_after_submit = True
        with fake_clock(), self.assertRaises(ab.DeliveryUncertain):
            self.start()
        self.assertEqual(self.keys, ["M-m"])
        self.assertEqual(len(self.typed), 1)

    def test_retries_use_configured_key_and_name_it_in_recovery(self):
        os.environ[SETTING] = "C-q"
        self.accept = False
        with fake_clock(), self.assertRaises(ab.DeliveryUncertain):
            self.start()
        self.assertEqual(self.keys, ["C-q"] * 4)
        self.assertEqual(len(self.typed), 1)
        state = ab.load_state(make_identity(self.root, "%1"))
        self.assertIn("press Enter if that agent is idle, or Ctrl+Q (the declared queue key) "
                      "if it is still working", ab.delivery_note(state))

    def test_task_finishing_between_retries_switches_to_enter(self):
        os.environ[SETTING] = "M-m"
        self.accept = False
        original = self.tmux

        def finish(args, **kwargs):
            result = original(args, **kwargs)
            if self.keys:
                self.footer = ANTIGRAVITY_IDLE
                self.accept = True
            return result

        with mock.patch.object(ab, "run_tmux", side_effect=finish), fake_clock():
            self.start()
        self.assertEqual(self.keys, ["M-m", "Enter"])
        self.assertEqual(len(self.typed), 1)

    def test_global_idle_override_disables_configured_busy_delivery(self):
        os.environ[SETTING] = "Enter"
        with mock.patch.object(ab, "BUSY_MODE", "idle"), fake_clock():
            with self.assertRaises(ab.PeerNotReady):
                self.start()
        self.assertEqual(self.typed, [])

    def test_idle_footer_in_payload_does_not_establish_idle(self):
        os.environ[SETTING] = "M-m"
        self.draft = f"? for shortcuts\nalt+m to send immediately {ab.FRAME_END}"
        self.assertEqual(ab.antigravity_queue_key(self.capture().stdout), "M-m")

    def test_task_finishing_after_paste_selects_enter(self):
        os.environ[SETTING] = "M-m"
        original = self.type_frame

        def finish(target, frame):
            original(target, frame)
            self.footer = ANTIGRAVITY_IDLE

        with mock.patch.object(ab, "type_into", side_effect=finish), fake_clock():
            self.start()
        self.assertEqual(self.keys, ["Enter"])

    def test_composer_disappearing_before_submit_gets_no_key(self):
        os.environ[SETTING] = "M-m"
        original = self.capture
        reads = 0

        def capture(*args, **kwargs):
            nonlocal reads
            result = original(*args, **kwargs)
            if self.typed:
                reads += 1
                if reads >= 4:
                    result.stdout = "permission dialog\n"
            return result

        with mock.patch.object(ab, "capture_pane_text", side_effect=capture), fake_clock():
            with self.assertRaises(ab.DeliveryUncertain):
                self.start()
        self.assertEqual(self.keys, [])
        self.assertEqual(len(self.typed), 1)


class TestAntigravityRecoveryKey(AntigravityCase):
    """Recovery text names a real key, and reserved keys never reach the pane."""

    def note(self):
        return ab.delivery_note(ab.load_state(make_identity(self.root, "%1")))

    def test_interrupt_and_suspend_keys_refuse_before_paste(self):
        for value in ("C-c", "C-z"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {SETTING: value}):
                with fake_clock(), self.assertRaisesRegex(ab.PeerNotReady, "reserved"):
                    self.start()
                self.assertEqual(self.typed, [])
                self.assertEqual(self.keys, [])

    def test_other_control_keys_stay_accepted(self):
        for value in ("C-d", "C-q", "C-s"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {SETTING: value}):
                self.assertEqual(ab.antigravity_configured_key(), value)

    def test_unresolved_first_press_names_both_keys(self):
        os.environ[SETTING] = "M-m"
        with mock.patch.object(ab, "antigravity_queue_key", return_value=None), fake_clock():
            with self.assertRaises(ab.DeliveryUncertain) as caught:
                self.start()
        self.assertEqual(self.keys, [])
        self.assertEqual(len(self.typed), 1)
        both = "Enter if that agent is idle, or Alt+M (the declared queue key) if it is still working"
        self.assertIn(both, str(caught.exception))
        self.assertIn(both, self.note())
        self.assertNotIn("press the queue key", self.note())

    def test_unreadable_composer_before_submit_names_both_keys(self):
        os.environ[SETTING] = "M-m"
        original = ab.read_input

        def unreadable_after_paste(target):
            return ab.INPUT_UNKNOWN if self.typed else original(target)

        with mock.patch.object(ab, "read_input", side_effect=unreadable_after_paste), fake_clock():
            with self.assertRaises(ab.DeliveryUncertain) as caught:
                self.start()
        self.assertEqual(self.keys, [])
        self.assertIn("press Enter if that agent is idle, or Alt+M", str(caught.exception))
        self.assertIn("press Enter if that agent is idle, or Alt+M", self.note())

    BOTH_CTRL_Q = "press Enter if that agent is idle, or Ctrl+Q (the declared queue key) if it is still working"

    def test_retry_that_cannot_resolve_reports_last_key_as_history_only(self):
        os.environ[SETTING] = "C-q"
        self.accept = False
        resolved = iter(["C-q"])
        with mock.patch.object(ab, "antigravity_queue_key", side_effect=lambda _: next(resolved, None)), \
                fake_clock():
            with self.assertRaises(ab.DeliveryUncertain) as caught:
                self.start()
        self.assertEqual(self.keys, ["C-q"])
        self.assertIn("The previous attempt pressed Ctrl+Q.", str(caught.exception))
        self.assertIn(self.BOTH_CTRL_Q, str(caught.exception))
        self.assertIn(self.BOTH_CTRL_Q, self.note())
        self.assertNotIn("press Ctrl+Q there", self.note())

    def test_exhausted_retries_name_both_keys(self):
        os.environ[SETTING] = "C-q"
        self.accept = False
        with fake_clock(), self.assertRaises(ab.DeliveryUncertain) as caught:
            self.start()
        self.assertEqual(caught.exception.delivery, "unsent")
        self.assertEqual(self.keys, ["C-q"] * 4)
        self.assertIn(self.BOTH_CTRL_Q, str(caught.exception))
        self.assertIn(self.BOTH_CTRL_Q, self.note())

    def test_unreadable_confirmation_after_resolved_key_names_both_keys(self):
        os.environ[SETTING] = "C-q"
        self.unreadable_after_submit = True
        with fake_clock(), self.assertRaises(ab.DeliveryUncertain) as caught:
            self.start()
        self.assertEqual(caught.exception.delivery, "uncertain")
        self.assertEqual(self.keys, ["C-q"])
        self.assertIn(self.BOTH_CTRL_Q, str(caught.exception))
        self.assertIn(self.BOTH_CTRL_Q, self.note())

    def test_claude_and_codex_keep_their_concrete_key(self):
        self.assertEqual(ab.press_instruction("Tab"), "press Tab there")
        self.assertEqual(ab.press_instruction("Enter"), "press Enter there")

    def test_state_from_bare_plan_still_gives_actionable_text(self):
        self.assertEqual(ab.submit_key_label(ab.ANTIGRAVITY_QUEUE_KEY),
                         "Enter if that agent is idle, or the declared queue key if it is still working")
