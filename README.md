# wx-gui

`wx-gui` is a macOS-first desktop GUI for automating the WeChat desktop client through Accessibility, AppleScript, and OCR-based UI recognition.

## Status

This project is already able to:

- launch a PySide6 desktop GUI
- connect to a running macOS WeChat client
- search chats and send text messages
- read the currently visible chat content
- monitor visible chats, including unread-badge polling
- trigger simple rule-based auto replies

This project is still under active development. The automation logic depends on the current WeChat desktop UI and may require tuning after client updates.

## Features

- macOS-first WeChat desktop automation
- layered architecture with GUI, application, and automation boundaries
- OCR-assisted chat and message recognition
- visible-chat monitoring with unread badge filtering
- rule-based auto reply with whitelist, blacklist, and cooldown support
- debug scripts for OCR and visible-chat badge inspection

## Quick Start

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -e .
```

### 3. Start the app

```bash
python -m app.main
```

## macOS Permissions

The app requires macOS Accessibility permissions to control WeChat.

Depending on your environment, you may also need to allow automation-related access for the terminal or host application you use to launch the app.

## Debug Scripts

The repository includes helper scripts for OCR and UI debugging:

- `scripts/debug_wechat_search.py`
- `scripts/debug_current_chat_ocr.py`
- `scripts/debug_visible_chat_badges.py`

These scripts write temporary debug artifacts into `data/`, which is ignored from version control by default.

## Project Layout

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

## Safety Notes

- This project automates a real desktop WeChat client.
- OCR and UI automation are inherently fragile and may click the wrong target if the UI changes.
- Please test carefully before enabling auto reply in real chats.

## Disclaimer

This project is an independent automation tool and is not affiliated with, endorsed by, or maintained by Tencent or WeChat.

You are responsible for ensuring your usage complies with local laws, workplace rules, and the platform terms that apply to your environment.

## License

This project is released under the MIT License. See [LICENSE](./LICENSE).
