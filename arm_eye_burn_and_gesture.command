#!/bin/zsh

# Double-click launcher for macOS Finder/Terminal.
# Uploading arm_eye invokes scripts/open_camera_after_upload.py, which starts
# the camera gesture controller after a successful upload.

set -u
setopt null_glob

PROJECT_DIR="${0:A:h}"
PLATFORMIO_BIN="/Users/silverbrick/.platformio/penv/bin/platformio"
CORE_DIR="${PROJECT_DIR}/.platformio-core"
UPLOAD_PORT="/dev/cu.usbserial-110"

print ""
print "arm_eye：烧录固件并启动摄像头手势识别"
print "项目：${PROJECT_DIR}"

if [[ ! -x "${PLATFORMIO_BIN}" ]]; then
    print -u2 "找不到 PlatformIO：${PLATFORMIO_BIN}"
    print -u2 "请先安装 PlatformIO Core。"
    read -k 1 "?按任意键关闭..."
    print ""
    exit 1
fi

if [[ ! -d "${PROJECT_DIR}/src" || ! -f "${PROJECT_DIR}/platformio.ini" ]]; then
    print -u2 "这不是有效的 arm_eye 项目目录。"
    read -k 1 "?按任意键关闭..."
    print ""
    exit 1
fi

if [[ ! -e "${UPLOAD_PORT}" ]]; then
    print -u2 "找不到指定的 ESP32 USB 串口：${UPLOAD_PORT}"
    print -u2 "请连接开发板，或修改启动器中的 UPLOAD_PORT。"
    read -k 1 "?按任意键关闭..."
    print ""
    exit 1
fi

# 重新烧录前释放上一次自动启动的识别客户端所占用的串口。
pid_file="${PROJECT_DIR}/logs/gesture_control.pid"
if [[ -f "${pid_file}" ]]; then
    running_pid="$(<"${pid_file}")"
    if [[ "${running_pid}" == <-> ]] && kill -0 "${running_pid}" 2>/dev/null; then
        print "停止旧的识别进程（PID ${running_pid}）……"
        kill "${running_pid}" 2>/dev/null || true
        sleep 0.5
    fi
fi

print "上传端口：${UPLOAD_PORT}"
print "开始烧录……"
cd "${PROJECT_DIR}"
PLATFORMIO_CORE_DIR="${CORE_DIR}" "${PLATFORMIO_BIN}" run \
    -e esp32dev -t upload --upload-port "${UPLOAD_PORT}"
status=$?

if (( status == 0 )); then
    print ""
    print "烧录成功。上传钩子已启动摄像头手势识别窗口。"
else
    print -u2 ""
    print -u2 "烧录失败（退出码 ${status}），未启动识别程序。"
fi

read -k 1 "?按任意键关闭此窗口..."
print ""
exit ${status}
