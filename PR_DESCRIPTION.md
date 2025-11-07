# 🚀 Claude CLI Adapter (Anthropic) — Production-Ready Integration

Concise, reviewer-friendly PR with clear setup, validation steps, and zero breaking changes.

## 1) Executive Summary
This PR adds a first-class Anthropic Claude adapter to AgentFlow. It enables Claude-powered plan generation via the CLI and full visualization in the web viewer. The change is backward‑compatible; Codex continues to work unchanged.

Why it’s useful
- Multi‑provider support (Claude + Codex)
- Mock mode for fast, cost‑free local testing and CI
- Web viewer compatible out of the box

Scope at a glance
- New adapter: `src/agentflow/adapters/claude_cli.py`
- Wrapper (mock/real): `anthropic_cli_wrapper.py`
- CLI flag: `--adapter claude`
- Docs: `docs/CLAUDE_ADAPTER.md`, example flow under `_PRD/`
- Tests: 7/7 unit tests passing

---

## 2) Quick Start (Windows PowerShell)

1) Configure environment (option A: ENV vars)
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-api03-..."   # or keep unset to use mock mode
$env:AGENTFLOW_ANTHROPIC_PATH = "D:\AgentFlow\anthropic_cli_wrapper.py"
```

2) Generate a plan with Claude
```powershell
py -m agentflow.cli --adapter claude "Create a user authentication flow"
```

3) View results in the web UI (keep this terminal open)
```powershell
py -m agentflow.cli view --port 5050
# Open http://127.0.0.1:5050
```

Optional (Bash/macOS/Linux)
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
export AGENTFLOW_ANTHROPIC_PATH="$PWD/anthropic_cli_wrapper.py"
python -m agentflow.cli --adapter claude "Create a user authentication flow"
python -m agentflow.cli view --port 5050
```

---

## 3) How It Works
- The adapter shells out to the wrapper (or Anthropic CLI), returning JSON.
- Text content is extracted, token usage captured, and artifacts are written.
- The web viewer reads artifacts and renders the plan timeline and details.

## 4) Configuration
Anthropic settings (all optional with sensible defaults):
- `anthropic_api_key` (ENV: `ANTHROPIC_API_KEY`)
- `anthropic_cli_path` (ENV: `AGENTFLOW_ANTHROPIC_PATH`)
- `anthropic_model` (default: `claude-3-5-sonnet-20241022`)
- `anthropic_max_tokens` (default: `4096`)

Mock mode (no API key): if the API key is missing or placeholder‑like, the wrapper returns contextual mock responses for fast, free testing and CI.

---

## 5) Run Tests
```powershell
pytest tests/unit -v
```
Expected result:
```
====== 7 passed ======
```

---

## 6) Troubleshooting
- Web UI closes: keep the terminal running; don’t close the window.
- Port busy: change with `--port 5051`.
- Windows path issues: use full paths (e.g., `D:\AgentFlow\anthropic_cli_wrapper.py`).
- No API key: mock mode kicks in automatically for local testing.

---

## 7) Files Changed (13, +781/−18)
New: `src/agentflow/adapters/claude_cli.py`, `anthropic_cli_wrapper.py`, `docs/CLAUDE_ADAPTER.md`, `tests/unit/test_claude_adapter.py`, `tests/live/test_claude_adapter_live.py`, `_PRD/example-flow-claude.yml`

Modified: `src/agentflow/adapters/__init__.py`, `src/agentflow/cli.py`, `src/agentflow/config.py`, `README.md`, `tests/unit/test_cli.py`, `tests/unit/test_codex_adapter.py`

---

## 8) What Reviewers Can Verify
- Switching adapters works: `--adapter claude` and `--adapter codex`.
- Artifact generation valid and viewable in the web UI.
- Mock mode behaves sensibly without a real API key.
- No regressions in existing Codex behavior.

---

## 9) Compatibility & Notes
- Backward compatible: Codex remains supported; defaults unchanged
- Security: API key is read from ENV or `.env`; mock mode avoids external calls
- No migration required; no API changes to existing code

## 10) Validation Checklist (Reviewer)
- [ ] `py -m agentflow.cli --adapter claude "hello world"` generates artifacts
- [ ] `py -m agentflow.cli view` lists plans and opens details
- [ ] Mock mode works without `ANTHROPIC_API_KEY`
- [ ] Codex path still works (no regressions)

Ready for review and merge. ✅
