"""
Workflow schemas — typed contracts for multi-agent task coordination.

A Workflow is a named sequence of agent tasks.
Each task has a role, input, and produces an output.
The orchestrator coordinates task execution.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentTask(BaseModel):
    """A single task within a workflow, assigned to a specific agent role."""

    task_id: str
    agent_role: str  # "planner" | "coding" | "retrieval" | "debugging" | "devops"
    instruction: str
    depends_on: list[str] = Field(default_factory=list)  # task_ids this depends on
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    error: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None


class WorkflowDefinition(BaseModel):
    """A named workflow with a sequence of agent tasks."""

    workflow_id: str
    name: str
    description: str
    tasks: list[AgentTask]
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )


class WorkflowRun(BaseModel):
    """The execution state of a workflow."""

    run_id: str
    workflow_id: str
    session_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    tasks: list[AgentTask] = Field(default_factory=list)
    final_output: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    completed_at: datetime.datetime | None = None


class WorkflowRequest(BaseModel):
    """API request to trigger a workflow."""

    workflow_name: str
    session_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowResponse(BaseModel):
    """API response after triggering a workflow."""

    run_id: str
    workflow_id: str
    status: WorkflowStatus
    message: str
