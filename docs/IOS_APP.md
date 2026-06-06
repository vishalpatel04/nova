# NOVA iPhone app

## Build

```bash
python3 scripts/generate_xcode_projects.py
cd apps/ios
xcodebuild -project NOVA.xcodeproj -scheme NOVA -destination 'generic/platform=iOS Simulator' build
```

## Simulator runtime

Install iOS simulator runtimes in **Xcode → Settings → Platforms**. List devices:

```bash
xcrun simctl list devices available
```

Run in Simulator: open `NOVA.xcodeproj`, select a simulator, **Run**.

## Physical device

1. Connect iPhone via USB
2. Xcode → **Signing & Capabilities** → Team (Apple ID)
3. Free Apple Developer accounts: 7-day signing, limited background features
4. **Product → Run** on your device
5. TestFlight: archive and upload when ready for beta distribution

## Keychain token storage

Aligned with macOS: service **`com.nova.ios`**, account = **`DEVICE_ID`** / persisted `nova_device_id`. Legacy `com.nova.ios.credentials` / `device_token` still supported.

Set API base URL in **Pair Device** before claiming (avoid hardcoded localhost on physical devices — use your Mac's LAN IP).

## Simulator pairing (later)

1. Start API on host: `make dev`
2. In Simulator, set Base URL to `http://127.0.0.1:8000` (or host IP)
3. Create client pairing code via admin API, claim in app, approve, poll for token

## Pairing

Claim code in **Pair Device**; app polls approval and retrieves the token automatically (no paste).

## Tests

```bash
xcodebuild -project NOVA.xcodeproj -scheme NOVA -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
```
