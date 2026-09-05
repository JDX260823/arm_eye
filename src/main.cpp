#include <Arduino.h>
#include <ESP32Servo.h>

#include "gesture_trajectories.h"

constexpr uint8_t AXIS_COUNT = 4;

// J1：GPIO34/GPIO18；J2：GPIO35/GPIO5；J3：GPIO32/GPIO17；J4：GPIO33/GPIO16。
const uint8_t potPins[AXIS_COUNT] = {34, 35, 32, 33};
const uint8_t servoPins[AXIS_COUNT] = {18, 5, 17, 16};
const char *axisNames[AXIS_COUNT] = {"J1", "J2", "J3", "J4"};

// 三针示教按钮模块使用 GPIO13：VCC -> 3.3V，OUT -> GPIO13，GND -> GND。
// 实测该模块未按下为 LOW、按下为 HIGH，因此使用高电平作为按下状态。
constexpr uint8_t BUTTON_PIN = 13;
constexpr uint8_t BUTTON_PRESSED_LEVEL = HIGH;

// 某个关节方向相反时，把对应位置改为 true。
const bool reversed[AXIS_COUNT] = {true, true, true, true};

// 主臂安全机械行程对应的 ADC 标定值（来自 arm_sync_calibration.log）。
const int adcMin[AXIS_COUNT] = {1100, 1470, 0, 0};
const int adcMax[AXIS_COUNT] = {4095, 3875, 4095, 4095};
constexpr int J1_ADC_CENTER = 2104;
constexpr int J1_ANGLE_OFFSET = -15;
constexpr int J1_GAIN_NUMERATOR = 3;
constexpr int J1_GAIN_DENOMINATOR = 2;
constexpr int J2_ANGLE_OFFSET = -45;
constexpr int angleMin[AXIS_COUNT] = {30, 60, 60, 60};
constexpr int angleCenter[AXIS_COUNT] = {90, 90, 90, 90};
constexpr int angleMax[AXIS_COUNT] = {150, 160, 160, 160};
constexpr int ANGLE_DEADBAND = 2;
constexpr int MAX_STEP_PER_LOOP = 2;
constexpr uint8_t ADC_SAMPLE_COUNT = 8;
constexpr uint16_t CONTROL_INTERVAL_MS = 20;
constexpr uint16_t SERIAL_INTERVAL_MS = 100;
constexpr uint16_t MOTION_FRAME_INTERVAL_MS = 50;
constexpr uint16_t BUTTON_DEBOUNCE_MS = 20;
constexpr uint16_t DOUBLE_CLICK_INTERVAL_MS = 400;
constexpr uint16_t LONG_PRESS_DURATION_MS = 2000;
constexpr size_t MAX_FRAMES = 600;

// 以下动作角取自主臂示教时串口记录的稳定结束角度。
// G（抓取）仅播放 J4 轨迹；U（抬升）：J3=60°；R：J1=30°。
constexpr int BASE_ROTATE_ANGLE = 30;
constexpr int ELBOW_LIFT_ANGLE = 60;
constexpr int GRIPPER_CLOSE_ANGLE = 60;
// G 抓取轨迹的 J4 目标整体下调 5°；运行时仍受 J4 安全范围限制。
constexpr int G_GRIPPER_ANGLE_OFFSET = -5;
// U 让 J3 从收到指令时的当前位置逆时针转 15°。
constexpr int U_J3_ANGLE_DELTA = -15;
// D（Thumb_Down）执行 U 的反动作：J3 顺时针转 15°。
constexpr int D_J3_ANGLE_DELTA = 15;
constexpr int FIXED_J2_ANGLE = 78;
constexpr bool GESTURE_ACTIONS_CALIBRATED = true;
constexpr uint16_t GESTURE_SEQUENCE_INTERVAL_MS = 100;

static_assert(
    BASE_ROTATE_ANGLE >= angleMin[0] && BASE_ROTATE_ANGLE <= angleMax[0],
    "BASE_ROTATE_ANGLE must stay inside the calibrated J1 range");
static_assert(
    ELBOW_LIFT_ANGLE >= angleMin[2] && ELBOW_LIFT_ANGLE <= angleMax[2],
    "ELBOW_LIFT_ANGLE must stay inside the calibrated J3 range");
static_assert(
    FIXED_J2_ANGLE >= angleMin[1] && FIXED_J2_ANGLE <= angleMax[1],
    "FIXED_J2_ANGLE must stay inside the calibrated J2 range");
static_assert(
    GRIPPER_CLOSE_ANGLE >= angleMin[3] &&
        GRIPPER_CLOSE_ANGLE <= angleMax[3],
    "GRIPPER_CLOSE_ANGLE must stay inside the calibrated J4 range");

enum RobotState//机器人状态
{
    NORMAL,
    RECORDING,
    PLAYING
};

enum ControlSource
{
    MASTER_SLAVE_CONTROL,
    GESTURE_HOLD_CONTROL
};

enum GestureSequence
{
    NO_GESTURE_SEQUENCE,
    GRAB_GESTURE_SEQUENCE
};

struct MotionFrame//录制的机器角度
{
    int base;
    int shoulder;
    int elbow;
    int gripper;
};

Servo servos[AXIS_COUNT];//创建4个舵机对象
int currentAngles[AXIS_COUNT] = {90, 90, 90, 90};//创建数组保存当前角度
int adcValues[AXIS_COUNT] = {0, 0, 0, 0};//保存当前电位
int targetAngles[AXIS_COUNT] = {90, 90, 90, 90};//目标角度
int gestureTargetAngles[AXIS_COUNT] = {90, 90, 90, 90};
MotionFrame recordedMotion[MAX_FRAMES];//记录录制的动作状态

RobotState state = NORMAL;//初始状态
ControlSource controlSource = MASTER_SLAVE_CONTROL;
GestureSequence activeGestureSequence = NO_GESTURE_SEQUENCE;
size_t gestureFrameIndex = 0;
unsigned long lastGestureFrameTime = 0;
bool lockJ2AtFixedAngle = false;
size_t frameCount = 0;//已录制帧数
size_t playbackIndex = 0;//播放时的当前帧帧位置
unsigned long lastControlTime = 0;//主从控制时间
unsigned long lastSerialTime = 0;
unsigned long lastRecordTime = 0;
unsigned long lastPlaybackTime = 0;

bool lastRawButtonState = LOW;
bool stableButtonState = LOW;
bool ignoreCurrentButtonPress = false;
bool singleClickPending = false;
bool longPressHandled = false;
bool ignoreLongPress = false;
unsigned long lastButtonChangeTime = 0;
unsigned long firstClickReleaseTime = 0;
unsigned long buttonPressStartTime = 0;

//平均采样，减小抖动
int readPotAverage(uint8_t pin)
{
    uint32_t sum = 0;

    for (uint8_t i = 0; i < ADC_SAMPLE_COUNT; i++)
    {
        sum += analogRead(pin);
    }

    return sum / ADC_SAMPLE_COUNT;
}

void selectMasterSlaveControl()
{
    controlSource = MASTER_SLAVE_CONTROL;
    lastControlTime = millis();
}

void startRecording()
{
    // 实体按钮开始录制时恢复原有主从控制。
    selectMasterSlaveControl();
    frameCount = 0;
    lastRecordTime = millis();//记录开始录制的时刻与esp32启动时刻的时间差
    state = RECORDING;
    Serial.println("Start Recording");
}

void stopRecording()
{
    state = NORMAL;
    Serial.println("Stop Recording");
    Serial.printf("Frames: %u\n", static_cast<unsigned int>(frameCount));
}

void recordFrame()
{
    const unsigned long now = millis();//记录停止录制的时刻距离esp32启动时刻的时间差
    if (now - lastRecordTime < MOTION_FRAME_INTERVAL_MS)//相减获得录制的时间长度
    {
        return;
    }
    lastRecordTime = now;

    if (frameCount >= MAX_FRAMES)//如果录制数组已满，直接返回
    {
        return;
    }

    // currentAngles 是经过映射、限位和步进平滑后实际写给舵机的安全角度。
    recordedMotion[frameCount] = {
        currentAngles[0],
        currentAngles[1],
        currentAngles[2],
        currentAngles[3]};
    frameCount++;

    if (frameCount == MAX_FRAMES)//录制容量达到600帧，自动退出录制状态
    {
        state = NORMAL;
        Serial.println("Recording Full");
        Serial.printf("Frames: %u\n", static_cast<unsigned int>(frameCount));
    }
}

void startPlayback()
{
    if (frameCount == 0)
    {
        Serial.println("No Recorded Motion");
        return;
    }

    // 实体按钮开始回放时退出手势保持模式，保留原回放行为。
    selectMasterSlaveControl();
    playbackIndex = 0;
    // 让第 0 帧在下一次 updatePlayback() 时立即输出。
    lastPlaybackTime = millis() - MOTION_FRAME_INTERVAL_MS;
    state = PLAYING;
    Serial.println("Start Playback");
}

void updatePlayback()
{
    const unsigned long now = millis();
    if (now - lastPlaybackTime < MOTION_FRAME_INTERVAL_MS)//检查距离上个回放帧是否不足50ms
    {
        return;
    }
    lastPlaybackTime = now;

    if (playbackIndex >= frameCount)
    {
        state = NORMAL;
        lastControlTime = now;
        Serial.println("Playback Finished");
        return;
    }

    const MotionFrame &frame = recordedMotion[playbackIndex];
    currentAngles[0] = frame.base;
    currentAngles[1] = frame.shoulder;
    currentAngles[2] = frame.elbow;
    currentAngles[3] = frame.gripper;

    for (uint8_t i = 0; i < AXIS_COUNT; i++)
    {
        servos[i].write(currentAngles[i]);
    }
    playbackIndex++;
}

void enterGestureHoldControl()
{
    if (controlSource != GESTURE_HOLD_CONTROL)
    {
        for (uint8_t i = 0; i < AXIS_COUNT; i++)
        {
            gestureTargetAngles[i] = currentAngles[i];
        }
    }

    controlSource = GESTURE_HOLD_CONTROL;
    lastControlTime = millis();
}

void stopGestureSequence()
{
    activeGestureSequence = NO_GESTURE_SEQUENCE;
    gestureFrameIndex = 0;
}

void beginGestureAction()
{
    enterGestureHoldControl();
    lockJ2AtFixedAngle = true;
    gestureTargetAngles[1] = constrain(
        FIXED_J2_ANGLE, angleMin[1], angleMax[1]);
}

bool gestureActionsAreReady()
{
    if (GESTURE_ACTIONS_CALIBRATED)
    {
        return true;
    }

    Serial.println(
        "Gesture action disabled: calibrate BASE_ROTATE_ANGLE, "
        "ELBOW_LIFT_ANGLE and GRIPPER_CLOSE_ANGLE, then set "
        "GESTURE_ACTIONS_CALIBRATED=true");
    return false;
}

void stopArm()
{
    if (state == RECORDING)
    {
        stopRecording();
    }
    else if (state == PLAYING)
    {
        state = NORMAL;
        Serial.println("Playback Stopped");
    }

    // S 是安全优先命令：取消尚未确认的按键单击，并忽略正在进行的按压。
    singleClickPending = false;
    if (lastRawButtonState == BUTTON_PRESSED_LEVEL ||
        stableButtonState == BUTTON_PRESSED_LEVEL)
    {
        ignoreCurrentButtonPress = true;
    }

    stopGestureSequence();
    lockJ2AtFixedAngle = false;
    enterGestureHoldControl();
    for (uint8_t i = 0; i < AXIS_COUNT; i++)
    {
        // 除 J4 外保持最后一次已经安全写出的角度，不产生新的跳变。
        gestureTargetAngles[i] = currentAngles[i];
    }
    // S：将 J4 缓慢调整到已标定的最大安全角度，作为松开/待机动作。
    gestureTargetAngles[3] = angleMax[3];
    Serial.printf("Gesture standby: moving J4 to max angle %d\n", angleMax[3]);
}

void resetArmPose()
{
    if (state == RECORDING)
    {
        stopRecording();
    }
    else if (state == PLAYING)
    {
        state = NORMAL;
        Serial.println("Playback stopped for reset");
    }

    stopGestureSequence();
    lockJ2AtFixedAngle = false;
    singleClickPending = false;
    enterGestureHoldControl();
    for (uint8_t i = 0; i < AXIS_COUNT; i++)
    {
        // 复位到上电时的安全中位，仍通过 updateGestureHoldControl 逐步移动。
        gestureTargetAngles[i] = angleCenter[i];
    }
    Serial.println("Long press reset: moving all joints to center");
}

void grab()
{
    if (!gestureActionsAreReady())
    {
        return;
    }

    beginGestureAction();
    // G 只驱动 J4；收到握拳指令后，J3 保持当时的实际角度。
    gestureTargetAngles[2] = currentAngles[2];
    activeGestureSequence = GRAB_GESTURE_SEQUENCE;
    gestureFrameIndex = 0;
    lastGestureFrameTime = millis() - GESTURE_SEQUENCE_INTERVAL_MS;
}

void liftArm()
{
    if (!gestureActionsAreReady())
    {
        return;
    }

    stopGestureSequence();
    beginGestureAction();
    // U 仅控制 J3：相对收到指令时的当前位置逆时针转 15°，其他关节保持原目标。
    gestureTargetAngles[2] = constrain(
        currentAngles[2] + U_J3_ANGLE_DELTA, angleMin[2], angleMax[2]);
}

void reverseLiftArm()
{
    if (!gestureActionsAreReady())
    {
        return;
    }

    stopGestureSequence();
    beginGestureAction();
    // D 仅控制 J3：执行 U 的反动作，其他关节保持原目标。
    gestureTargetAngles[2] = constrain(
        currentAngles[2] + D_J3_ANGLE_DELTA, angleMin[2], angleMax[2]);
}

void rotateArm()
{
    if (!gestureActionsAreReady())
    {
        return;
    }

    stopGestureSequence();
    beginGestureAction();
    // R 仅控制 J1，其他关节保持原目标。
    gestureTargetAngles[0] = constrain(
        BASE_ROTATE_ANGLE, angleMin[0], angleMax[0]);
}

void executeGestureCommand(char command)
{
    if (command == 'S')
    {
        stopArm();
        return;
    }

    // 动作命令不打断录制或回放；只有安全停止 S 可以随时打断。
    if (state != NORMAL)
    {
        Serial.println("Gesture action ignored while recording or playing");
        return;
    }

    switch (command)
    {
    case 'G':
        grab();
        break;
    case 'U':
        liftArm();
        break;
    case 'D':
        reverseLiftArm();
        break;
    case 'R':
        rotateArm();
        break;
    default:
        break;
    }
}

void handleSerialCommand()
{
    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == '\r' || command == '\n')
        {
            continue;
        }

        if (command != 'S' && command != 'G' &&
            command != 'U' && command != 'D' && command != 'R')
        {
            continue;
        }

        Serial.printf("Received command: %c\n", command);
        executeGestureCommand(command);
    }
}

void updateGestureHoldControl()
{
    const unsigned long now = millis();
    if (now - lastControlTime < CONTROL_INTERVAL_MS)
    {
        return;
    }
    lastControlTime = now;

    if (activeGestureSequence == GRAB_GESTURE_SEQUENCE &&
        now - lastGestureFrameTime >= GESTURE_SEQUENCE_INTERVAL_MS)
    {
        lastGestureFrameTime = now;
        if (gestureFrameIndex < G_GRAB_TRAJECTORY_LENGTH)
        {
            const GestureTrajectoryFrame &frame =
                G_GRAB_TRAJECTORY[gestureFrameIndex];
            gestureTargetAngles[3] = static_cast<int>(frame.j4) +
                                     G_GRIPPER_ANGLE_OFFSET;
            gestureFrameIndex++;
        }
        else
        {
            stopGestureSequence();
            Serial.println("Gesture G trajectory finished");
        }
    }

    if (lockJ2AtFixedAngle)
    {
        gestureTargetAngles[1] = constrain(
            FIXED_J2_ANGLE, angleMin[1], angleMax[1]);
    }

    for (uint8_t i = 0; i < AXIS_COUNT; i++)
    {
        // 即使将来修改动作常量，运行时仍再次限制在原机械安全范围内。
        gestureTargetAngles[i] = constrain(
            gestureTargetAngles[i], angleMin[i], angleMax[i]);
        const int difference = gestureTargetAngles[i] - currentAngles[i];
        if (difference != 0)
        {
            currentAngles[i] += constrain(
                difference,
                -MAX_STEP_PER_LOOP,
                MAX_STEP_PER_LOOP);
            servos[i].write(currentAngles[i]);
        }
    }
}

void handleSingleClick()
{
    Serial.println("Single Click");

    if (state == NORMAL)
    {
        startRecording();
    }
    else if (state == RECORDING)
    {
        stopRecording();
    }
}

void handleDoubleClick()
{
    Serial.println("Double Click");

    // 双击只在正常主从状态下启动回放。
    if (state == NORMAL)
    {
        startPlayback();
    }
}

void updateButton()
{
    const unsigned long now = millis();
    const bool rawButtonState = digitalRead(BUTTON_PIN);

    if (rawButtonState != lastRawButtonState)
    {
        lastRawButtonState = rawButtonState;
        lastButtonChangeTime = now;
    }

    if (rawButtonState == BUTTON_PRESSED_LEVEL &&
        stableButtonState == BUTTON_PRESSED_LEVEL &&
        !longPressHandled && !ignoreLongPress &&
        now - buttonPressStartTime >= LONG_PRESS_DURATION_MS)
    {
        longPressHandled = true;
        singleClickPending = false;
        // 松开时忽略这次按键，避免长按复位后又被当成单击。
        ignoreCurrentButtonPress = true;
        resetArmPose();
        return;
    }

    if (now - lastButtonChangeTime < BUTTON_DEBOUNCE_MS ||
        rawButtonState == stableButtonState)
    {
        return;
    }

    stableButtonState = rawButtonState;
    if (stableButtonState == BUTTON_PRESSED_LEVEL)
    {
        buttonPressStartTime = now;
        longPressHandled = false;
        // 若按键是在播放期间按下，松开后也整次忽略，避免状态混乱。
        ignoreCurrentButtonPress = (state == PLAYING);
        return;
    }

    if (ignoreCurrentButtonPress)
    {
        ignoreCurrentButtonPress = false;
        ignoreLongPress = false;
        longPressHandled = false;
        return;
    }

    if (longPressHandled)
    {
        longPressHandled = false;
        ignoreLongPress = false;
        return;
    }

    // 录制时不需要等待双击窗口，单击松开后立即停止录制。
    if (state == RECORDING)
    {
        singleClickPending = false;
        handleSingleClick();
        return;
    }

    if (state != NORMAL)
    {
        return;
    }

    if (singleClickPending)
    {
        singleClickPending = false;
        handleDoubleClick();
    }
    else
    {
        singleClickPending = true;
        firstClickReleaseTime = now;
    }
}

void updatePendingClick()
{
    if (!singleClickPending)
    {
        return;
    }

    const unsigned long now = millis();
    const bool buttonIsBeingPressed =
        (lastRawButtonState == BUTTON_PRESSED_LEVEL) ||
        (stableButtonState == BUTTON_PRESSED_LEVEL);

    // 第二击已经开始时，等待它松开后再判定为双击。
    if (buttonIsBeingPressed ||
        now - firstClickReleaseTime < DOUBLE_CLICK_INTERVAL_MS)
    {
        return;
    }

    singleClickPending = false;
    handleSingleClick();
}

void updateMasterSlaveControl()
{
    const unsigned long now = millis();
    if (now - lastControlTime < CONTROL_INTERVAL_MS)
    {
        return;
    }
    lastControlTime = now;

    // 以下 ADC 映射、限位和舵机步进控制保留原有逻辑。
    for (uint8_t i = 0; i < AXIS_COUNT; i++)
    {
        adcValues[i] = readPotAverage(potPins[i]);

        const int outputMin = reversed[i] ? angleMax[i] : angleMin[i];
        const int outputMax = reversed[i] ? angleMin[i] : angleMax[i];
        const int calibratedAdc = constrain(adcValues[i], adcMin[i], adcMax[i]);
        if (i == 0)
        {
            targetAngles[i] = calibratedAdc <= J1_ADC_CENTER
                                  ? map(calibratedAdc, adcMin[i], J1_ADC_CENTER,
                                        outputMin, angleCenter[i])
                                  : map(calibratedAdc, J1_ADC_CENTER, adcMax[i],
                                        angleCenter[i], outputMax);
        }
        else
        {
            targetAngles[i] = map(
                calibratedAdc, adcMin[i], adcMax[i], outputMin, outputMax);
        }
        if (i == 0)
        {
            targetAngles[i] = angleCenter[i] +
                              (targetAngles[i] - angleCenter[i]) *
                                  J1_GAIN_NUMERATOR / J1_GAIN_DENOMINATOR;
            targetAngles[i] += J1_ANGLE_OFFSET;
        }
        else if (i == 1)
        {
            targetAngles[i] += J2_ANGLE_OFFSET;
        }
        targetAngles[i] = constrain(targetAngles[i], angleMin[i], angleMax[i]);

        const int difference = targetAngles[i] - currentAngles[i];

        const int deadband = (i == 0) ? 1 : ANGLE_DEADBAND;
        if (abs(difference) >= deadband)
        {
            // 每个控制周期最多移动 2°，避免关节突然快速运动。
            currentAngles[i] += constrain(
                difference,
                -MAX_STEP_PER_LOOP,
                MAX_STEP_PER_LOOP);
            servos[i].write(currentAngles[i]);
        }
    }

    if (now - lastSerialTime >= SERIAL_INTERVAL_MS)
    {
        lastSerialTime = now;
        for (uint8_t i = 0; i < AXIS_COUNT; i++)
        {
            Serial.printf(
                "%s: ADC=%4d Target=%3d Current=%3d  ",
                axisNames[i],
                adcValues[i],
                targetAngles[i],
                currentAngles[i]);
        }
        Serial.println();
    }
}

void setup()
{
    Serial.begin(115200);
    analogReadResolution(12);
    // 三针模块的 OUT 已有确定电平，不再使用裸按钮所需的内部上拉。
    pinMode(BUTTON_PIN, INPUT);
    lastRawButtonState = digitalRead(BUTTON_PIN);
    stableButtonState = lastRawButtonState;
    lastButtonChangeTime = millis();
    // 如果上电时正按着按钮，忽略这一次，等松开后再正常识别。
    ignoreCurrentButtonPress =
        (stableButtonState == BUTTON_PRESSED_LEVEL);
    ignoreLongPress = ignoreCurrentButtonPress;
    buttonPressStartTime = millis();
    for (uint8_t i = 0; i < AXIS_COUNT; i++)
    {
        pinMode(potPins[i], INPUT);
        servos[i].setPeriodHertz(50);
        servos[i].attach(servoPins[i], 500, 2400);

        // 三个关节上电都先回到机械中位。
        currentAngles[i] = angleCenter[i];
        targetAngles[i] = angleCenter[i];
        gestureTargetAngles[i] = angleCenter[i];
        servos[i].write(angleCenter[i]);
    }

    delay(1000);

    Serial.println("J1 + J2 + J3 joint test ready");
    Serial.println("J1: Pot GPIO34, Servo GPIO18");
    Serial.println("J2: Pot GPIO35, Servo GPIO5");
    Serial.println("J3: Pot GPIO32, Servo GPIO17");
    Serial.println("J4: Pot GPIO33, Servo GPIO16");
    Serial.println("Teach button module: VCC=3.3V, OUT=GPIO13, GND=GND");
    Serial.println("Single click: Record/Stop, Double click: Playback, Long press 2s: Reset pose");
    Serial.println("Serial gestures: S=Standby, G=Grab, U=Lift, D=Reverse Lift, R=Rotate");
    if (!GESTURE_ACTIONS_CALIBRATED)
    {
        Serial.println("Gesture G/U/R actions are disabled until angle calibration");
    }
    Serial.println("System Ready");
}

void loop()
{
    updateButton();
    updatePendingClick();
    handleSerialCommand();

    if (state == PLAYING)
    {
        updatePlayback();
    }
    else if (controlSource == GESTURE_HOLD_CONTROL)
    {
        updateGestureHoldControl();
    }
    else
    {
        updateMasterSlaveControl();

        if (state == RECORDING)
        {
            recordFrame();
        }
    }
}
