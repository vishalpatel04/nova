# NOVA Voice Mode

Local wake-word and push-to-talk voice commands route into the same `/api/v1/chat` endpoint used by NOVAGenie.

## CLI

```bash
# Simulated transcript (CI-safe)
nova voice --transcript "hey nova build a landing page for SusCo"

# Push-to-talk from stdin
echo "hey nova, draft an email about this app" | nova voice --push-to-talk --debug
```

## Wake phrases

- `hey nova`
- `okay nova`
- `nova` (prefix)

After wake detection, the remainder of the transcript is sent as a chat message.

## Safety

High-risk approvals require explicit wording when using voice:

- Email send: `yes, send email`
- Deploy: `yes, approve deployment`

A casual `yes` after wake does **not** approve Level 2/3 actions unless the pending approval context is clear in chat.

## macOS app

NOVAGenie uses the same wake parsing logic via `VoiceRuntime` while the compact window is open. Mic permissions are required (`NSMicrophoneUsageDescription`, `NSSpeechRecognitionUsageDescription`).

## STT options

1. macOS on-device Speech framework (preferred in app)
2. Push-to-talk fallback via CLI stdin
3. Optional local Whisper installs are not required for the investor demo

## Environment

| Variable | Purpose |
|----------|---------|
| `NOVA_API_BASE` | API URL (default `http://127.0.0.1:8000`) |
| `NOVA_API_TOKEN` | Bearer token for chat API |

## Limitations

- No background always-on listening while the popup is closed
- Wake-word uses transcript phrase detection, not a dedicated keyword model
- TTS is optional and macOS-native only in the app today
