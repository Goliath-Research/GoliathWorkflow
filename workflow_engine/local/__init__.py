"""In-process workflow engine — executes WorkflowDefinitionSpec without DB/gateway."""

from .engine import LocalWorkflowEngine, RunResult

__all__ = ["LocalWorkflowEngine", "RunResult"]
