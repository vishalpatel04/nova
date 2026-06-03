# ADR 0003: Lightweight Workflow Runner (LangGraph-Ready)

## Status

Accepted — Foundation Slice 1

## Context

Foundation Slice 1 implements one durable mission: `system_status`. LangGraph adds dependency weight, checkpoint storage, and operational complexity. The workflow interface must remain swappable for LangGraph in Slice 2 when multi-step agent missions arrive.

## Decision

Implement a typed workflow abstraction in `nova_core/workflows/base.py`:

- `BaseWorkflow` with `steps()` returning `WorkflowStepDefinition` list
- `WorkflowContext` carrying session, settings, mission, and event emitter
- `WORKFLOW_REGISTRY` mapping mission types to workflow classes

Do **not** import LangGraph in Slice 1. Document the adapter boundary:

```python
# Future: LangGraph adapter wraps BaseWorkflow steps as graph nodes
class LangGraphAdapter:
    def compile(self, workflow: BaseWorkflow) -> CompiledGraph: ...
```

## Consequences

**Positive:**
- Zero LangGraph deps in Slice 1; faster bootstrap.
- `system_status` mission is fully testable with plain async Python.
- WebSocket progress events already wired via `emit_event` callback.

**Negative:**
- Must write LangGraph adapter in Slice 2 (planned).
- No durable checkpoint/resume until LangGraph is integrated.

## When to adopt LangGraph

Adopt in Slice 2 when implementing:
- Multi-agent missions with branching
- Human-in-the-loop approval gates mid-workflow
- Crash recovery and resume from checkpoint
