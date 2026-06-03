# ADR 0002: Native iOS and macOS Clients

## Status

Accepted — Foundation Slice 1

## Context

NOVA is a voice-first personal AI operating system. The operator uses an iPhone and a MacBook daily. A web UI or Telegram bot would not deliver the native experience required (NOVA Orb, menu-bar genie, Action Button, wake word).

## Decision

Build native SwiftUI clients:

- **iPhone** (`apps/ios/`) — Orb home, text chat, Mission Room, Agents, Devices, Settings.
- **macOS** (`apps/macos/`) — Menu-bar app, floating Orb, compact/expanded chat, voice modes, worker health display.

Both clients use a shared networking layer pattern and design tokens. Slice 1 uses mock/preview data with API contracts defined; live binding comes in Slice 2.

## Consequences

**Positive:**
- Platform-native UX (Orb, menu bar, permissions, Keychain).
- Action Button App Intent and wake-word providers integrate naturally on macOS/iOS.
- Distinct voice profiles per commander map to AVSpeech/equivalent.

**Negative:**
- Requires macOS CI runner for Xcode builds.
- Two codebases to maintain (mitigated by shared design tokens and API DTOs).

## Alternatives considered

| Alternative | Rejected because |
|-------------|------------------|
| React Native | Poor menu-bar / Action Button / wake-word integration |
| Web PWA | No Orb, no menu bar, weak voice pipeline |
| Single cross-platform Flutter | macOS menu-bar and iOS Action Button immature |
