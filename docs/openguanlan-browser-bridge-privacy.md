# OpenGuanlan Browser Bridge Privacy Policy

Effective date: 2026-05-13

OpenGuanlan Browser Bridge is a read-only browser extension for Guanlan. It helps
AI agents collect user-authorized target-page visible evidence from Chrome or
Chromium and send it to a local `openguanlan daemon` running on the same
computer.

## Data Collected

The extension can read the current target page URL, title, visible text, visible
links, visible frame metadata, and visible HTML structure after the user grants
the current site and authorizes a Guanlan browser-assist task.

The extension does not collect or read:

- Cookies
- Tokens
- Passwords
- localStorage or sessionStorage
- Browser profiles or browser databases
- Keychain or operating system credential stores
- Hidden credential fields
- Unrelated private messages, orders, admin pages, or personal pages

## Data Use

Data is used only to create Guanlan browser-visible evidence for the target page
requested by the user. The extension sends results only to the local
`openguanlan daemon` on `127.0.0.1` or `localhost`.

The extension does not sell data, use data for advertising, or send browser page
content to a remote server.

## Permissions

The extension requests the minimum permissions needed for its single purpose:

- `tabs` to identify the active target tab.
- `scripting` to read visible page content after site permission is granted.
- `activeTab` to let the user authorize the current tab from the popup.
- localhost host permissions to communicate with `openguanlan daemon`.
- optional site permissions, requested per site from the popup.

The extension does not request cookie, storage, debugger, downloads, or native
messaging permissions.

## Security

The extension runs as a Manifest V3 extension. Its code is packaged with the
extension and does not load remote executable code. HTML and attribute extraction
redacts common token, session, authentication, password, secret, and CSRF
markers.

## User Control

Users choose which sites to grant. Users can revoke site permissions in Chrome's
extension settings at any time. Users can stop the local daemon by terminating
the `openguanlan daemon` process.

## Contact

For questions, use the Guanlan GitHub repository:
https://github.com/shenyangs/Guanlan

