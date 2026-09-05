import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

import { buildSlide01 } from "/Users/silverbrick/.codex/plugins/cache/openai-primary-runtime/presentations/26.819.11345/skills/presentations/assets/builtin_templates/codex-grid-layout-library/artifact-tool-compose/slide-01.mjs";
import { buildSlide05 } from "/Users/silverbrick/.codex/plugins/cache/openai-primary-runtime/presentations/26.819.11345/skills/presentations/assets/builtin_templates/codex-grid-layout-library/artifact-tool-compose/slide-05.mjs";
import { buildSlide13 } from "/Users/silverbrick/.codex/plugins/cache/openai-primary-runtime/presentations/26.819.11345/skills/presentations/assets/builtin_templates/codex-grid-layout-library/artifact-tool-compose/slide-13.mjs";
import { buildSlide15 } from "/Users/silverbrick/.codex/plugins/cache/openai-primary-runtime/presentations/26.819.11345/skills/presentations/assets/builtin_templates/codex-grid-layout-library/artifact-tool-compose/slide-15.mjs";
import { buildSlide19 } from "/Users/silverbrick/.codex/plugins/cache/openai-primary-runtime/presentations/26.819.11345/skills/presentations/assets/builtin_templates/codex-grid-layout-library/artifact-tool-compose/slide-19.mjs";
import { buildSlide26 } from "/Users/silverbrick/.codex/plugins/cache/openai-primary-runtime/presentations/26.819.11345/skills/presentations/assets/builtin_templates/codex-grid-layout-library/artifact-tool-compose/slide-26.mjs";

const TMP_DIR = process.env.TMP_DIR;
const FINAL_PPTX = process.env.FINAL_PPTX;

if (!TMP_DIR || !FINAL_PPTX) {
  throw new Error("TMP_DIR and FINAL_PPTX are required");
}

const FONT = "Helvetica Neue";
const BLACK = "#000000";
const BLUE = "#3D8DFF";
const MUTED = "#5F6368";

function run(text, fontSize = 21.33, { bold = false, color = BLACK } = {}) {
  return {
    runs: [{ run: text, textStyle: { fontSize: `${fontSize}px`, typeface: FONT, color, bold } }],
    paragraphStyle: { lineSpacingPercent: 112000 },
  };
}

function pair(title, body, titleSize = 28, bodySize = 19.5) {
  return {
    titleHere: { ...run(title, titleSize, { bold: true, color: BLUE }), spaceAfter: 650 },
    loremIpsumDolorSitAmetConsecteturAdipiscing: run(body, bodySize, { color: MUTED }),
  };
}

function gridPair(title, body) {
  return {
    titleGoesHere: { ...run(title, 26, { bold: true, color: BLUE }), spaceAfter: 500 },
    loremIpsumDolorSitAmetConsecteturAdipiscing: run(body, 18.5, { color: MUTED }),
  };
}

function sectionTitle(text) {
  return run(text, 38.67, { bold: true });
}

function slideNum(n) {
  return run(String(n).padStart(2, "0"), 13.33, { color: MUTED });
}

function addAccent(slide, label) {
  const bar = slide.shapes.add({
    geometry: "roundRect",
    name: `accent-${label}`,
    position: { left: 41.33, top: 154, width: 78, height: 8 },
    fill: BLUE,
    line: { style: "solid", fill: BLUE, width: 0 },
  });
  bar.altText = "章节强调色条";
}

function addNotes(slide, talk, sources) {
  const notes = `${talk}\n\n[Sources]\n${sources.map((s) => `- ${s}`).join("\n")}`;
  slide.speakerNotes.textFrame.setText(notes);
  slide.speakerNotes.setVisible(true);
}

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  await fs.mkdir(TMP_DIR, { recursive: true });
  await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });

  const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });

  // 1. Cover
  {
    const slide = buildSlide01(deck, {
      title: run("PROJECT DEFENSE · 10 MIN", 20, { bold: true, color: BLUE }),
      title2: {
        runs: [
          { run: "视觉手势驱动的\n", textStyle: { fontSize: "58px", typeface: FONT, color: BLACK, bold: true } },
          { run: "四自由度机械臂控制系统", textStyle: { fontSize: "58px", typeface: FONT, color: BLACK, bold: true } },
        ],
        paragraphStyle: { lineSpacingPercent: 92000 },
      },
      title3: {
        runs: [
          { run: "arm 与 arm_eye 项目答辩\n", textStyle: { fontSize: "25px", typeface: FONT, color: MUTED } },
          { run: "答辩人：________    2026年8月", textStyle: { fontSize: "21px", typeface: FONT, color: MUTED } },
        ],
        paragraphStyle: { lineSpacingPercent: 125000 },
      },
    });
    addNotes(slide,
      "大家好，我汇报的题目是《视觉手势驱动的四自由度机械臂控制系统》。项目由 arm 基础控制程序和 arm_eye 视觉控制扩展组成。接下来我将从项目演进、系统实现、安全机制和测试结果四个方面进行说明。建议用时：35秒。",
      ["/Users/silverbrick/Documents/ChatGPT/arm_eye/src/main.cpp", "/Users/silverbrick/Documents/PlatformIO/Projects/arm/src/main.cpp"]);
  }

  // 2. Evolution
  {
    const slide = buildSlide05(deck, {
      title: sectionTitle("01  从示教复现到自然交互"),
      body1: {
        titleHere: { ...run("arm｜基础控制", 30, { bold: true, color: BLUE }), spaceAfter: 700 },
        loremIpsumDolorSitAmetConsecteturAdipiscing: run("电位器实时映射四个舵机\n\n按钮完成动作录制与回放\n\n解决“机械臂如何稳定运动”", 20, { color: MUTED }),
      },
      body2: {
        titleHere: { ...run("arm_eye｜视觉扩展", 30, { bold: true, color: BLUE }), spaceAfter: 700 },
        loremIpsumDolorSitAmetConsecteturAdipiscing: run("电脑摄像头识别手势\n\n串口发送动作指令给 ESP32\n\n解决“人如何更自然地控制机械臂”", 20, { color: MUTED }),
      },
      footer1: slideNum(2),
    });
    addAccent(slide, "evolution");
    addNotes(slide,
      "这两个项目是继承关系。arm 首先完成四轴安全控制、动作录制和回放；arm_eye 不改动 arm，而是在其可靠控制基础上增加视觉识别和串口命令层。核心变化是把输入方式从机械电位器扩展成自然手势。建议用时：55秒。",
      ["/Users/silverbrick/Documents/PlatformIO/Projects/arm/src/main.cpp", "/Users/silverbrick/Documents/ChatGPT/arm_eye/gesture_control/README.md"]);
  }

  // 3. arm baseline
  {
    const slide = buildSlide13(deck, {
      title: sectionTitle("02  arm 项目：建立可靠的四轴控制底座"),
      body1: gridPair("四关节同步", "J1–J4 分别读取电位器，并驱动对应舵机。"),
      body2: gridPair("安全角度", "J1：30–150°；J2/J3/J4：60–160°。"),
      body3: gridPair("示教录制", "GPIO13 单击开始或停止，保存完整运动过程。"),
      body4: gridPair("动作回放", "双击按钮按记录帧顺序复现机械臂动作。"),
      footer1: slideNum(3),
    });
    addAccent(slide, "arm");
    addNotes(slide,
      "arm 项目的价值是先把底层控制做稳。四个关节分别采集电位器信号并驱动舵机；每个关节都有安全角度限制。按钮支持录制和回放，而且记录的是完整过程，不只是起止角度，因此能保留动作轨迹。建议用时：60秒。",
      ["/Users/silverbrick/Documents/PlatformIO/Projects/arm/src/main.cpp:13", "/Users/silverbrick/Documents/PlatformIO/Projects/arm/src/main.cpp:27"]);
  }

  // 4. Architecture
  {
    const slide = buildSlide15(deck, {
      title: sectionTitle("03  arm_eye：构建“看见—判断—执行”闭环"),
      body1: {
        titleHere: { ...run("控制链路", 30, { bold: true, color: BLUE }), spaceAfter: 700 },
        loremIpsumDolorSitAmetConsecteturAdipiscing: run("MacBook 摄像头\n→ MediaPipe\n→ 串口命令\n→ ESP32\n→ 四轴机械臂", 23, { color: MUTED }),
        quamUtMassaLuctusCursusNullamPharetra: run("识别与执行解耦，便于独立调试。", 18, { color: MUTED }),
      },
      label1: run("01 采集", 23, { bold: true, color: BLUE }),
      body2: run("OpenCV 读取电脑摄像头画面", 19.5, { color: MUTED }),
      label2: run("02 识别", 23, { bold: true, color: BLUE }),
      body3: run("MediaPipe GestureRecognizer 输出类别与置信度", 19.5, { color: MUTED }),
      label3: run("03 通信", 23, { bold: true, color: BLUE }),
      body4: run("PySerial 将单字符命令发送到固定端口", 19.5, { color: MUTED }),
      label4: run("04 执行", 23, { bold: true, color: BLUE }),
      body5: run("ESP32 将指令转换为安全、平滑的舵机运动", 19.5, { color: MUTED }),
      footer1: slideNum(4),
    });
    addAccent(slide, "architecture");
    addNotes(slide,
      "arm_eye 形成了一条完整链路：电脑摄像头负责采集，MediaPipe 输出手势类别和置信度，Python 程序经过稳定性判断后发送单字符命令，ESP32 再执行对应的关节动作。识别与固件分层，问题可以在摄像头、串口或舵机任一层单独定位。建议用时：65秒。",
      ["/Users/silverbrick/Documents/ChatGPT/arm_eye/gesture_control/gesture_control.py", "/Users/silverbrick/Documents/ChatGPT/arm_eye/src/main.cpp"]);
  }

  // 5. Hardware mapping
  {
    const slide = buildSlide13(deck, {
      title: sectionTitle("04  硬件映射与关节校准"),
      body1: gridPair("J1｜底座旋转", "电位器 GPIO34 · 舵机 GPIO18\n安全范围 30–150°"),
      body2: gridPair("J2｜姿态稳定", "电位器 GPIO35 · 舵机 GPIO5\nG 动作中固定为 78°"),
      body3: gridPair("J3｜抬升关节", "电位器 GPIO32 · 舵机 GPIO17\n安全范围 60–160°"),
      body4: gridPair("J4｜末端夹爪", "电位器 GPIO33 · 舵机 GPIO16\n安全范围 60–160°"),
      footer1: slideNum(5),
    });
    addAccent(slide, "hardware");
    addNotes(slide,
      "四个关节使用独立的模拟输入和 PWM 输出。安全范围直接沿用 arm 项目的校准结果，避免视觉指令使舵机越界。抓取动作中，J2 固定在实测稳定值 78 度，减少其他关节动作时的姿态漂移。建议用时：55秒。",
      ["/Users/silverbrick/Documents/ChatGPT/arm_eye/src/main.cpp:8", "/Users/silverbrick/Documents/ChatGPT/arm_eye/src/main.cpp:53"]);
  }

  // 6. Gesture mapping
  {
    const slide = buildSlide15(deck, {
      title: sectionTitle("05  五种手势映射为可解释动作"),
      body1: {
        titleHere: { ...run("Open_Palm → S", 28, { bold: true, color: BLUE }), spaceAfter: 700 },
        loremIpsumDolorSitAmetConsecteturAdipiscing: run("待机 / 松开\nJ4 调整到最大安全角 160°\n其他关节保持", 21, { color: MUTED }),
        quamUtMassaLuctusCursusNullamPharetra: run("无手 10 帧后也自动发送 S。", 18, { color: MUTED }),
      },
      label1: run("Closed_Fist", 21, { bold: true, color: BLUE }),
      body2: run("G｜J3+J4 完整抓取轨迹，J4 校准 -5°", 18.5, { color: MUTED }),
      label2: run("Pointing_Up", 21, { bold: true, color: BLUE }),
      body3: run("U｜J3 以当前位置为基准逆时针 15°", 18.5, { color: MUTED }),
      label3: run("Thumb_Down", 21, { bold: true, color: BLUE }),
      body4: run("D｜U 的反动作，J3 顺时针 15°", 18.5, { color: MUTED }),
      label4: run("Victory", 21, { bold: true, color: BLUE }),
      body5: run("R｜J1 控制底座旋转到预设安全位置", 18.5, { color: MUTED }),
      footer1: slideNum(6),
    });
    addAccent(slide, "gestures");
    addNotes(slide,
      "系统只响应五种明确手势。张开手掌是待机和松开；握拳触发抓取轨迹；食指向上控制抬升；拇指向下执行抬升的反动作；胜利手势控制底座旋转。每个动作都能解释到具体关节，因此便于校准和答辩演示。建议用时：70秒。",
      ["/Users/silverbrick/Documents/ChatGPT/arm_eye/gesture_control/gesture_control.py:28", "/Users/silverbrick/Documents/ChatGPT/arm_eye/src/main.cpp:334"]);
  }

  // 7. Safety and filtering
  {
    const slide = buildSlide13(deck, {
      title: sectionTitle("06  安全性：识别过滤 + 运动约束"),
      body1: gridPair("置信度门槛", "识别置信度 ≥ 0.65 才进入候选状态。"),
      body2: gridPair("连续帧确认", "同一手势稳定 4 帧后才发送命令。"),
      body3: gridPair("平滑限速", "每 20 ms 最大变化 2°，减少舵机突跳。"),
      body4: gridPair("硬件复位", "GPIO13 长按 2 秒，四轴平滑回到 90°。"),
      footer1: slideNum(7),
    });
    addAccent(slide, "safety");
    addNotes(slide,
      "视觉识别存在瞬时误判，因此我设计了两级过滤：先检查 0.65 的置信度，再要求同一手势连续稳定 4 帧。进入固件后仍受安全角度和每周期 2 度的限速约束。如果出现异常，长按 GPIO13 两秒，四个关节会平滑回到 90 度。建议用时：65秒。",
      ["/Users/silverbrick/Documents/ChatGPT/arm_eye/gesture_control/gesture_control.py:21", "/Users/silverbrick/Documents/ChatGPT/arm_eye/src/main.cpp:33", "/Users/silverbrick/Documents/ChatGPT/arm_eye/src/main.cpp:40"]);
  }

  // 8. Verification
  {
    const slide = buildSlide19(deck, {
      title: sectionTitle("07  工程验证：可构建、可测试、可一键运行"),
      body1: {
        topic: { ...run("验证结论", 22, { bold: true, color: BLUE }), spaceAfter: 450 },
        loremIpsumDolorSitAmetConsecteturAdipiscing: run("固件通过 PlatformIO 构建；识别逻辑有自动化测试；macOS 启动器可完成烧录并自动开启摄像头识别。", 20, { color: MUTED }),
      },
      stat1: run("17", 54, { bold: true, color: BLUE }),
      stat2: run("9.7%", 54, { bold: true, color: BLUE }),
      stat3: run("22.5%", 54, { bold: true, color: BLUE }),
      body2: run("Python 单元测试\n全部通过", 20, { color: MUTED }),
      body3: run("ESP32 RAM\n占用率", 20, { color: MUTED }),
      body4: run("ESP32 Flash\n占用率", 20, { color: MUTED }),
      footer1: slideNum(8),
    });
    const verificationIntro = slide.shapes.items.find(
      (shape) => shape.name === "Content-Placeholder-15-12",
    );
    if (verificationIntro) {
      verificationIntro.position = { left: 41.33, top: 155, width: 1197.33, height: 120 };
    }
    addNotes(slide,
      "项目不仅能运行，也做了可重复验证。Python 识别状态机共有 17 项单元测试并全部通过；最近一次 ESP32 构建中，RAM 占用约 9.7%，Flash 占用约 22.5%，资源余量充足。双击启动器后会自动烧录并启动摄像头识别，降低现场演示步骤。建议用时：60秒。",
      ["/Users/silverbrick/Documents/ChatGPT/arm_eye/gesture_control/tests/test_gesture_control.py", "/Users/silverbrick/Documents/ChatGPT/arm_eye/platformio.ini", "/Users/silverbrick/Documents/ChatGPT/arm_eye/scripts/open_camera_after_upload.py"]);
  }

  // 9. Demo and limitations
  {
    const slide = buildSlide05(deck, {
      title: sectionTitle("08  现场演示路径与后续优化"),
      body1: {
        titleHere: { ...run("演示路径｜约 60 秒", 29, { bold: true, color: BLUE }), spaceAfter: 650 },
        loremIpsumDolorSitAmetConsecteturAdipiscing: run("1. 双击启动器并完成烧录\n\n2. 摄像头显示识别标签\n\n3. 依次演示 S、U/D、R、G\n\n4. 长按按钮完成安全复位", 19, { color: MUTED }),
      },
      body2: {
        titleHere: { ...run("当前限制｜可继续迭代", 29, { bold: true, color: BLUE }), spaceAfter: 650 },
        loremIpsumDolorSitAmetConsecteturAdipiscing: run("抓取效果受夹爪结构与摩擦力影响\n\nG 轨迹约 29 秒，演示节奏偏慢\n\n依赖摄像头权限与固定串口\n\n下一步：轨迹压缩、目标检测、力反馈", 19, { color: MUTED }),
      },
      footer1: slideNum(9),
    });
    addAccent(slide, "demo");
    addNotes(slide,
      "答辩时建议用一分钟完成现场演示：启动、展示识别标签，再按风险从低到高演示待机、升降、旋转和抓取，最后长按复位。当前主要限制不在识别链路，而在机械夹爪的结构、摩擦力和抓取轨迹时长。下一步优先压缩轨迹并加入视觉目标定位或力反馈。建议用时：65秒。",
      ["/Users/silverbrick/Documents/ChatGPT/arm_eye/src/gesture_trajectories.h", "/Users/silverbrick/Documents/ChatGPT/arm_eye/gesture_control/README.md"]);
  }

  // 10. Close
  {
    const slide = buildSlide26(deck, {
      title: run("CONCLUSION", 20, { bold: true, color: BLUE }),
      title2: {
        runs: [
          { run: "从可靠控制，\n", textStyle: { fontSize: "64px", typeface: FONT, color: BLACK, bold: true } },
          { run: "走向自然交互。", textStyle: { fontSize: "64px", typeface: FONT, color: BLACK, bold: true } },
        ],
        paragraphStyle: { lineSpacingPercent: 92000 },
      },
      title3: {
        loremIpsumDetails: run("arm：安全、录制、回放", 22, { color: MUTED }),
        loremIpsumDetails2: run("arm_eye：视觉、串口、手势闭环", 22, { color: MUTED }),
        loremIpsumDetails3: run("谢谢各位老师，请提问。", 22, { bold: true, color: BLUE }),
      },
    });
    addNotes(slide,
      "总结来说，arm 完成了机械臂可靠控制的底座，arm_eye 在此基础上实现了从视觉识别到安全执行的完整闭环。项目已经具备可演示、可测试和可继续扩展的工程基础。我的汇报结束，谢谢各位老师，请批评指正。建议用时：35秒。",
      ["/Users/silverbrick/Documents/ChatGPT/arm_eye/gesture_control/README.md"]);
  }

  for (const [index, slide] of deck.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(path.join(TMP_DIR, `${stem}.png`), await deck.export({ slide, format: "png", scale: 1 }));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(TMP_DIR, `${stem}.layout.json`), await layout.text());
  }

  await writeBlob(path.join(TMP_DIR, "deck-montage.webp"), await deck.export({ format: "webp", montage: true, scale: 1 }));
  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(FINAL_PPTX);
  console.log(`Created ${FINAL_PPTX}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
