# AgentFlow

> Prototype scaffolding for the AgentFlow planner and Codex CLI adapter described in the PRD.

## Problem We Are Solving

Modern agent workflows span many steps, tools, and retries, yet most planners treat execution as a black box. Operators cannot see a persistent plan, reason about dependencies, or audit decisions after the fact. Teams end up stitching together logs, spreadsheets, and ad-hoc dashboards just to answer basic questions like “what ran?” or “why did the agent choose that tool?”

## Why This Direction

AgentFlow fixes that visibility gap by standardizing on a canonical YAML plan that survives from planning through execution. A Codex-style CLI orchestrator executes the plan node by node, writing structured state and metrics back into the same file, while a lightweight Flask UI renders the plan as an interactive graph. This direction gives engineers:

- A machine-editable plan they can diff, review, and version in git.
- Deterministic execution with human-in-the-loop controls (pause, edit, rerun).
- A shared contract so external runners or evaluators can plug in without reimplementing the stack.
- Real-time observability over progress, failures, and evaluation metrics captured per node.

## Layout

- `src/agentflow/` - core package with configuration helpers and adapters.
- `tests/` - unit and live tests for the Codex adapter.

## Getting Started

```bash
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[dev]"
```

The Codex CLI must be installed globally:

```bash
npm.cmd install -g @openai/codex
```

Set `OPENAI_API_KEY` in `.env` (already provided). Tests automatically load it.

## Running Tests

- `pytest -k unit` runs fast unit tests.
- `pytest tests/live -m live` runs the live Codex integration test (uses real API calls).
