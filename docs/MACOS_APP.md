# NOVA macOS menu-bar app (NOVAGenie)

## Build

```bash
python3 scripts/generate_xcode_projects.py
cd apps/macos
xcodebuild -project NOVAGenie.xcodeproj -scheme NOVAGenie build
```

## Device token (Keychain)

Store the claimed client token the same way as workers: **service** `com.nova.macos`, **account** = your `DEVICE_ID` (e.g. `arth-mac-client`).

```bash
export DEVICE_ID=arth-mac-client
security add-generic-password -U -s com.nova.macos -a "$DEVICE_ID" -w "$TOKEN"
```

The app also reads `DEVICE_ID` from the environment when `nova_device_id` is not set yet, and can discover a lone Keychain entry on `com.nova.macos`. On launch, NOVA logs `nova_token_lookup_*` and `nova_auth_diagnostic` (token value never logged).

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
