# OpenGuanlan Browser Bridge

OpenGuanlan Browser Bridge is the Chrome/Chromium extension companion for
Guanlan browser-assisted evidence. It connects the visible browser tab to the
local `openguanlan daemon` so an Agent can read target-page visible content
after user authorization.

## Purpose

The extension has one narrow purpose: provide read-only browser-visible evidence
for Guanlan when public page reading is weak, dynamic, login-gated, or blocked.

It is not a general browser automation product. It does not provide write
actions such as clicking submit buttons, filling forms, uploading files, posting,
liking, commenting, following, purchasing, or sending messages.

## Permissions

- `tabs`: read the active tab URL/title and manage the target tab selected by the
  user-authorized Guanlan task.
- `scripting`: read visible DOM text from a site after that site has been
  explicitly granted.
- `activeTab`: let the user grant the current site from the popup.
- `http://127.0.0.1:19830/*` and `http://localhost:19830/*`: communicate with
  the local `openguanlan daemon`.
- Optional host permissions: requested per site from the popup before visible
  page content is extracted.

The extension does not request `cookies`, `storage`, `debugger`, `downloads`, or
native messaging permissions.

## User Flow

1. Install or load the extension.
2. Run `openguanlan daemon` locally.
3. Open the target page in Chrome/Chromium.
4. Click the OpenGuanlan extension and grant the current site.
5. After the user authorizes the Guanlan browser-assist task, run:

```bash
guanlan browser-assist run "URL" --adapter openguanlan --execute --json
```

The output is Guanlan `browser_visible` JSON/JSONL, suitable for
`guanlan archive add-browser-note --from-json browser-notes.jsonl`.

## Safety Boundary

OpenGuanlan Browser Bridge does not read Cookie, Token, localStorage,
sessionStorage, browser profile, browser database, keychain, password fields, or
hidden credential fields. HTML and attribute reads are sanitized for common
token/session/password markers.

Private or account pages may only be read when they are the target page and the
user has separately authorized that target, purpose, risk, and read-only scope.
Such output must be marked `private_account_evidence=true`.

