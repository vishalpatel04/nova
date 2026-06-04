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

## Pairing

Claim code in **Pair Device**; app polls approval and retrieves the token automatically (no paste).

## Tests

```bash
xcodebuild -project NOVA.xcodeproj -scheme NOVA -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
```
