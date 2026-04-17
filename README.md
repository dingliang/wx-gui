# wx-gui

`wx-gui` 是一个 macOS 优先的桌面 GUI 项目，用来通过 Accessibility、AppleScript 和 OCR 自动化控制微信桌面客户端。  
`wx-gui` is a macOS-first desktop GUI project for automating the WeChat desktop client through Accessibility, AppleScript, and OCR.

## 项目状态 | Status

当前项目已经可以：  
The project can currently:

- 启动 PySide6 桌面 GUI  
  launch a PySide6 desktop GUI
- 连接正在运行的 macOS 微信客户端  
  connect to a running macOS WeChat client
- 搜索聊天并发送文本消息  
  search chats and send text messages
- 读取当前打开聊天中的可见消息  
  read visible messages from the currently open chat
- 轮询左侧可见会话，并支持按未读红点过滤  
  poll visible chats and optionally filter by unread red badges
- 执行基于规则的自动回复  
  run rule-based auto replies

项目仍在持续开发中。由于依赖真实微信桌面界面，微信版本变化后可能需要重新调节自动化逻辑。  
The project is still under active development. Because it depends on the live WeChat desktop UI, automation logic may need retuning after client updates.

## 主要功能 | Features

- macOS 优先的微信桌面自动化  
  macOS-first WeChat desktop automation
- 分层架构：GUI / Application / Automation  
  layered architecture: GUI / Application / Automation
- OCR 辅助的聊天与消息识别  
  OCR-assisted chat and message recognition
- 左侧可见会话监听与未读红点过滤  
  visible chat monitoring with unread badge filtering
- 带白名单、黑名单、冷却时间的规则型自动回复  
  rule-based auto reply with whitelist, blacklist, and cooldown support
- OCR 和未读角标调试脚本  
  debug scripts for OCR and unread badge inspection

## 快速开始 | Quick Start

### 1. 创建虚拟环境 | Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. 安装依赖 | Install dependencies

```bash
pip install -e .
```

### 3. 启动应用 | Start the app

```bash
python -m app.main
```

## macOS 权限要求 | macOS Permissions

应用需要 macOS 的“辅助功能”权限来控制微信。  
The app requires macOS Accessibility permissions to control WeChat.

根据你的启动方式，终端或宿主应用还可能需要“自动化”相关权限。  
Depending on how you launch the app, your terminal or host application may also need automation-related permissions.

## 调试脚本 | Debug Scripts

仓库内置了几个调试脚本：  
The repository includes several debug scripts:

- `scripts/debug_wechat_search.py`
- `scripts/debug_current_chat_ocr.py`
- `scripts/debug_visible_chat_badges.py`

这些脚本会把临时调试产物写入 `data/`，该目录默认已加入忽略。  
These scripts write temporary debug artifacts into `data/`, which is ignored by default.

## 目录结构 | Project Layout

```text
app/
  application/
  automation/
  domain/
  gui/
  infrastructure/
scripts/
tests/
ARCHITECTURE.md
```

## 安全提示 | Safety Notes

- 这个项目会自动化控制真实微信客户端。  
  This project automates a real WeChat desktop client.
- OCR 与 UI 自动化天然脆弱，界面变化时可能点错目标。  
  OCR and UI automation are inherently fragile and may click the wrong target if the UI changes.
- 开启自动回复前，请先在低风险聊天里充分测试。  
  Please test carefully in a low-risk chat before enabling auto reply.

## 免责声明 | Disclaimer

本项目是独立的自动化工具，与腾讯或微信没有从属、合作或官方维护关系。  
This project is an independent automation tool and is not affiliated with, endorsed by, or maintained by Tencent or WeChat.

你需要自行确保使用方式符合当地法律、工作规范以及平台适用条款。  
You are responsible for ensuring that your usage complies with local laws, workplace rules, and the platform terms that apply to your environment.

## 许可证 | License

本项目基于 MIT License 开源，详见 [LICENSE](./LICENSE)。  
This project is released under the MIT License. See [LICENSE](./LICENSE).
