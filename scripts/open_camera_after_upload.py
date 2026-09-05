"""Start the arm_eye gesture controller after a successful firmware upload.

The recognizer owns the camera and displays its annotated OpenCV window. The
browser preview is intentionally not opened here: opening two camera clients
at the same time is unreliable on macOS and can prevent MediaPipe from seeing
frames.
"""

from pathlib import Path
import os
import subprocess
import time

Import("env")

PROJECT_ROOT = Path(env.subst("$PROJECT_DIR"))
GESTURE_DIR = PROJECT_ROOT / "gesture_control"
GESTURE_SCRIPT = GESTURE_DIR / "gesture_control.py"
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "gesture_control.log"
PID_FILE = LOG_DIR / "gesture_control.pid"


def log(message: str) -> None:
    line = f"[arm_eye gesture] {message}"
    print(line)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
    except OSError:
        # Logging must never turn a successful firmware upload into a failure.
        pass


def process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def existing_controller_pid() -> int | None:
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if process_is_running(pid) else None


def upload_port(upload_env) -> str | None:
    """Return the port used by PlatformIO, if it is known after uploading."""
    try:
        value = upload_env.get("UPLOAD_PORT")
    except AttributeError:
        value = None
    if value is None:
        try:
            value = upload_env.subst("$UPLOAD_PORT")
        except Exception:
            value = None
    port = str(value or "").strip()
    if not port or port.startswith("$") or port.lower() == "none":
        return None
    return port


def start_gesture_controller(upload_env) -> None:
    if not GESTURE_SCRIPT.is_file():
        raise FileNotFoundError(f"识别程序不存在: {GESTURE_SCRIPT}")
    if not PYTHON.is_file():
        raise FileNotFoundError(
            f"Python 虚拟环境不存在: {PYTHON}，请先安装 gesture_control/requirements.txt"
        )

    old_pid = existing_controller_pid()
    if old_pid is not None:
        log(f"识别程序已在运行 (PID {old_pid})，不重复启动")
        return

    command = [str(PYTHON), str(GESTURE_SCRIPT)]
    port = upload_port(upload_env)
    if port:
        command.extend(["--port", port])
        log(f"使用烧录串口启动识别: {port}")
    else:
        log("未读取到烧录串口，启动识别程序自动选择 USB 串口")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    output = LOG_FILE.open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(GESTURE_DIR),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    finally:
        output.close()

    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    log(f"已启动摄像头手势识别 (PID {process.pid})，窗口标题为 ESP32 Arm Gesture Control")


def after_upload(source, target, env):
    try:
        start_gesture_controller(env)
    except Exception as exc:  # noqa: BLE001 - report failure without hiding upload result
        log(f"自动启动手势识别失败: {exc}")


env.AddPostAction("upload", after_upload)
