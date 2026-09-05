#!/usr/bin/env python3
"""MacBook camera gesture control client for the ESP32 arm.

The state-machine portion of this module deliberately has no third-party
imports.  This keeps it testable on machines where the camera/runtime
dependencies have not been installed yet.  OpenCV, MediaPipe and PySerial are
loaded only by :func:`main`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


GESTURE_CONFIDENCE_THRESHOLD = 0.65
STABLE_FRAMES = 4
NO_HAND_FRAMES_TO_STOP = 10
SERIAL_BAUDRATE = 115200
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

GESTURE_TO_COMMAND = {
    "Open_Palm": "S",
    "Closed_Fist": "G",
    "Pointing_Up": "U",
    "Thumb_Down": "D",
    "Victory": "R",
}

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = SCRIPT_DIR / "models" / "gesture_recognizer.task"


class RuntimeDependencyError(RuntimeError):
    """Raised when an optional runtime dependency is unavailable."""


class CameraInitializationError(RuntimeError):
    """Raised when neither macOS camera-opening strategy succeeds."""


@dataclass(frozen=True, slots=True)
class FilterUpdate:
    """A snapshot returned for every processed video frame."""

    gesture_label: str
    raw_gesture: str | None
    confidence: float
    stable_count: int
    no_hand_frames: int
    emitted_command: str | None
    last_sent_command: str | None


class GestureCommandFilter:
    """Convert noisy per-frame recognition into de-duplicated arm commands."""

    def __init__(
        self,
        confidence_threshold: float = GESTURE_CONFIDENCE_THRESHOLD,
        stable_frames: int = STABLE_FRAMES,
        no_hand_frames_to_stop: int = NO_HAND_FRAMES_TO_STOP,
    ) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if stable_frames < 1:
            raise ValueError("stable_frames must be at least 1")
        if no_hand_frames_to_stop < 1:
            raise ValueError("no_hand_frames_to_stop must be at least 1")

        self.confidence_threshold = confidence_threshold
        self.stable_frames = stable_frames
        self.no_hand_frames_to_stop = no_hand_frames_to_stop
        self.candidate_gesture: str | None = None
        self.stable_count = 0
        self.no_hand_frames = 0
        self.last_sent_command: str | None = None

    def _reset_stability(self) -> None:
        self.candidate_gesture = None
        self.stable_count = 0

    def _emit_if_changed(self, command: str) -> str | None:
        if command == self.last_sent_command:
            return None
        self.last_sent_command = command
        return command

    def update(
        self,
        hand_present: bool,
        gesture_name: str | None = None,
        confidence: float = 0.0,
    ) -> FilterUpdate:
        """Process one frame and return a state snapshot.

        ``hand_present`` must be derived from MediaPipe's hand landmarks, not
        from whether a classified gesture happens to be available.  A hand
        with an unsupported or low-confidence classification therefore resets
        gesture stability but also resets the consecutive no-hand counter.
        """

        score = float(confidence)
        emitted_command: str | None = None

        if not hand_present:
            self.no_hand_frames += 1
            self._reset_stability()
            if self.no_hand_frames >= self.no_hand_frames_to_stop:
                emitted_command = self._emit_if_changed("S")
            return FilterUpdate(
                gesture_label="No Hand",
                raw_gesture=gesture_name,
                confidence=score,
                stable_count=self.stable_count,
                no_hand_frames=self.no_hand_frames,
                emitted_command=emitted_command,
                last_sent_command=self.last_sent_command,
            )

        # Any actual hand breaks a run of no-hand frames, even when its
        # category is unsupported or uncertain.
        self.no_hand_frames = 0
        supported = gesture_name in GESTURE_TO_COMMAND
        confident = score >= self.confidence_threshold

        if not supported or not confident:
            self._reset_stability()
            if gesture_name and gesture_name not in {"None", "Unknown"} and not supported:
                label = f"Ignored ({gesture_name})"
            else:
                label = "Uncertain"
            return FilterUpdate(
                gesture_label=label,
                raw_gesture=gesture_name,
                confidence=score,
                stable_count=self.stable_count,
                no_hand_frames=self.no_hand_frames,
                emitted_command=None,
                last_sent_command=self.last_sent_command,
            )

        if gesture_name == self.candidate_gesture:
            self.stable_count = min(self.stable_count + 1, self.stable_frames)
        else:
            self.candidate_gesture = gesture_name
            self.stable_count = 1

        if self.stable_count >= self.stable_frames:
            emitted_command = self._emit_if_changed(GESTURE_TO_COMMAND[gesture_name])

        return FilterUpdate(
            gesture_label=gesture_name,
            raw_gesture=gesture_name,
            confidence=score,
            stable_count=self.stable_count,
            no_hand_frames=self.no_hand_frames,
            emitted_command=emitted_command,
            last_sent_command=self.last_sent_command,
        )


def observation_from_result(result: Any) -> tuple[bool, str | None, float]:
    """Extract ``(hand_present, gesture, confidence)`` from a Tasks result.

    Hand presence intentionally depends only on non-empty landmark groups.
    Classification output is not used as a proxy for hand detection.
    """

    landmark_groups = getattr(result, "hand_landmarks", None) or []
    hand_present = any(bool(group) for group in landmark_groups)
    if not hand_present:
        return False, None, 0.0

    gesture_groups = getattr(result, "gestures", None) or []
    if not gesture_groups or not gesture_groups[0]:
        return True, None, 0.0

    category = max(
        gesture_groups[0],
        key=lambda item: float(getattr(item, "score", 0.0) or 0.0),
    )
    name = getattr(category, "category_name", None)
    score = float(getattr(category, "score", 0.0) or 0.0)
    return True, name, score


def _load_vision_dependencies() -> tuple[Any, Any]:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeDependencyError(
            "OpenCV is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc

    try:
        import mediapipe as mp  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeDependencyError(
            "MediaPipe is not installed. Use Python 3.11 and run: "
            "python -m pip install -r requirements.txt"
        ) from exc

    try:
        _ = mp.tasks.vision.GestureRecognizer
    except AttributeError as exc:
        raise RuntimeDependencyError(
            "The installed MediaPipe package does not provide the Tasks "
            "GestureRecognizer API. Reinstall the version in requirements.txt."
        ) from exc

    return cv2, mp


def _load_serial_dependencies() -> tuple[Any, Any]:
    try:
        import serial  # type: ignore[import-not-found]
        from serial.tools import list_ports  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeDependencyError(
            "PySerial is not installed. Install requirements.txt or run with --no-serial."
        ) from exc
    return serial, list_ports


def open_camera(cv2: Any, camera_index: int) -> Any:
    """Open a camera with AVFoundation first and the default backend second."""

    capture = None
    avfoundation = getattr(cv2, "CAP_AVFOUNDATION", None)
    if avfoundation is not None:
        try:
            capture = cv2.VideoCapture(camera_index, avfoundation)
        except Exception:
            capture = None
        if capture is not None and capture.isOpened():
            print(f"Camera {camera_index}: using macOS AVFoundation backend.")
        elif capture is not None:
            capture.release()
            capture = None

    if capture is None:
        try:
            capture = cv2.VideoCapture(camera_index)
        except Exception:
            capture = None
        if capture is not None and capture.isOpened():
            print(f"Camera {camera_index}: using OpenCV default backend.")

    if capture is None or not capture.isOpened():
        if capture is not None:
            capture.release()
        raise CameraInitializationError(
            "Camera initialization failed.\n"
            "Please check macOS Camera permission:\n"
            "System Settings -> Privacy & Security -> Camera\n"
            "Allow Camera access for Codex, Terminal, VS Code, or the app that starts Python."
        )

    # Some cameras ignore one or both requests.  That is harmless; processing
    # continues at the closest resolution the device supports.
    for property_id, requested_value in (
        (cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH),
        (cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT),
    ):
        try:
            capture.set(property_id, requested_value)
        except Exception:
            # Resolution negotiation is best effort and must not disable an
            # otherwise usable camera.
            pass
    return capture


_BUILTIN_CAMERA_MARKERS = ("macbook", "built-in", "builtin", "内置")


def camera_index_from_system_profiler(output: str) -> int | None:
    """Map macOS's camera listing to the corresponding AVFoundation index."""

    # system_profiler emits one block per camera, each containing Model ID and
    # Unique ID.  The blocks are listed in the same order AVFoundation exposes
    # devices to OpenCV by index on macOS.
    camera_blocks = [
        block
        for block in output.split("\n\n")
        if "model id:" in block.lower() and "unique id:" in block.lower()
    ]
    for index, block in enumerate(camera_blocks):
        if any(marker in block.lower() for marker in _BUILTIN_CAMERA_MARKERS):
            return index
    return None


def preferred_camera_index() -> int:
    """Prefer the MacBook camera when Continuity Camera is also available."""

    if sys.platform != "darwin":
        return 0

    try:
        probe = subprocess.run(
            ["system_profiler", "SPCameraDataType"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        print("Camera device enumeration unavailable; falling back to AVFoundation index 0.")
        return 0

    selected = camera_index_from_system_profiler(probe.stdout)
    if selected is None:
        print("Built-in MacBook camera not identified; falling back to AVFoundation index 0.")
        return 0

    print(f"Camera selection: MacBook built-in camera at AVFoundation index {selected}.")
    return selected


def create_gesture_recognizer(mp: Any, model_path: Path) -> Any:
    """Create a synchronous, single-hand MediaPipe recognizer in VIDEO mode."""

    vision = mp.tasks.vision
    options = vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=1,
    )
    return vision.GestureRecognizer.create_from_options(options)


_SERIAL_DEVICE_MARKERS = (
    "usbmodem",
    "usbserial",
    "wchusbserial",
    "slab_usbtouart",
)
_SERIAL_METADATA_MARKERS = (
    "esp32",
    "esp 32",
    "espressif",
    "usb serial",
    "usb-to-serial",
    "usb to uart",
    "cp210",
    "ch340",
    "ch341",
    "ch910",
    "silicon labs",
    "ftdi",
)


def _port_search_text(port: Any) -> str:
    values = (
        getattr(port, "device", ""),
        getattr(port, "description", ""),
        getattr(port, "manufacturer", ""),
        getattr(port, "product", ""),
        getattr(port, "interface", ""),
        getattr(port, "hwid", ""),
    )
    return " ".join(str(value or "") for value in values).lower()


def is_obvious_usb_serial_port(port: Any) -> bool:
    """Return whether a port is a plausible macOS ESP32 USB serial device."""

    device = str(getattr(port, "device", "") or "")
    text = _port_search_text(port)
    if not device.startswith("/dev/cu."):
        return False
    if "bluetooth" in text:
        return False
    if getattr(port, "vid", None) is not None and getattr(port, "pid", None) is not None:
        return True
    return any(marker in text for marker in _SERIAL_DEVICE_MARKERS + _SERIAL_METADATA_MARKERS)


def auto_select_serial_port(ports: Sequence[Any]) -> str | None:
    """Select only when the choice is unambiguous enough to be safe."""

    candidates = [port for port in ports if is_obvious_usb_serial_port(port)]
    if len(candidates) == 1:
        return str(candidates[0].device)

    # If several USB serial adapters exist, select a single explicitly labelled
    # Espressif/ESP32 device.  Otherwise require --port instead of guessing.
    labelled_esp32 = [
        port
        for port in candidates
        if any(marker in _port_search_text(port) for marker in ("esp32", "esp 32", "espressif"))
    ]
    if len(labelled_esp32) == 1:
        return str(labelled_esp32[0].device)
    return None


def print_serial_ports(ports: Sequence[Any]) -> None:
    if not ports:
        print("Detected serial ports: none")
        return

    print("Detected serial ports:")
    for port in ports:
        device = str(getattr(port, "device", "unknown"))
        description = str(getattr(port, "description", "") or "unknown device")
        vid = getattr(port, "vid", None)
        pid = getattr(port, "pid", None)
        usb_id = f" [VID:PID {vid:04X}:{pid:04X}]" if vid is not None and pid is not None else ""
        print(f"  {device} - {description}{usb_id}")


class SerialLink:
    """Small failure-tolerant wrapper around a non-blocking PySerial port."""

    def __init__(self, serial_module: Any, port: str) -> None:
        self.serial_module = serial_module
        self.port = port
        self._serial: Any | None = None
        try:
            self._serial = serial_module.Serial(
                port=port,
                baudrate=SERIAL_BAUDRATE,
                timeout=0,
                write_timeout=0.25,
            )
            print(f"Serial connected: {port} at {SERIAL_BAUDRATE} baud")
        except Exception as exc:  # Hardware/driver failures must not stop vision.
            print(f"Serial connection failed for {port}: {exc}", file=sys.stderr)

    @property
    def connected(self) -> bool:
        return self._serial is not None and bool(getattr(self._serial, "is_open", True))

    def _disconnect_after_error(self, action: str, exc: Exception) -> None:
        print(f"Serial {action} failed; continuing with vision only: {exc}", file=sys.stderr)
        serial_port = self._serial
        self._serial = None
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass

    def send(self, command: str) -> bool:
        if not self.connected:
            return False
        try:
            self._serial.write(f"{command}\n".encode("ascii"))
            return True
        except Exception as exc:
            self._disconnect_after_error("write", exc)
            return False

    def drain_input(self) -> None:
        """Non-blockingly discard firmware logs so its RX buffer cannot grow."""

        if not self.connected:
            return
        try:
            waiting = int(getattr(self._serial, "in_waiting", 0) or 0)
            if waiting > 0:
                # timeout=0 makes this read non-blocking.  A generous cap keeps
                # a pathological device from monopolizing a video frame.
                self._serial.read(min(waiting, 65536))
        except Exception as exc:
            self._disconnect_after_error("read", exc)

    def close(self) -> None:
        serial_port = self._serial
        self._serial = None
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception as exc:
                print(f"Serial close warning: {exc}", file=sys.stderr)


def draw_overlay(
    cv2: Any,
    frame: Any,
    update: FilterUpdate,
    serial_status: str,
    port: str,
    fps: float,
) -> None:
    confidence_text = f"{update.confidence:.2f}" if update.raw_gesture else "--"
    command_text = update.last_sent_command or "-"
    lines = (
        f"Gesture: {update.gesture_label}",
        f"Confidence: {confidence_text}",
        f"Stable: {update.stable_count}/{STABLE_FRAMES}",
        f"No hand: {min(update.no_hand_frames, NO_HAND_FRAMES_TO_STOP)}/{NO_HAND_FRAMES_TO_STOP}",
        f"Command: {command_text}",
        f"Serial: {serial_status}",
        f"Port: {port}",
        f"FPS: {fps:.1f}",
        "Q: quit",
    )
    for index, line in enumerate(lines):
        position = (12, 28 + index * 25)
        cv2.putText(frame, line, position, cv2.FONT_HERSHEY_SIMPLEX, 0.57, (0, 0, 0), 3)
        cv2.putText(frame, line, position, cv2.FONT_HERSHEY_SIMPLEX, 0.57, (80, 255, 80), 1)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recognize MacBook camera gestures and control the ESP32 arm."
    )
    parser.add_argument(
        "--model",
        type=Path,
        help=f"Gesture Recognizer .task model (default: {DEFAULT_MODEL_PATH})",
    )
    parser.add_argument("--port", help="Explicit serial port, for example /dev/cu.usbmodem1101")
    parser.add_argument(
        "--no-serial",
        action="store_true",
        help="Run camera recognition without opening or writing a serial port",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=None,
        help="Explicit OpenCV camera index; default auto-selects the MacBook built-in camera",
    )
    return parser


def _resolve_model_path(argument: Path | None) -> Path:
    if argument is None:
        return DEFAULT_MODEL_PATH
    return argument.expanduser().resolve()


def _configure_serial(args: argparse.Namespace) -> tuple[SerialLink | None, str]:
    serial_module, list_ports = _load_serial_dependencies()
    try:
        ports = list(list_ports.comports())
    except Exception as exc:
        print(f"Serial enumeration failed; continuing with vision only: {exc}", file=sys.stderr)
        ports = []
    print_serial_ports(ports)

    selected_port = args.port or auto_select_serial_port(ports)
    if selected_port is None:
        candidates = [str(port.device) for port in ports if is_obvious_usb_serial_port(port)]
        if candidates:
            print(
                "Serial port is ambiguous; not connecting automatically. "
                "Choose one with --port /dev/cu.xxxxx.\nCandidates: " + ", ".join(candidates),
                file=sys.stderr,
            )
        else:
            print(
                "No obvious ESP32 USB serial port found; continuing with vision only. "
                "Connect the board or specify --port /dev/cu.xxxxx.",
                file=sys.stderr,
            )
        return None, "-"

    if args.port:
        print(f"Using requested serial port: {selected_port}")
    else:
        print(f"Auto-selected serial port: {selected_port}")
    return SerialLink(serial_module, selected_port), selected_port


def _run_video_loop(
    cv2: Any,
    mp: Any,
    capture: Any,
    recognizer: Any,
    serial_link: SerialLink | None,
    selected_port: str,
    serial_disabled: bool,
) -> None:
    command_filter = GestureCommandFilter()
    last_timestamp_ms = -1
    previous_frame_time: float | None = None
    smoothed_fps = 0.0

    while True:
        ok, frame = capture.read()
        if not ok or frame is None:
            print("Camera frame read failed; exiting cleanly.", file=sys.stderr)
            return

        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        media_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        timestamp_ms = max(int(time.monotonic() * 1000), last_timestamp_ms + 1)
        last_timestamp_ms = timestamp_ms
        result = recognizer.recognize_for_video(media_image, timestamp_ms)
        hand_present, gesture_name, confidence = observation_from_result(result)
        update = command_filter.update(hand_present, gesture_name, confidence)

        if update.emitted_command is not None:
            command = update.emitted_command
            if serial_disabled:
                print(f"Command ready (serial disabled): {command}")
            elif serial_link is not None and serial_link.send(command):
                print(f"Sent command: {command}")
            else:
                print(f"Command ready but serial is disconnected: {command}")

        # The existing firmware reports joint state roughly every 100 ms.  Its
        # output is deliberately drained without blocking on every video frame.
        if serial_link is not None:
            serial_link.drain_input()

        now = time.perf_counter()
        if previous_frame_time is not None and now > previous_frame_time:
            instantaneous_fps = 1.0 / (now - previous_frame_time)
            smoothed_fps = (
                instantaneous_fps if smoothed_fps == 0.0 else 0.9 * smoothed_fps + 0.1 * instantaneous_fps
            )
        previous_frame_time = now

        if serial_disabled:
            serial_status = "Disabled (--no-serial)"
        elif serial_link is not None and serial_link.connected:
            serial_status = "Connected"
        else:
            serial_status = "Disconnected"
        draw_overlay(cv2, frame, update, serial_status, selected_port, smoothed_fps)
        cv2.imshow("ESP32 Arm Gesture Control", frame)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q")):
            print("Q pressed; exiting.")
            return


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)
    if args.no_serial and args.port:
        parser.error("--port cannot be combined with --no-serial")

    model_path = _resolve_model_path(args.model)
    if not model_path.is_file():
        print(
            "Gesture Recognizer model not found:\n"
            f"  {model_path}\n"
            "Place the official MediaPipe gesture_recognizer.task at that path "
            "or pass --model /path/to/gesture_recognizer.task.\n"
            "The model is not downloaded automatically.",
            file=sys.stderr,
        )
        return 2

    try:
        cv2, mp = _load_vision_dependencies()
    except RuntimeDependencyError as exc:
        print(f"Dependency error: {exc}", file=sys.stderr)
        return 2

    serial_link: SerialLink | None = None
    selected_port = "-"
    capture = None
    recognizer = None

    try:
        if args.no_serial:
            print("Serial disabled: vision-only mode.")
        else:
            try:
                serial_link, selected_port = _configure_serial(args)
            except RuntimeDependencyError as exc:
                print(f"Dependency error: {exc}", file=sys.stderr)
                return 2

        try:
            recognizer = create_gesture_recognizer(mp, model_path)
        except Exception as exc:
            print(
                "MediaPipe Gesture Recognizer initialization failed. "
                "Verify that --model points to the official compatible .task file.\n"
                f"Details: {exc}",
                file=sys.stderr,
            )
            return 2

        camera_index = args.camera_index if args.camera_index is not None else preferred_camera_index()
        try:
            capture = open_camera(cv2, camera_index)
        except CameraInitializationError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        try:
            _run_video_loop(
                cv2,
                mp,
                capture,
                recognizer,
                serial_link,
                selected_port,
                args.no_serial,
            )
        except KeyboardInterrupt:
            print("\nCtrl+C received; exiting cleanly.")
        return 0
    finally:
        if capture is not None:
            capture.release()
        if recognizer is not None:
            try:
                recognizer.close()
            except Exception as exc:
                print(f"MediaPipe close warning: {exc}", file=sys.stderr)
        if serial_link is not None:
            serial_link.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
