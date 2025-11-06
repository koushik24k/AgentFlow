from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Type

import yaml

from agentflow.config import ConfigurationError

from .plan import write_plan


class WorkflowHistoryEntry(Dict[str, Any]):
    """Dictionary-based representation of a workflow cycle entry."""


class WorkflowHistory(Dict[str, Any]):
    """Dictionary capturing workflow-wide metadata and cycle entries."""


def handle_workflow_command(
    args: Sequence[str],
    *,
    initialize_adapter: Callable[[], Tuple[object, Type[BaseException]]],
    execute_prompt: Callable[..., Any],
) -> int:
    parser = argparse.ArgumentParser(
        prog="agentflow workflow",
        description="Run multiple prompt cycles that adapt using self-evaluation feedback.",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=3,
        help="Number of adaptive cycles to run (default: 3).",
    )
    parser.add_argument(
        "--workflow-id",
        default=None,
        help="Identifier for the workflow archive. Generated from timestamp when omitted.",
    )
    parser.add_argument(
        "--history-root",
        default="sandbox/workflows",
        help="Directory used to persist cross-cycle history (default: sandbox/workflows).",
    )
    parser.add_argument(
        "--output",
        choices=["yaml", "afl"],
        default="yaml",
        help="Per-cycle artifact output preference (default: yaml). Use 'afl' to also emit AgentFlowLanguage files.",
    )
    parser.add_argument(
        "prompt",
        nargs=argparse.REMAINDER,
        help="Base prompt text supplied to the first cycle.",
    )

    namespace = parser.parse_args(list(args))
    base_prompt = " ".join(namespace.prompt).strip()
    if not base_prompt:
        parser.error("Prompt text is required for workflow execution.")

    cycles = namespace.cycles
    if cycles <= 0:
        parser.error("--cycles must be a positive integer.")

    history_root = Path(namespace.history_root).resolve()
    workflow_id = _determine_workflow_id(namespace.workflow_id)
    request_afl = namespace.output == "afl"

    try:
        adapter, adapter_error_class = initialize_adapter()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"Unknown adapter '{exc.args[0]}'. Use 'codex', 'copilot', or 'mock'.", file=sys.stderr)
        return 1

    outcome = run_workflow(
        adapter=adapter,
        adapter_error_class=adapter_error_class,
        base_prompt=base_prompt,
        cycles=cycles,
        request_afl=request_afl,
        workflow_id=workflow_id,
        history_root=history_root,
        execute_prompt=execute_prompt,
    )

    print(f"Workflow history written to: {outcome.history_path}")
    if outcome.failed_cycle is not None:
        print(
            f"Workflow halted after cycle {outcome.failed_cycle}; inspect per-cycle artifacts for details.",
        )
        return 1
    return 0


def run_workflow(
    *,
    adapter: object,
    adapter_error_class: Type[BaseException],
    base_prompt: str,
    cycles: int,
    request_afl: bool,
    workflow_id: str,
    history_root: Path,
    execute_prompt: Callable[..., Any],
) -> "WorkflowOutcome":
    history_dir = history_root / workflow_id
    history_dir.mkdir(parents=True, exist_ok=True)

    history = load_workflow_history(history_dir)
    if not history:
        now = datetime.now(timezone.utc).isoformat()
        history = WorkflowHistory(
            workflow_id=workflow_id,
            base_prompt=base_prompt,
            created_at=now,
            last_updated=now,
            runs=[],
        )

    runs: List[WorkflowHistoryEntry] = list(history.get("runs", []))
    starting_cycle = len(runs) + 1
    base_summary = base_prompt[:80].replace("\n", " ").strip() or "Workflow cycle"
    failed_cycle: Optional[int] = None
    history_path = history_dir / "history.yaml"

    for offset in range(cycles):
        cycle_number = starting_cycle + offset
        prompt, adjustment_summary, adjustment_payload = build_cycle_prompt(
            base_prompt=base_prompt,
            history_runs=runs,
        )

        cycle_summary = f"{base_summary} (cycle {cycle_number})"
        plan_id_prefix = f"{workflow_id}-cycle{cycle_number:02d}"
        result = execute_prompt(
            adapter,
            adapter_error_class,
            prompt=prompt,
            summary=cycle_summary,
            plan_id_prefix=plan_id_prefix,
            request_afl=request_afl,
        )

        plan_document = result.plan_document
        evaluation = extract_evaluation(plan_document)
        flow_summary = summarize_flow_spec(plan_document)

        reflection_node = build_workflow_summary_node(
            cycle_number=cycle_number,
            plan_document=plan_document,
            adjustment_summary=adjustment_summary,
            evaluation=evaluation,
            flow_summary=flow_summary,
            adjustment_payload=adjustment_payload,
        )
        if reflection_node:
            plan_document.setdefault("nodes", []).append(reflection_node)
            write_plan(result.plan_path, plan_document)
            result.plan_document = plan_document  # type: ignore[attr-defined]
            if isinstance(getattr(result, "final_state", None), dict):
                result.final_state["plan_document"] = plan_document  # type: ignore[index]

        history_entry = WorkflowHistoryEntry(
            cycle=cycle_number,
            prompt=prompt,
            prompt_adjustment=adjustment_summary,
            plan_path=str(result.plan_path),
            afl_path=str(result.afl_path) if getattr(result, "afl_path", None) else None,
            evaluation=evaluation,
            flow_summary=flow_summary,
            plan_status=result.plan_status,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        if history_entry.get("afl_path") is None:
            history_entry.pop("afl_path", None)
        runs.append(history_entry)
        history["runs"] = runs
        history["last_updated"] = datetime.now(timezone.utc).isoformat()

        history_path = save_workflow_history(history_dir, history)

        if result.plan_status == "failed":
            failed_cycle = cycle_number
            print(f"[cycle {cycle_number}] Plan execution failed: {result.plan_path}")
            break

        score = evaluation.get("score")
        score_text = f"{score:.3f}" if isinstance(score, (int, float)) else "n/a"
        print(
            f"[cycle {cycle_number}] Wrote plan artifact: {result.plan_path} (score: {score_text})",
        )
        if request_afl and getattr(result, "afl_path", None):
            print(f"[cycle {cycle_number}] Wrote AgentFlowLanguage artifact: {result.afl_path}")

    else:
        history_path = save_workflow_history(history_dir, history)

    return WorkflowOutcome(
        workflow_id=workflow_id,
        history_path=history_path,
        runs=runs,
        failed_cycle=failed_cycle,
    )


def build_cycle_prompt(
    *,
    base_prompt: str,
    history_runs: Sequence[WorkflowHistoryEntry],
) -> Tuple[str, str, Dict[str, Any]]:
    if not history_runs:
        return base_prompt, "Initial cycle prompt with no adjustments.", {}

    recent_runs = history_runs[-3:]
    reflection_lines: List[str] = []
    for entry in recent_runs:
        eval_block = entry.get("evaluation") or {}
        score = eval_block.get("score")
        justification = eval_block.get("justification") or eval_block.get("error")
        line_parts = [
            f"Cycle {entry.get('cycle')}",
            f"score={score:.3f}" if isinstance(score, (int, float)) else "score=n/a",
        ]
        if justification:
            line_parts.append(f"feedback={justification}")
        flow_summary = entry.get("flow_summary") or {}
        node_count = flow_summary.get("node_count")
        if isinstance(node_count, int):
            line_parts.append(f"nodes={node_count}")
        reflection_lines.append(" | ".join(line_parts))

    last_feedback = (history_runs[-1].get("evaluation") or {}).get("justification") or ""
    directives = derive_adjustment_directives(last_feedback)
    reflection_block = "\n".join(f"- {line}" for line in reflection_lines)
    directive_block = "\n".join(f"- {item}" for item in directives)

    adjustment_summary = "Injected reflective context from previous cycles and targeted improvements."
    adaptive_prompt = (
        f"{base_prompt}\n\n"
        "### Reflection Log\n"
        f"{reflection_block}\n\n"
        "### Improvement Directives\n"
        f"{directive_block}\n\n"
        "Using the reflections above, regenerate or refine the LangGraph plan. "
        "Be explicit about how this cycle differs from earlier attempts and "
        "explain the adjustments inside the self-evaluation justification."
    )

    adjustment_payload = {
        "reflection_log": [line for line in reflection_lines],
        "directives": directives,
    }
    return adaptive_prompt, adjustment_summary, adjustment_payload


def derive_adjustment_directives(feedback: str) -> List[str]:
    normalized = feedback.lower()
    directives: List[str] = []

    if "branch" in normalized or "condition" in normalized:
        directives.append("Strengthen branching coverage to handle the missing conditions noted above.")
    if "loop" in normalized or "iteration" in normalized:
        directives.append("Refine loop nodes with clearer exit criteria and tracking of iterations.")
    if "evaluation" in normalized or "self" in normalized:
        directives.append("Improve the evaluation node to report precise pass/fail signals.")
    if "prompt" in normalized or "clarity" in normalized:
        directives.append("Clarify each node's prompt so tool calls and outputs are unambiguous.")

    if not directives:
        directives.append("Address the critique directly and document how the LangGraph changes resolve it.")
    directives.append("Track concrete changes in the evaluation justification for this cycle.")
    return directives


def extract_evaluation(plan_document: Dict[str, Any]) -> Dict[str, Any]:
    node = _primary_node(plan_document)
    outputs = node.get("outputs") or {}
    evaluation = outputs.get("evaluation")
    if isinstance(evaluation, dict):
        eval_payload = {
            "score": evaluation.get("score"),
            "justification": evaluation.get("justification"),
            "error": evaluation.get("error"),
            "raw_message": evaluation.get("raw_message"),
        }
    else:
        eval_payload = {}

    metrics = node.get("metrics") or {}
    if "evaluation_score" in metrics and "score" not in eval_payload:
        eval_payload["score"] = metrics.get("evaluation_score")
    if "evaluation_error" in metrics and "error" not in eval_payload:
        eval_payload["error"] = metrics.get("evaluation_error")

    return eval_payload


def summarize_flow_spec(plan_document: Dict[str, Any]) -> Dict[str, Any]:
    node = _primary_node(plan_document)
    outputs = node.get("outputs") or {}
    flow_spec = outputs.get("flow_spec")
    if not isinstance(flow_spec, dict):
        return {}

    nodes = flow_spec.get("nodes") or []
    edges = flow_spec.get("edges") or []
    branch_nodes = 0
    loop_nodes = 0
    evaluation_nodes = 0

    for spec_node in nodes:
        if isinstance(spec_node, dict):
            if spec_node.get("on_true") or spec_node.get("on_false"):
                branch_nodes += 1
            if spec_node.get("type") == "loop":
                loop_nodes += 1
            if spec_node.get("type") == "evaluation":
                evaluation_nodes += 1

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "branch_nodes": branch_nodes,
        "loop_nodes": loop_nodes,
        "evaluation_nodes": evaluation_nodes,
    }


def build_workflow_summary_node(
    *,
    cycle_number: int,
    plan_document: Dict[str, Any],
    adjustment_summary: str,
    evaluation: Dict[str, Any],
    flow_summary: Dict[str, Any],
    adjustment_payload: Dict[str, Any],
) -> Dict[str, Any]:
    primary = _primary_node(plan_document)
    primary_id = primary.get("id", "codex_execution")

    justification = evaluation.get("justification") or evaluation.get("error")
    score = evaluation.get("score")
    outputs: Dict[str, Any] = {
        "adjustment_summary": adjustment_summary,
        "reflection": adjustment_payload,
        "evaluation_score": score,
        "evaluation_justification": justification,
        "flow_summary": flow_summary,
    }

    node_id = f"workflow_reflection_cycle_{cycle_number}"
    summary = f"Workflow reflection for cycle {cycle_number}"

    return {
        "id": node_id,
        "type": "reflection",
        "summary": summary,
        "depends_on": [primary_id],
        "status": "succeeded",
        "attempt": 1,
        "inputs": {},
        "outputs": outputs,
        "artifacts": [],
        "metrics": {},
        "timeline": {},
        "history": [],
    }


def load_workflow_history(history_dir: Path) -> WorkflowHistory:
    history_path = history_dir / "history.yaml"
    if not history_path.exists():
        return WorkflowHistory()

    with history_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            return WorkflowHistory()
        return WorkflowHistory(data)


def save_workflow_history(history_dir: Path, history: WorkflowHistory) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / "history.yaml"
    with history_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(history, handle, sort_keys=False)
    return history_path


def _primary_node(plan_document: Dict[str, Any]) -> Dict[str, Any]:
    nodes = plan_document.get("nodes") or []
    for node in nodes:
        if isinstance(node, dict) and node.get("id") == "codex_execution":
            return node
    return nodes[0] if nodes else {}


def _determine_workflow_id(candidate: Optional[str]) -> str:
    if candidate:
        return _sanitize_identifier(candidate)
    timestamp = datetime.now(timezone.utc).strftime("workflow-%Y%m%d%H%M%S")
    return timestamp


def _sanitize_identifier(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")
    return sanitized or datetime.now(timezone.utc).strftime("workflow-%Y%m%d%H%M%S")


class WorkflowOutcome:
    def __init__(
        self,
        *,
        workflow_id: str,
        history_path: Path,
        runs: List[WorkflowHistoryEntry],
        failed_cycle: Optional[int],
    ) -> None:
        self.workflow_id = workflow_id
        self.history_path = history_path
        self.runs = runs
        self.failed_cycle = failed_cycle
