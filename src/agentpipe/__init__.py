"""AgentPipe: Build your own autonomous agent pipelines.

An Airflow-inspired framework where each task is an autonomous agent
with a model brain and tools, connected in a DAG pipeline.
"""

__version__ = "0.1.0"

from agentpipe.core.agent import Agent
from agentpipe.core.condition import Condition, Edge
from agentpipe.core.constraint import Constraint, ConstraintType, ViolationAction
from agentpipe.core.pipeline import ExecutionStrategy, Pipeline
from agentpipe.core.task import Permissions, TaskDefinition
from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
from agentpipe.models.registry import ModelConfig, ModelRegistry
from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter

__all__ = [
    "Agent",
    "Condition",
    "Constraint",
    "ConstraintType",
    "Edge",
    "ExecutionStrategy",
    "ModelConfig",
    "ModelProvider",
    "ModelRegistry",
    "ModelResponse",
    "Permissions",
    "Pipeline",
    "StopReason",
    "TaskDefinition",
    "Tool",
    "ToolDefinition",
    "ToolParameter",
    "ViolationAction",
]
