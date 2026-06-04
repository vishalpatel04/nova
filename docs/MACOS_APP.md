# NOVA macOS menu-bar app (NOVAGenie)

## Build

```bash
python3 scripts/generate_xcode_projects.py
cd apps/macos
xcodebuild -project NOVAGenie.xcodeproj -scheme NOVAGenie build
```

## Features (Slice 2C)

- Pairing status polling
- Mission Room WebSocket stream with reconnect badge
- Global hotkey **⌃⌥ Space** (Carbon, no Accessibility)
- Launch at login via `SMAppService`

## Worker always-on

```bash
make install-worker   # launchd agent
make worker-status
make worker-restart
make uninstall-worker
```

Logs: `~/Library/Logs/nova/nova-worker.stdout.log`

## Tests

```bash
xcodebuild -project NOVAGenie.xcodeproj -scheme NOVAGenie test
```
