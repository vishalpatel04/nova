# NOVA

Personal AI operating system for Arth Agrawal — a production-quality nervous-system foundation with cloud-ready control plane, native iOS/macOS clients, and replaceable worker nodes.

## Architecture

```mermaid
graph TB
    subgraph clients [Clients]
        iOS[iPhone SwiftUI]
        macOS[macOS Genie]
    end
    subgraph control [Control Plane]
        API[FastAPI]
        DB[(PostgreSQL)]
        Redis[(Redis)]
    end
    subgraph workers [Worker Nodes]
        W1[macOS Worker]
        W2[Linux Worker]
    end
    iOS --> API
    macOS --> API
    W1 --> API
    W2 --> API
    API --> DB
    API --> Redis
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full details.

## Quick start

```bash
make bootstrap    # venv, deps, Docker, migrations
make dev          # start API on :8000
make worker       # start worker daemon (separate terminal)
make test         # run pytest
```

## Stack

| Component | Technology |
|-----------|------------|
| Control plane | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL (pgvector-compatible) |
| Cache | Redis |
| Worker | Python daemon (launchd-managed) |
| iPhone | SwiftUI |
| macOS | SwiftUI menu-bar app |

## Agents

Seven permanent commanders: **NOVA**, **MARS**, **MERCURY**, **JUPITER**, **VENUS**, **SATURN**, **NEPTUNE** — plus functional specialists. See [docs/AGENT_HIERARCHY.md](docs/AGENT_HIERARCHY.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Agent Hierarchy](docs/AGENT_HIERARCHY.md)
- [Device Model](docs/DEVICE_MODEL.md)
- [Configuration](docs/CONFIGURATION.md)
- [Foundation Slice 1 Plan](docs/FOUNDATION_SLICE_1_PLAN.md)
- [ADRs](docs/adr/)

## License

Private — Arth Agrawal.
