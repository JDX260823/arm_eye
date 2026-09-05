from __future__ import annotations

import unittest
from types import SimpleNamespace

from gesture_control.gesture_control import (
    GESTURE_CONFIDENCE_THRESHOLD,
    GestureCommandFilter,
    SerialLink,
    auto_select_serial_port,
    camera_index_from_system_profiler,
    is_obvious_usb_serial_port,
    observation_from_result,
)


class GestureCommandFilterTests(unittest.TestCase):
    def test_requires_four_consecutive_frames_and_deduplicates(self) -> None:
        state = GestureCommandFilter()

        for expected_count in (1, 2, 3):
            update = state.update(True, "Closed_Fist", 0.90)
            self.assertEqual(update.stable_count, expected_count)
            self.assertIsNone(update.emitted_command)

        update = state.update(True, "Closed_Fist", 0.90)
        self.assertEqual(update.stable_count, 4)
        self.assertEqual(update.emitted_command, "G")

        for _ in range(8):
            update = state.update(True, "Closed_Fist", 0.99)
            self.assertIsNone(update.emitted_command)
            self.assertEqual(update.stable_count, 4)

    def test_a_changed_gesture_restarts_stability(self) -> None:
        state = GestureCommandFilter()
        for _ in range(3):
            state.update(True, "Closed_Fist", 0.9)

        first_victory = state.update(True, "Victory", 0.9)
        self.assertEqual(first_victory.stable_count, 1)
        self.assertIsNone(first_victory.emitted_command)

        state.update(True, "Victory", 0.9)
        state.update(True, "Victory", 0.9)
        confirmed = state.update(True, "Victory", 0.9)
        self.assertEqual(confirmed.emitted_command, "R")

    def test_threshold_is_inclusive_and_mapping_is_exact(self) -> None:
        expected = {
            "Open_Palm": "S",
            "Closed_Fist": "G",
            "Pointing_Up": "U",
            "Thumb_Down": "D",
            "Victory": "R",
        }
        for gesture, command in expected.items():
            with self.subTest(gesture=gesture):
                state = GestureCommandFilter()
                for _ in range(3):
                    self.assertIsNone(
                        state.update(True, gesture, GESTURE_CONFIDENCE_THRESHOLD).emitted_command
                    )
                self.assertEqual(
                    state.update(True, gesture, GESTURE_CONFIDENCE_THRESHOLD).emitted_command,
                    command,
                )

    def test_low_confidence_resets_stability_but_is_not_no_hand(self) -> None:
        state = GestureCommandFilter()
        for _ in range(3):
            state.update(True, "Pointing_Up", 0.95)

        uncertain = state.update(True, "Pointing_Up", 0.649)
        self.assertEqual(uncertain.gesture_label, "Uncertain")
        self.assertEqual(uncertain.stable_count, 0)
        self.assertEqual(uncertain.no_hand_frames, 0)

        for _ in range(3):
            self.assertIsNone(state.update(True, "Pointing_Up", 0.95).emitted_command)
        self.assertEqual(state.update(True, "Pointing_Up", 0.95).emitted_command, "U")

    def test_unsupported_gesture_breaks_a_no_hand_run(self) -> None:
        state = GestureCommandFilter()
        for _ in range(9):
            state.update(False)

        ignored = state.update(True, "Thumb_Up", 0.99)
        self.assertEqual(ignored.gesture_label, "Ignored (Thumb_Up)")
        self.assertEqual(ignored.no_hand_frames, 0)
        self.assertIsNone(ignored.emitted_command)

        for _ in range(9):
            self.assertIsNone(state.update(False).emitted_command)
        self.assertEqual(state.update(False).emitted_command, "S")

    def test_ten_no_hand_frames_emit_one_stop(self) -> None:
        state = GestureCommandFilter()
        for expected_count in range(1, 10):
            update = state.update(False)
            self.assertEqual(update.no_hand_frames, expected_count)
            self.assertIsNone(update.emitted_command)

        stopped = state.update(False)
        self.assertEqual(stopped.emitted_command, "S")
        for _ in range(20):
            self.assertIsNone(state.update(False).emitted_command)

    def test_same_command_is_not_resent_after_uncertain_frames(self) -> None:
        state = GestureCommandFilter()
        for _ in range(4):
            first = state.update(True, "Closed_Fist", 0.9)
        self.assertEqual(first.emitted_command, "G")

        state.update(True, None, 0.0)
        for _ in range(4):
            repeated = state.update(True, "Closed_Fist", 0.9)
        self.assertIsNone(repeated.emitted_command)


class ResultObservationTests(unittest.TestCase):
    def test_empty_landmarks_mean_no_hand_even_if_category_exists(self) -> None:
        category = SimpleNamespace(category_name="Victory", score=0.99)
        result = SimpleNamespace(hand_landmarks=[], gestures=[[category]])
        self.assertEqual(observation_from_result(result), (False, None, 0.0))

    def test_landmarks_mean_hand_even_without_a_category(self) -> None:
        result = SimpleNamespace(hand_landmarks=[[object()]], gestures=[])
        self.assertEqual(observation_from_result(result), (True, None, 0.0))

    def test_highest_scoring_category_is_used(self) -> None:
        categories = [
            SimpleNamespace(category_name="Victory", score=0.6),
            SimpleNamespace(category_name="Open_Palm", score=0.8),
        ]
        result = SimpleNamespace(hand_landmarks=[[object()]], gestures=[categories])
        self.assertEqual(observation_from_result(result), (True, "Open_Palm", 0.8))


class SerialSelectionTests(unittest.TestCase):
    @staticmethod
    def port(device: str, **values: object) -> SimpleNamespace:
        defaults = {
            "description": "",
            "manufacturer": "",
            "product": "",
            "interface": "",
            "hwid": "",
            "vid": None,
            "pid": None,
        }
        defaults.update(values)
        return SimpleNamespace(device=device, **defaults)

    def test_selects_one_ch340_and_ignores_bluetooth(self) -> None:
        ch340 = self.port(
            "/dev/cu.usbserial-110",
            description="USB Serial",
            product="CH340",
            vid=0x1A86,
            pid=0x7523,
        )
        bluetooth = self.port(
            "/dev/cu.Bluetooth-Incoming-Port",
            description="Bluetooth-Incoming-Port",
        )
        self.assertTrue(is_obvious_usb_serial_port(ch340))
        self.assertFalse(is_obvious_usb_serial_port(bluetooth))
        self.assertEqual(auto_select_serial_port([bluetooth, ch340]), ch340.device)

    def test_multiple_generic_usb_ports_are_ambiguous(self) -> None:
        first = self.port("/dev/cu.usbserial-1", vid=1, pid=1)
        second = self.port("/dev/cu.usbmodem-2", vid=2, pid=2)
        self.assertIsNone(auto_select_serial_port([first, second]))

    def test_single_labelled_esp32_wins_among_usb_candidates(self) -> None:
        generic = self.port("/dev/cu.usbserial-1", vid=1, pid=1)
        esp32 = self.port(
            "/dev/cu.usbmodem-2",
            description="Espressif ESP32 USB JTAG/serial debug unit",
            vid=0x303A,
            pid=0x1001,
        )
        self.assertEqual(auto_select_serial_port([generic, esp32]), esp32.device)


class SerialLinkTests(unittest.TestCase):
    def test_writes_newline_and_drains_firmware_output(self) -> None:
        class FakePort:
            is_open = True
            in_waiting = 12

            def __init__(self) -> None:
                self.writes: list[bytes] = []
                self.read_sizes: list[int] = []
                self.closed = False

            def write(self, value: bytes) -> None:
                self.writes.append(value)

            def read(self, size: int) -> bytes:
                self.read_sizes.append(size)
                return b"x" * size

            def close(self) -> None:
                self.closed = True

        fake_port = FakePort()
        serial_module = SimpleNamespace(Serial=lambda **_: fake_port)
        link = SerialLink(serial_module, "/dev/cu.usbserial-test")

        self.assertTrue(link.send("G"))
        link.drain_input()
        link.close()

        self.assertEqual(fake_port.writes, [b"G\n"])
        self.assertEqual(fake_port.read_sizes, [12])
        self.assertTrue(fake_port.closed)


class CameraSelectionTests(unittest.TestCase):
    def test_prefers_macbook_block_over_iphone_continuity_camera(self) -> None:
        profiler_output = """Camera:

    MacBook Air相机:

      Model ID: MacBook Air相机
      Unique ID: builtin-id

    “Silver Brick”的相机:

      Model ID: iPhone18,1
      Unique ID: iphone-id
"""
        self.assertEqual(camera_index_from_system_profiler(profiler_output), 0)

    def test_selects_builtin_when_iphone_is_listed_first(self) -> None:
        profiler_output = """Camera:

    Continuity Camera:

      Model ID: iPhone18,1
      Unique ID: iphone-id

    MacBook Pro Camera:

      Model ID: MacBook Pro Camera
      Unique ID: builtin-id
"""
        self.assertEqual(camera_index_from_system_profiler(profiler_output), 1)

    def test_returns_none_when_no_builtin_camera_is_reported(self) -> None:
        profiler_output = """Camera:

    Continuity Camera:

      Model ID: iPhone18,1
      Unique ID: iphone-id
"""
        self.assertIsNone(camera_index_from_system_profiler(profiler_output))


if __name__ == "__main__":
    unittest.main()
