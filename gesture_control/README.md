# macOS 摄像头手势控制 ESP32 机械臂

该目录为原 `arm` PlatformIO 工程增加电脑端视觉控制。它使用 MacBook 摄像头、OpenCV、MediaPipe Tasks `GestureRecognizer` 和 PySerial，把稳定手势转换为 `S/G/U/D/R\n`。原有主从控制、实体按钮、录制与回放逻辑仍保留在 `src/main.cpp`。

## 当前环境与版本

本机已检查：

```text
Architecture: arm64
Python:       3.11.7
PlatformIO:   6.1.19
MediaPipe:    0.10.35
PySerial:     3.5
```

MediaPipe 0.10.35 会同时安装其要求的 `opencv-contrib-python`；因此本机 `cv2.__version__` 为 `5.0.0`。程序只使用常规 OpenCV API。

## 1. 创建独立 Python 环境

从项目根目录运行：

```bash
uname -m
python3 --version
which python3

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r gesture_control/requirements.txt
```

不要把视觉依赖安装进全局 Python 或 PlatformIO 的 Python 环境。验证安装：

```bash
python -c "import cv2, mediapipe, serial; print(cv2.__version__, mediapipe.__version__, serial.VERSION)"
python -m pip check
```

## 2. 模型文件

程序默认从脚本相对路径读取：

```text
gesture_control/models/gesture_recognizer.task
```

仓库中已放入官方 float16 模型，大小为 `8,373,440` 字节。若文件缺失，可从 [MediaPipe 官方模型地址](https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task)重新下载：

```bash
curl -L --fail \
  -o gesture_control/models/gesture_recognizer.task \
  https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task
```

校验：

```bash
shasum -a 256 gesture_control/models/gesture_recognizer.task
```

预期 SHA-256：

```text
97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482
```

也可用 `--model /path/to/gesture_recognizer.task` 指定其他官方兼容模型。程序不会静默下载或使用写死的绝对路径。

## 3. macOS 摄像头权限

程序先用 `system_profiler SPCameraDataType` 读取设备顺序，优先选择名称或 Model ID 包含 `MacBook`、`Built-in` 或 `内置` 的摄像头；这样连接 iPhone Continuity Camera 时也不会主动选手机。然后对选中的 AVFoundation index 尝试：

```python
cv2.VideoCapture(selected_camera_index, cv2.CAP_AVFOUNDATION)
```

失败后会回退到 OpenCV 默认后端。两者都失败时会明确退出，不会静默运行。

可检查 macOS 设备顺序：

```bash
system_profiler SPCameraDataType
```

如需手动覆盖选择，可传 `--camera-index N`；默认行为始终优先尝试 MacBook 内置摄像头。

在 macOS 中打开：

```text
System Settings
→ Privacy & Security
→ Camera
```

允许实际启动 Python 的应用访问摄像头，例如 Codex、Terminal 或 Visual Studio Code。首次授权后可能需要完全退出并重新打开该应用。程序请求 `640 × 480`；摄像头不接受精确设置时仍会继续使用实际分辨率。

MediaPipe 的 macOS 视觉图需要正常的图形会话。若在严格隔离或纯 headless shell 中看到 Metal/NSGL 初始化错误，请从已获摄像头权限的桌面 Terminal、Codex 或 VS Code 运行。

## 4. 手势与安全过滤

| 手势 | 串口 | 含义 |
|---|---:|---|
| `Open_Palm` | `S` | 待机：J4 调整到最大安全角度，其他关节保持 |
| `Closed_Fist` | `G` | Grab |
| `Pointing_Up` | `U` | J3 从当前位置逆时针转 15° |
| `Thumb_Down` | `D` | U 的反动作：J3 顺时针转 15° |
| `Victory` | `R` | Rotate |

过滤规则：

- 只接受置信度 `>= 0.65` 的五种手势。
- 同一有效手势必须连续出现 4 帧才确认。
- 相同命令只发送一次；手势变化并再次稳定后才发送新命令。
- 连续 10 帧没有检测到手部 landmarks 时，只发送一次 `S`。
- 检测到手但分类低置信度或属于 `Thumb_Up`、`ILoveYou`、`None` 等类别时，不发动作命令，并重置稳定计数。
- MediaPipe 使用同步 `VIDEO` 模式和单手跟踪，避免不必要的异步复杂度。

窗口叠加手势、置信度、稳定帧、无手帧、命令、串口状态、端口和 FPS。按 `Q` 退出；`Ctrl+C` 也会释放摄像头、MediaPipe、窗口与串口。

## 5. 先运行纯视觉模式

从项目根目录：

```bash
source .venv/bin/activate
cd gesture_control
python gesture_control.py --no-serial
```

该模式会完整运行摄像头、识别、稳定判断和画面叠加，但不会枚举、打开或写入串口。终端会打印准备发送的命令。

## 6. 查看与选择 macOS 串口

```bash
source .venv/bin/activate
python -m serial.tools.list_ports -v
ls /dev/cu.*
```

ESP32/USB 转串口通常类似：

```text
/dev/cu.usbserial-xxxx
/dev/cu.wchusbserialxxxx
/dev/cu.usbmodemxxxx
```

程序会打印全部端口，并只在选择足够明确时自动连接 ESP32、CH340/CH341、CP210x、FTDI 或 USB Serial 设备。多个候选设备无法可靠区分时，它会继续视觉识别并要求使用 `--port`，不会随便连接蓝牙或其他串口。

本次检查曾发现 CH340（VID:PID `1A86:7523`）端口 `/dev/cu.usbserial-110`，但最终复查时设备已不在枚举结果中，因此当前没有可确认的自动选择端口。

## 7. 运行串口控制

自动检测：

```bash
source .venv/bin/activate
cd gesture_control
python gesture_control.py
```

明确指定端口：

```bash
python gesture_control.py --port /dev/cu.usbserial-110
```

文档形式的占位示例：

```bash
python gesture_control.py --port /dev/cu.xxxxx
```

串口为 `115200 8N1`，命令是单字符 ASCII 加换行：`S\n`、`G\n`、`U\n`、`R\n`。串口连接或写入失败时，程序会切换为仅视觉状态而不崩溃。客户端会非阻塞清空 ESP32 每 100 ms 输出的关节日志，避免输入缓冲无限增长。

## 8. ESP32 固件构建与串口解析验证

从项目根目录构建：

```bash
platformio run -e esp32dev
```

当前构建已通过。烧录会复位 ESP32，并使现有固件在 `setup()` 中把四轴写到 90°。烧录前必须先断开舵机动力电源或把机械臂置于确认安全的位置：

```bash
platformio run -e esp32dev -t upload --upload-port /dev/cu.usbserial-110
platformio device monitor --baud 115200 --port /dev/cu.usbserial-110
```

首次实机测试应逐项发送：

```text
G
U
R
S
```

串口应看到：

```text
Received command: G
（随后按录制轨迹逐帧驱动 J3/J4，J2 固定为 78°）
```

`S` 具有安全优先级：可中断录制或回放，将 J4 调整到标定的最大安全角度，并保持其他关节最后一次已安全写出的角度。`G/U/R` 不会在录制或回放期间打断原逻辑。实体示教按钮开始录制或回放时会退出手势保持模式，恢复原有主从控制。

## 9. G/U/R 动作角校准与过程轨迹

本次 G 动作使用主臂录制期间串口输出的连续 `Current` 采样生成轨迹，J2 按确认值固定为 78°，播放时 J4 轨迹整体下调 5°：

```cpp
constexpr int FIXED_J2_ANGLE = 78;
// G_GRAB_TRAJECTORY[]：G 的 J3/J4 逐帧过程数据
constexpr bool GESTURE_ACTIONS_CALIBRATED = true;
```

G 的过程轨迹已写入 `src/gesture_trajectories.h`；U、R 仍需按同样流程录制后再写入。编译期和运行时仍会限制在原工程安全范围内；首次实机测试必须逐轴确认机械方向、夹爪开合方向和限位：

| 轴 | 功能 | 原安全范围 | 手势 |
|---|---|---:|---|
| J1 | Base | 30°–150° | `R` |
| J2 | Shoulder | 60°–160° | 固定 78° |
| J3 | Elbow | 60°–160° | `G`、`U` |
| J4 | Gripper | 60°–160° | `G` |

推荐校准方法：在原主从模式下缓慢移动主臂到所需动作位置，从串口日志记录对应 `Current` 角度；先断开负载或抬空机械臂，逐轴、小范围验证，再填入常量。四个 MG90S 应使用足额独立 5V 舵机电源，并与 ESP32 共地；不要由 ESP32 3.3V 或仅靠 USB 给四个舵机供电。

原工程中 J3/J4 的 ADC 标定仍是 `0..4095` 占位值，也应在最终机械联调前校准。

## 10. 完整机械臂控制启动顺序

正常烧录 `arm_eye` 后，上传完成钩子会自动启动带摄像头窗口的识别客户端，并把本次烧录使用的 USB 串口传给客户端。若只想手动启动或调试，可按下列步骤执行：

GPIO13 示教按钮仍支持单击录制/停止、双击回放；长按 2 秒会取消当前动作并将四个关节平滑复位到安全中位。

1. 先用 `--no-serial` 验证五种手势、0.65 阈值、4 帧稳定和 10 帧无手停止。
2. 保持机械臂悬空或断开舵机动力电源，先发送 `S` 确认串口链路。
3. 确认独立舵机电源、共地、限位空间和断电手段。
4. 运行 `python gesture_control.py --port /dev/cu.xxxxx`，先测 `S`，再逐项测试 `G`、`U`、`R`。

## 11. 常见故障

- `Camera initialization failed`：在 macOS Camera 设置中给实际启动 Python 的应用授权，然后重启该应用。
- `Gesture Recognizer model not found`：确认模型位于 `models/gesture_recognizer.task`，或传入 `--model`。
- `MediaPipe ... initialization failed`：确认使用 Python 3.11、官方 `.task` 文件，并在正常 macOS 图形会话中运行。
- `No obvious ESP32 USB serial port found`：检查 USB 数据线、CH340/CP210x 驱动和 `python -m serial.tools.list_ports -v` 输出；可明确传 `--port /dev/cu.*`。
- `Serial port is ambiguous`：同时存在多个 USB 串口；必须用 `--port` 指定。
- 串口打开后 ESP32 重启：许多 USB-UART 适配器会因 DTR/RTS 变化复位，这是常见行为；先确保 90° 上电姿态安全。
- 看见 `Received command` 但舵机不动：确认动作角开关为 `true`、当前处于 `NORMAL` 而非录制/回放，并检查舵机动力电源。
- 看不见 `Received command`：确认固件已烧录、两端均为 115200、选用 `/dev/cu.*` 而不是 Windows `COM*`。

## 自动化检查

```bash
source .venv/bin/activate
python -m unittest discover -s gesture_control/tests -v
python -m py_compile gesture_control/gesture_control.py
platformio run -e esp32dev
```
