"""
Adapter implementations that integrate external systems with AgentFlow.
"""

from .codex_cli import CodexCLIAdapter, CodexCLIError, CodexResult
from .claude_cli import ClaudeCLIAdapter, ClaudeCLIError, ClaudeResult

# Simple registry for CLI-selectable adapters
ADAPTERS = {
	"codex": CodexCLIAdapter,
	"claude": ClaudeCLIAdapter,
}

__all__ = [
	"CodexCLIAdapter",
	"CodexCLIError",
	"CodexResult",
	"ClaudeCLIAdapter",
	"ClaudeCLIError",
	"ClaudeResult",
	"ADAPTERS",
]
