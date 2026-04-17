# Contributing

Thanks for your interest in contributing to `wx-gui`.

## Before You Start

- This project focuses on macOS-first WeChat desktop automation.
- UI automation is sensitive to client layout changes, so please keep changes small and well-scoped.
- Prefer fixes that improve observability and safety over aggressive automation shortcuts.

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pytest -q
```

## Contribution Guidelines

- Keep code ASCII unless the file already uses Chinese text and Chinese is clearly justified.
- Prefer small PRs with a focused purpose.
- Add or update tests when you change application-layer behavior.
- Avoid committing local debug artifacts, screenshots, or runtime logs.
- Be careful with changes that could cause real messages to be sent unintentionally.

## Bug Reports

When reporting automation bugs, please include:

- macOS version
- WeChat desktop version if known
- what page or chat UI was visible
- whether the issue is reproducible
- OCR/debug output if available

## Security and Privacy

Please do not include real chat screenshots, personal conversations, or secrets in public issues unless they have been sanitized first.

For security-sensitive reports, see [SECURITY.md](./SECURITY.md).
