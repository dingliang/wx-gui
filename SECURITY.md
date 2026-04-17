# Security Policy

## Supported Scope

This repository is an experimental desktop automation tool. Security-sensitive reports are still welcome, especially for:

- accidental leakage of local chat data
- unintended message sending behavior
- unsafe handling of screenshots, logs, or debug artifacts
- obvious code paths that could expose local machine details

## Reporting

If you discover a sensitive issue, please avoid opening a public issue with raw private data.

Instead, report it privately to the repository maintainer through the contact method configured on the hosting platform.

## Sensitive Data Handling

Before sharing logs, screenshots, or traces:

- remove personal chat content
- remove local absolute paths if possible
- remove account identifiers and private links

## Operational Reminder

Because this project automates a real messaging client, always test changes in a low-risk chat before using them in normal conversations.
