# NOVA Daily Driver Chat, Memory, and Voice

This slice keeps NOVA local-first and compact while making the popup the main daily interface.

## Conversational routing

- Deterministic commands still take precedence: system status, devices, sessions, safe search, approvals, background tasks, orchestration, and memory.
- General chat routes to local Ollama/Qwen/DeepSeek first.
- Paid providers stay disabled unless explicitly configured.
- If local inference fails, NOVA falls back to a compact canned help response and marks the response as degraded.

## Conversation memory

- Chat sessions persist on the backend.
- The popup restores the latest valid session on launch.
- Recent bounded turns are added to the local model prompt.
- `New Chat` clears the active thread without deleting older sessions.
- `Recent Chats` opens the saved session list.
- `Clear Current Conversation` clears the active draft, turns, and pending follow-ups.

## Structured personal memory

- Use `remember that ...` to save a user-approved fact.
- Use `what do you remember about me?` to review saved memory.
- Use `forget <memory key>` to remove a saved fact.
- Secret-like values, keys, tokens, credentials, and environment-like values are rejected.
- Structured memory survives new chats.

## Pending tool-intent memory

- `search my computer for <query>` opens a folder-choice follow-up.
- The follow-up is consumed once, expires, and stays owned by the same user + device + session.
- Unrelated replies re-prompt instead of going to the model first.

## Safe personal search roots

Approved search scopes:

- `~/Desktop`
- `~/Documents`
- `~/Downloads`
- `~/Projects`

Protected paths remain blocked:

- `~/NOVA_VAULT`
- `~/.ssh`
- `~/.aws`
- `~/.config`
- `.env` and key files

Search stays read-only, bounded, and local. No shell execution or cloud transmission is used for personal search.

## Compact popup UX

- The popup keeps the input visible.
- Recent chats and new-chat controls live in the header.
- Quick chips stay horizontal and do not cover messages.
- Streaming bubbles are replaced with the final response.
- Long answers collapse behind `Show more`.
- Errors are dismissible.

## Voice and wake word

- Voice input is local only.
- Push-to-talk remains available.
- Optional wake-word listening only runs while the popup is open.
- Supported wake phrases: `Nova`, `Hey Nova`, `Okay Nova`.
- Wake-word mode stays off by default.
- `Voice Off` is the kill switch.
- No raw audio is stored by default.
- No cloud speech service is used.
- If on-device speech recognition is unavailable, wake-word mode stays disabled.

## Voice settings

- Enable microphone input
- Enable "Hey Nova" while popup is open
- Start listening when popup opens
- Auto-send after voice transcription
- Sound cue on wake
- Stop listening when popup closes
- Voice Off kill switch
- Background listening while NOVA is closed is not implemented yet

## Startup

1. Start Ollama.
2. Ensure `qwen2.5:7b` is available locally.
3. Start the API and migrate the database.
4. Launch NOVAGenie.
5. Pair the Mac or restore its Keychain token.

## Troubleshooting

- Degraded provider badge means Ollama is unavailable or the model is missing.
- If wake-word mode is unsupported, use push-to-talk.
- If a search prompt hangs on `...`, use the latest build; that is a fixed loading-state bug.
- Protected files should block cleanly with an audit event, not a stack trace.

## Manual wake-word smoke

1. Open the popup.
2. Enable wake-word mode in Settings.
3. Close and reopen the popup.
4. Say `Hey Nova`.
5. Confirm the listening state appears.
6. Speak a request.
7. Confirm the transcript fills the input.
8. Press `Voice Off` and confirm recording stops immediately.

## Current limitation

- NOVA does not keep listening while the app is fully closed yet. That requires a separate privacy review.
