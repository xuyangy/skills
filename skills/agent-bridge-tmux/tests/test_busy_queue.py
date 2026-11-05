"""Queue submissions use an empty composer while transcript output continues."""

import contextlib
import io
import subprocess
import types
from pathlib import Path
from unittest import mock

from test_agent_bridge import (
    TempRoot, ab, claude_screen, codex_screen,
    fake_clock, make_identity,
)


class BusyQueueCase(TempRoot):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(ab, "INPUT_MODE", "screen"))
        self.enterContext(mock.patch.object(ab, "BUSY_MODE", "queue"))
        self.enterContext(mock.patch.object(ab, "SUBMIT_ATTEMPTS", 4))
        self.enterContext(mock.patch.object(ab, "pane_exists", return_value=True))
        self.enterContext(mock.patch.object(ab, "viewer_open", return_value=None))
        self.enterContext(mock.patch.object(ab, "Focus", side_effect=lambda _: contextlib.nullcontext()))
        self.enterContext(mock.patch.object(ab, "tmux_value", return_value="1"))
        self.enterContext(mock.patch.object(ab, "publish_status"))
        self.enterContext(mock.patch.object(ab, "state_root", return_value=self.root))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.draft = ""
        self.typed = []
        self.keys = []
        self.captures = 0
        self.submitted = False
        self.unreadable_after_submit = False
        self.accept = True
        self.screen = codex_screen
        self.enterContext(mock.patch.object(ab, "capture_target", side_effect=lambda _: self.capture().stdout))
        self.enterContext(mock.patch.object(ab, "capture_pane_text", side_effect=self.capture))
        self.enterContext(mock.patch.object(ab, "type_into", side_effect=self.type_frame))
        self.enterContext(mock.patch.object(ab, "run_tmux", side_effect=self.tmux))

    def transcript(self, *args, **kwargs):
        self.captures += 1
        return f"Working... esc to interrupt {self.captures}\n"

    def capture(self, *args, **kwargs):
        above = self.transcript()
        text = ("permission dialog\n" if self.submitted and self.unreadable_after_submit
                else self.screen(self.draft, above=above))
        return subprocess.CompletedProcess([], 0, text)

    def type_frame(self, target, frame):
        self.typed.append(frame)
        self.draft = frame

    def tmux(self, args, **kwargs):
        if args[0] == "send-keys":
            key = args[-1]
            self.keys.append(key)
            if self.accept:
                self.draft = ""
                self.submitted = True
        return subprocess.CompletedProcess(args, 0, "")

    def start(self):
        identity = make_identity(self.root, "%1")
        body = self.root / "body.txt"
        body.write_text("Review this change")
        with mock.patch.object(ab, "detect_identity", return_value=identity):
            result = ab.command_start(types.SimpleNamespace(
                target="%2", max_turns=4, body_file=str(body), goal_phrase=None, fresh=False))
        return identity, result


class TestBusyQueue(BusyQueueCase):
    def test_codex_busy_start_queues_with_tab_and_records_pending(self):
        with fake_clock() as elapsed:
            identity, result = self.start()
        self.assertLess(elapsed(), 5)
        self.assertEqual(self.keys, ["Tab"])
        self.assertEqual(len(self.typed), 1)
        self.assertEqual(result["delivery"], "delivered")
        self.assertEqual(result["acceptance"], "unknown")
        self.assertEqual(ab.load_state(identity)["status"], "pending")

    def test_claude_busy_start_queues_with_enter(self):
        self.screen = claude_screen
        with fake_clock() as elapsed:
            _, result = self.start()
        self.assertLess(elapsed(), 5)
        self.assertEqual(self.keys, ["Enter"])
        self.assertEqual(result["delivery"], "delivered")

    def test_unsubmitted_codex_frame_retries_tab_without_pasting_twice(self):
        self.accept = False
        with fake_clock(), self.assertRaises(ab.DeliveryUncertain) as caught:
            self.start()
        self.assertEqual(caught.exception.delivery, "unsent")
        self.assertEqual(self.keys, ["Tab"] * 4)
        self.assertEqual(len(self.typed), 1)
        identity = make_identity(self.root, "%1")
        state = ab.load_state(identity)
        self.assertEqual(state["status"], "pending")
        self.assertEqual(state["submit_key"], "Tab")
        self.assertIn("press Tab", ab.delivery_note(state))

    def test_unknown_screen_after_queue_submit_is_uncertain(self):
        self.unreadable_after_submit = True
        with fake_clock(), self.assertRaises(ab.DeliveryUncertain) as caught:
            self.start()
        self.assertEqual(caught.exception.delivery, "uncertain")
        self.assertEqual(self.keys, ["Tab"])
        self.assertEqual(len(self.typed), 1)

    def test_input_taken_after_admission_refuses_before_paste(self):
        original = ab.queue_ready

        def ready(*args):
            key = original(*args)
            self.draft = "human draft"
            return key

        with mock.patch.object(ab, "queue_ready", side_effect=ready), fake_clock():
            with self.assertRaises(ab.PeerNotReady):
                self.start()
        self.assertEqual(self.keys, [])
        self.assertEqual(self.typed, [])
        self.assertIsNone(ab.load_state(make_identity(self.root, "%1")))

    def test_supported_input_does_not_need_a_still_transcript(self):
        with fake_clock() as elapsed:
            self.assertEqual(ab.wait_ready("%2", timeout=10), "Tab")
        self.assertLess(elapsed(), 2)
        self.assertGreater(self.captures, 2)

    def test_nonempty_input_is_not_queue_ready(self):
        for draft in ("human draft", f"old {ab.FRAME_END}", "[Pasted text #1 +5 lines]"):
            with self.subTest(draft=draft), fake_clock():
                self.draft = draft
                self.assertIsNone(ab.queue_ready("%2", deadline=10))
        self.assertEqual(self.keys, [])

    def test_unknown_and_unsupported_composers_keep_idle_gate(self):
        # The transcript above keeps changing, so only the idle gate in
        # wait_ready can refuse; deliver's own pre-paste check is never reached.
        screens = {
            "permission dialog": lambda draft, above="", **kw: f"{above}permission dialog\n",
            "shell prompt": lambda draft, above="", **kw: f"{above}$ {draft}\n",
        }
        for name, screen in screens.items():
            with self.subTest(screen=name), fake_clock(), \
                    mock.patch.object(ab, "deliver", side_effect=AssertionError("delivered")):
                self.screen = screen
                with self.assertRaisesRegex(ab.PeerNotReady, "did not reach a confirmed idle prompt"):
                    self.start()
        self.assertEqual(self.typed, [])
        self.assertEqual(self.keys, [])

    def test_tail_idle_override_and_unverified_submit_keep_idle_gate(self):
        for name, value in (("INPUT_MODE", "tail"), ("BUSY_MODE", "idle"), ("SUBMIT_ATTEMPTS", 1)):
            with self.subTest(option=name), mock.patch.object(ab, name, value), fake_clock():
                with self.assertRaises(ab.PeerNotReady):
                    ab.wait_ready("%2", timeout=3)

    def test_open_viewer_cannot_be_admitted_as_an_empty_composer(self):
        with mock.patch.object(ab, "viewer_open", return_value=ab.CODEX_VIEWER), \
                mock.patch.object(ab, "close_viewer", return_value=False), fake_clock():
            with self.assertRaises(ab.PeerNotReady):
                ab.wait_ready("%2", timeout=3)
        self.assertEqual(self.typed, [])

    def test_changing_composer_is_not_queue_ready(self):
        screens = [codex_screen(""), claude_screen("")]
        with mock.patch.object(ab, "capture_pane_text", side_effect=[
                subprocess.CompletedProcess([], 0, screen) for screen in screens]), fake_clock():
            self.assertIsNone(ab.queue_ready("%2", deadline=10))

    def test_slow_capture_cannot_admit_after_deadline(self):
        def slow_capture(*args, **kwargs):
            ab.time.sleep(3)
            return self.capture(*args, **kwargs)

        with mock.patch.object(ab, "capture_pane_text", side_effect=slow_capture), fake_clock():
            with self.assertRaises(ab.PeerNotReady):
                ab.wait_ready("%2", timeout=2)

    def test_paste_settles_while_transcript_keeps_changing(self):
        self.draft = f"frame {ab.FRAME_END}"
        with fake_clock() as elapsed:
            ab.wait_settled("%2")
        self.assertAlmostEqual(elapsed(), ab.SUBMIT_DELAY + ab.SETTLE_PAUSE)

    def test_abort_prevents_queue_admission(self):
        identity = make_identity(self.root, "%1")
        Path(identity["abort_file"]).touch()
        with fake_clock(), self.assertRaisesRegex(ab.BridgeError, "abort"):
            ab.wait_ready("%2", timeout=10, identity=identity)
        self.assertEqual(self.keys, [])

    def test_close_confirmation_uses_ordinary_queued_reply_and_receive(self):
        with fake_clock():
            a, _ = self.start()
            b = make_identity(self.root, "%2")

            def receive(identity, frame, tag):
                source = self.root / f"{tag}.frame"
                source.write_text(frame)
                with mock.patch.object(ab, "detect_identity", return_value=identity):
                    return ab.command_receive(types.SimpleNamespace(
                        frame_file=str(source), body_out=str(self.root / f"{tag}.body")))

            def reply(identity, body, tag):
                source = self.root / f"{tag}.out"
                source.write_text(body)
                with mock.patch.object(ab, "detect_identity", return_value=identity):
                    return ab.command_reply(types.SimpleNamespace(body_file=str(source)))

            receive(b, self.typed[-1], "opening")
            reply(b, "NOTICE: verify me\nBRIDGE CLOSE: requested\nAgreed on the item.", "request")
            receive(a, self.typed[-1], "request")
            result = reply(a, "NOTICE: verify me\nBRIDGE CLOSE: confirmed\nEvidence: agreement checked.", "confirm")
            self.assertEqual(result["delivery"], "delivered")
            confirmation = receive(b, self.typed[-1], "confirm")
        self.assertEqual(self.keys, ["Tab", "Tab", "Tab"])
        self.assertIn("Evidence: agreement checked.", Path(confirmation["decoded_body_file"]).read_text())
        self.assertEqual(confirmation["turn"], 3)
        self.assertEqual(len(self.typed), 3)

    def test_codex_queue_key_remains_tab_if_task_finishes_after_admission(self):
        original_type = self.type_frame

        def type_after_task_finishes(target, frame):
            original_type(target, frame)
            self.transcript = lambda *args, **kwargs: "Worked for 5s\n"

        with mock.patch.object(ab, "type_into", side_effect=type_after_task_finishes), fake_clock():
            _, result = self.start()
        self.assertEqual(self.keys, ["Tab"])
        self.assertEqual(result["delivery"], "delivered")


class TestFirstPasteSettling(BusyQueueCase):
    """The first paste must land in the input box and hold still before submit.

    The transcript changes on every capture, so only the input box can settle.
    """

    def setUp(self):
        super().setUp()
        self.render_after = 0
        self.pasted_at = None
        self.frames = []

    def type_frame(self, target, frame):
        self.typed.append(frame)
        self.pasted_at = self.captures
        self.frames.append(frame)

    def capture(self, *args, **kwargs):
        if (self.pasted_at is not None and not self.submitted and not self.draft
                and self.captures - self.pasted_at >= self.render_after):
            self.draft = self.frames[-1]
        return super().capture(*args, **kwargs)

    def test_delayed_render_waits_past_matching_empty_reads(self):
        self.render_after = 4
        with fake_clock():
            _, result = self.start()
        self.assertEqual(result["delivery"], "delivered")
        self.assertEqual(len(self.typed), 1)
        self.assertEqual(self.keys, ["Tab"])

    def test_frame_that_never_renders_times_out_without_a_key(self):
        self.render_after = 10 ** 9
        with fake_clock() as elapsed, self.assertRaises(ab.DeliveryUncertain) as caught:
            self.start()
        self.assertEqual(caught.exception.delivery, "uncertain")
        self.assertEqual(self.keys, [])
        self.assertEqual(len(self.typed), 1)
        self.assertLess(elapsed(), 60 + ab.SUBMIT_DELAY + ab.SETTLE_TIMEOUT + 2 * ab.SETTLE_PAUSE)
        state = ab.load_state(make_identity(self.root, "%1"))
        self.assertEqual(state["status"], "pending")
        self.assertEqual(state["delivery"], "uncertain")

    def test_timeout_wins_over_a_final_read_that_shows_the_frame(self):
        with mock.patch.object(ab, "wait_frame_settled", return_value=False), fake_clock():
            with self.assertRaises(ab.DeliveryUncertain) as caught:
                self.start()
        self.assertEqual(self.keys, [])
        self.assertIn("did not hold still", str(caught.exception))

    def test_retry_settling_still_sees_an_empty_box_as_submitted(self):
        # The first Tab is not taken, so the first confirmation read still
        # holds the frame. The box then empties inside the real retry
        # wait_settled, as when the TUI submits on its own.
        self.accept = False
        settling = []
        original_settled = ab.wait_settled
        original_capture = self.capture

        def settled(target):
            settling.append(target)
            return original_settled(target)

        def capture(*args, **kwargs):
            if settling and self.draft:
                self.draft = ""
                self.submitted = True
            return original_capture(*args, **kwargs)

        with mock.patch.object(ab, "wait_settled", side_effect=settled), \
                mock.patch.object(ab, "capture_pane_text", side_effect=capture), fake_clock():
            _, result = self.start()
        self.assertEqual(settling, ["%2"])
        self.assertEqual(result["delivery"], "delivered")
        self.assertEqual(self.keys, ["Tab"])


class TestWaitFrameSettled(BusyQueueCase):
    """wait_frame_settled counts only consecutive matching reads of the frame."""

    def scripted(self, drafts):
        reads = iter(drafts)
        last = [drafts[-1]]

        def capture(*args, **kwargs):
            self.draft = next(reads, last[0])
            return BusyQueueCase.capture(self)

        return mock.patch.object(ab, "capture_pane_text", side_effect=capture)

    def test_empty_box_never_settles(self):
        with self.scripted([""]), fake_clock() as elapsed:
            self.assertFalse(ab.wait_frame_settled("%2"))
        self.assertGreaterEqual(elapsed(), ab.SUBMIT_DELAY + ab.SETTLE_TIMEOUT)

    def test_frame_that_disappears_resets_the_match(self):
        frame = f"Review this {ab.FRAME_END}"
        with self.scripted([frame, "", frame, frame]), fake_clock():
            self.assertTrue(ab.wait_frame_settled("%2"))
        # frame, empty (resets), frame, frame: settled on the fourth read.
        self.assertEqual(self.captures, 4)

    def test_frame_that_keeps_flickering_never_settles(self):
        frame = f"Review this {ab.FRAME_END}"
        with self.scripted([frame, ""] * 50), fake_clock():
            self.assertFalse(ab.wait_frame_settled("%2"))

    def test_matching_capture_that_returns_after_the_deadline_is_rejected(self):
        frame = f"Review this {ab.FRAME_END}"
        reads = 0

        def capture(*args, **kwargs):
            nonlocal reads
            reads += 1
            if reads == 2:
                ab.time.sleep(ab.SETTLE_TIMEOUT + 1)
            self.draft = frame
            return BusyQueueCase.capture(self)

        with mock.patch.object(ab, "capture_pane_text", side_effect=capture), fake_clock():
            self.assertFalse(ab.wait_frame_settled("%2"))
        self.assertEqual(reads, 2)
