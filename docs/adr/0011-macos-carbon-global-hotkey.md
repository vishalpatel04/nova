# ADR-0011: macOS global hotkey via Carbon

## Status

Accepted — Slice 2C

## Context

Summon NOVA from any app with ⌥ S without requiring Accessibility trust.

## Decision

Use Carbon `RegisterEventHotKey` + `InstallEventHandler` in `GlobalHotkeyManager`. Default: Option + S (`kVK_ANSI_S`). Toggle and conflict messaging in Settings.

## Alternatives considered

- `NSEvent.addGlobalMonitorForEvents` — requires Accessibility
- CGEvent tap — requires Accessibility

## Consequences

- Hotkey does not work when another app registers the same combination
- Wake-word daemon remains a future slice
