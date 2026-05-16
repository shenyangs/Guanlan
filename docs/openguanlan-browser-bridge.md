# OpenGuanlan Browser Assist

OpenGuanlan is Guanlan's browser-assisted evidence layer. Its default job is to
turn a weak public read, dynamic page, login gate, or verification page into a
clear user-authorized visible-page task for the host Agent browser.

OpenGuanlan does not mean "install the Chrome extension first." The stable
default path is:

```bash
guanlan diagnose page "URL"
guanlan browser-assist plan "URL" --json
guanlan browser-assist sessions "URL" --json
guanlan browser-assist run "URL" --adapter openguanlan --json
guanlan archive add-browser-note --from-json browser-notes.jsonl
```

The host Agent opens the target page, lets the user finish login, verification,
or account switching when needed, and then extracts only the visible target-page
content described by the OpenGuanlan contract.

## Optional Bridge

`openguanlan-bridge` is an optional sidecar for environments that want a
dedicated Chrome/Chromium extension and local daemon. It is not required for the
main OpenGuanlan path.

Use it only when the user explicitly wants this sidecar:

```bash
guanlan browser-assist setup-openguanlan --json
openguanlan setup --json
openguanlan daemon
openguanlan pair-code --json
guanlan browser-assist run "URL" --adapter openguanlan-bridge --json
```

The extension must still be installed and enabled manually by the user, and the
pairing code must be copied by the user into the popup. Guanlan does not
silently install extensions or grant website permissions.

## Safety Boundary

OpenGuanlan reads target-page visible evidence only after user authorization. It
does not read Cookie, Token, localStorage, sessionStorage, browser profile,
browser database, keychain, password fields, hidden credential fields, or
unrelated personal pages.

Private or account pages may only be read when they are the target page and the
user has separately authorized that target, purpose, risk, and read-only scope.
Such output must be marked `private_account_evidence=true`.

It does not perform write actions such as clicking submit buttons, filling
forms, uploading files, posting, liking, commenting, following, purchasing, or
sending messages.

## Chrome Store Package

The packaged extension remains useful for the optional bridge. Its permission
model must stay narrow:

- localhost daemon access by default;
- target website access requested per site from the popup;
- no `cookies`, `debugger`, `downloads`, native messaging, profile, or storage
  export permissions.

Build the optional bridge package with:

```bash
scripts/build_openguanlan_extension.sh
```
