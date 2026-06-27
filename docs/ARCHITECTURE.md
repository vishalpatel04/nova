# NOVA Architecture

## Overview

NOVA is a personal AI operating system composed of a **control plane**, **worker nodes**, and **native clients**. The architecture supports adding or replacing devices without changing business logic.

## System diagram

```mermaid
graph TB
    subgraph operator [Operator Devices]
        iPhone[iPhone Client]
        MacGenie[macOS Genie App]
    end

    subgraph m3 [Current M3 MacBook]
        API[FastAPI Control Plane]
        PG[(PostgreSQL)]
        RD[(Redis)]
        Worker[nova-worker daemon]
    end

    subgraph future [Future Nodes]
        M2[M2 MacBook Worker]
        Mini[Mac mini Worker]
        Linux[Linux Worker]
        Cloud[Cloud Worker]
        Friend[Friend Laptop]
    end

    iPhone -->|HTTP WebSocket| API
    MacGenie -->|HTTP WebSocket| API
    Worker -->|register heartbeat| API
    M2 -.->|outbound| API
    Mini -.->|outbound| API
    Linux -.->|outbound| API
    Cloud -.->|outbound| API
    Friend -.->|outbound| API
    API --> PG
    API --> RD
```

## Components

### Control plane (`apps/api`)

FastAPI service providing:

- Health, readiness, and system status endpoints
- Device and agent registry
- Mission creation and execution
- WebSocket mission progress events
- Audit logging

Runs in Docker Compose alongside PostgreSQL and Redis.

### Worker daemon (`apps/worker`)

Launchd-managed service on each worker node:

- Outbound registration and heartbeat
- Capability reporting (14 typed capabilities)
- Reconnect with exponential backoff
- Health endpoint on port 9100
- **No dangerous tool execution in Slice 1**

Device identity is set via `DEVICE_ID` environment variable — never hardcoded to hardware.

### iPhone client (`apps/ios`)

SwiftUI app with:

- NOVA Orb home screen
- Text chat, Mission Room, Agents, Devices, Settings
- Placeholder STT/TTS interfaces
- Design tokens and agent colour system

### macOS genie (`apps/macos`)

SwiftUI menu-bar app with:

- Floating NOVA Orb placeholder
- Compact and expanded chat
- Voice modes: `prime_only`, `war_room`, `silent_operations`, `briefing`
- Worker health display
- Mock wake-word, STT, TTS provider interfaces

### Core library (`nova_core`)

Shared Python domain logic:

| Package | Purpose |
|---------|---------|
| `models/` | SQLAlchemy ORM, enums, model lanes |
| `mission_graph/` | MissionGraph state machine (LangGraph-style) |
| `forge/` | Forge engine adapters (template, OpenHands, Claude, Codex) |
| `gateway/` | Multi-channel message envelope (OpenClaw-inspired, skills blocked) |
| `voice/` | Wake-word + transcript pipeline |
| `agent_os/` | Prime/Forge/Nexus/Orbit mission execution |
| `schemas/` | Pydantic settings and API DTOs |
| `tools/` | Typed tool extension points |
| `sentry/` | Logging and audit |

## Agent OS stack (investor architecture)

NOVA is the **local command centre** — not a replacement for Claude Code or OpenHands.

```mermaid
graph TB
    UI[NOVAGenie / CLI / Voice]
    Gateway[NOVA Gateway]
    Graph[MissionGraph]
    Prime[Prime / Commanders]
    Forge[Forge Engines]
    Sentry[Sentry Gate]

    UI --> Gateway
    Gateway --> Graph
    Graph --> Prime
    Prime --> Forge
    Forge --> Template[deterministic_template]
    Forge --> OH[OpenHands adapter]
    Forge --> CC[Claude Code CLI]
    Forge --> CX[Codex CLI]
    Forge --> Sentry
```

- **MissionGraph** records node evidence for every mission
- **Forge** delegates to external coding agents when configured
- **OpenClaw skills are never executed** — gateway pattern only
- **Investor demo fallback:** deterministic templates always work offline

See [EXTERNAL_AGENT_STACK_AUDIT.md](./EXTERNAL_AGENT_STACK_AUDIT.md).

## Data flow: system_status mission

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant NOVA as NOVA Workflow
    participant DB as PostgreSQL
    participant WS as WebSocket

    Client->>API: POST /missions (system_status)
    API->>DB: Create mission + timeline event
    API->>NOVA: Run workflow
    NOVA->>DB: Query worker heartbeats
    NOVA->>DB: Calculate availability
    NOVA->>WS: Emit progress events
    NOVA->>DB: Store agent messages + result
    API->>Client: Mission response
```

## Design principles

1. **APIs before desktop clicking** — all orchestration goes through the control plane.
2. **Independent worker nodes** — no merged RAM/GPU pools; each node reports its own capabilities.
3. **Replaceable device identity** — `DEVICE_ID` is configurable per node.
4. **Never store plaintext secrets** — API keys via environment only.
5. **Approval-ready structure** — missions support cancellation and approval gates from day one.

## Known limitations (Slice 1)

- No API authentication (dev bearer placeholder)
- Redis connected but not used for pub/sub
- SwiftUI clients use mock data
- No voice capture, Gmail, shell execution, or desktop automation
- Scheduler app is a placeholder

## Next slice

See [FOUNDATION_SLICE_1_PLAN.md](FOUNDATION_SLICE_1_PLAN.md) for Slice 2 scope.
