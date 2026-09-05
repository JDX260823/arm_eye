# arm_eye

该工程沿用 `/Users/silverbrick/Documents/PlatformIO/Projects/arm` 的 ESP32 四舵机控制程序，并增量加入 MacBook 摄像头手势识别与 USB 串口控制。

- `src/main.cpp`：原主从、按钮、录制/回放逻辑，以及新增的 `S/G/U/D/R` 解析和安全控制仲裁（`D` 为 U 的反动作）。
- GPIO13 按钮：单击录制/停止，双击回放，长按 2 秒将四个关节平滑复位到安全中位。
- `arm_eye_burn_and_gesture.command`：双击即可在 macOS Terminal 中烧录本项目，并自动启动识别程序。
- `arm_eye_burn_and_gesture.app`：标准 macOS 应用包，双击后在 Terminal 中执行同一流程。
- `platformio.ini`：ESP32 Arduino + ESP32Servo 构建配置。
- `gesture_control/gesture_control.py`：macOS 摄像头、MediaPipe Tasks、稳定帧过滤与 PySerial 客户端。
- `web/index.html`：可手动打开的本地摄像头预览页，优先选择 MacBook 内置摄像头。
- `scripts/open_camera_after_upload.py`：PlatformIO 上传完成钩子，自动启动摄像头手势识别客户端。
- `gesture_control/README.md`：安装、权限、运行、烧录、校准和故障排查说明。

请先阅读 [gesture_control/README.md](gesture_control/README.md)。当前 `G` 已写入主臂录制得到的 J3/J4 过程轨迹，并将 J2 固定为 `78°`；`U/R` 仍需继续录制后再写入，首次实机测试应逐项、小范围确认。

## 在线摄像头预览

仓库内置 GitHub Pages 自动发布流程。每次向 `main` 分支推送后，`web/` 目录会自动发布为 HTTPS 静态站点。首次访问时请允许浏览器使用摄像头；页面只在浏览器本地读取视频流，不会上传画面。

## 烧录后自动启动手势识别

执行 `platformio run -e esp32dev -t upload` 成功后，项目会自动使用 `.venv/bin/python` 启动 `gesture_control/gesture_control.py`，打开带识别叠加信息的摄像头窗口，并通过烧录所用串口发送 `S/G/U/D/R` 指令。识别客户端日志写入 `logs/gesture_control.log`。为避免 macOS 摄像头被两个程序抢占，上传钩子不再同时打开网页预览；网页仍可手动启动后访问 <http://127.0.0.1:8765/index.html>。

上传端口已固定为 `/dev/cu.usbserial-110`，写在 `platformio.ini` 和双击启动器中。

也可以直接双击项目根目录中的 `arm_eye_burn_and_gesture.app`（或 `.command`）。首次被 macOS 拦截时，在 Finder 中右键应用并选择“打开”，随后允许 Terminal、Python 和摄像头权限。请保持 `.app`、`.command` 与项目目录一起，不要单独移动应用包。
