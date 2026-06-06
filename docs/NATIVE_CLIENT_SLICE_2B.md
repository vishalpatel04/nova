# Native Client Slice 2B

## iPhone (NOVA)

- Keychain device token storage
- Pairing claim + honest approval waiting (paste token after operator approves)
- Authenticated REST (`NOVAAPIClient`)
- WebSocket tickets for mission timeline stream
- Live Devices / Agents / Mission Room
- Queued mission and offline worker messaging
- Apple Speech tap-to-listen + AVSpeech synthesis
- App Intent `NOVAListenIntent` for Shortcuts / Action Button assignment

**Not in 2B:** global always-on iPhone wake word.

## macOS (NOVAGenie)

- Menu-bar app with Keychain token
- Live worker health from `/api/v1/system/status`
- Voice modes: prime_only, war_room, silent_operations, briefing
- Orb click-to-talk with Apple Speech
- Settings window: pairing token, devices, agents, missions
- Wake-word provider interface preserved in `VoiceInterfaces.swift` — no working daemon in 2B

**Not in 2B:** global hotkey daemon (document assign Shortcuts on macOS until Carbon/hotkey helper slice).

## Manual Action Button setup (iPhone)

1. Open Shortcuts → App Shortcuts → NOVA → **Start NOVA Listening**
2. Assign to Action Button or Control Center

## Pairing (both platforms)

1. Operator creates code: `POST /api/v1/pairing/codes` (bootstrap admin)
2. Client claims code in Pairing screen
3. If `pending_approval`, operator approves; client pastes issued token into app
