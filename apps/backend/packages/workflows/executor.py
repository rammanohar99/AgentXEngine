"""
Workflow executor — runs a WorkflowRun by coordinating agent tasks.

Execution model:
- Tasks with no dependencies run first (in parallel where possible)
- Tasks with dependencies run after their dependencies complete
- Each task is delegated to the appropriate specialist agent
- Results from completed tasks are available to dependent tasks

Phase 6.1 fix: Correct task failure detection.
Previously, when a task's LLM call failed, the runtime emitted an ERROR event
and returned empty text. The executor collected empty text and marked the task
COMPLETE. A task that produced no output due to an error is FAILED, not COMPLETE.

Fix: Detect ERROR events from the runtime and mark the task as FAILED.

Usage:
    executor = WorkflowExecutor(orchestrator)
    run = await executor.execute(workflow_run)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from packages.workflows.schemas import AgentTask, TaskStatus, WorkflowRun, WorkflowStatus

logger = structlog.get_logger(__name__)


class WorkflowExecutor:
    """
    Executes a WorkflowRun by running tasks in dependency order.

    Injected with an Orchestrator that handles agent delegation.
    """

    def __init__(self, orchestrator: object) -> None:
        self._orchestrator = orchestrator

    async def execute(self, run: WorkflowRun) -> WorkflowRun:
        """
        Execute all tasks in the workflow run.

        Returns the updated WorkflowRun with task results.
        """
        run.status = WorkflowStatus.RUNNING
        logger.info("workflow_run_start", run_id=run.run_id, task_count=len(run.tasks))

        completed_results: dict[str, str] = {}

        try:
            # Simple topological execution — process tasks in order,
            # skipping those whose dependencies aren't met yet
            remaining = list(run.tasks)
            max_iterations = len(remaining) * 2  # Prevent infinite loops
            iteration = 0

            while remaining and iteration < max_iterations:
                iteration += 1
                made_progress = False

                for task in list(remaining):
                    # Check if all dependencies are complete
                    deps_met = all(
                        dep_id in completed_results for dep_id in task.depends_on
                    )
                    if not deps_met:
                        continue

                    # Build task instruction with dependency results
                    instruction = self._build_task_instruction(task, completed_results)

                    # Execute the task
                    result = await self._run_task(task, instruction, run.session_id)
                    completed_results[task.task_id] = result
                    remaining.remove(task)
                    made_progress = True

                if not made_progress:
                    # Circular dependency or unresolvable — fail remaining tasks
                    for task in remaining:
                        task.status = TaskStatus.FAILED
                        task.error = "Dependency cycle or unresolvable dependency"
                    break

            # Determine final output from the last completed task
            if run.tasks:
                last_task = run.tasks[-1]
                run.final_output = completed_results.get(last_task.task_id, "")

            # Check if all tasks completed successfully
            failed_tasks = [t for t in run.tasks if t.status == TaskStatus.FAILED]
            run.status = WorkflowStatus.FAILED if failed_tasks else WorkflowStatus.COMPLETE
            run.completed_at = datetime.now(timezone.utc)

            logger.info(
                "workflow_run_complete",
                run_id=run.run_id,
                status=run.status,
                failed_tasks=len(failed_tasks),
            )

        except Exception as exc:
            run.status = WorkflowStatus.FAILED
            run.completed_at = datetime.now(timezone.utc)
            logger.error("workflow_run_failed", run_id=run.run_id, error=str(exc))

        return run

    async def _run_task(
        self, task: AgentTask, instruction: str, session_id: str
    ) -> str:
        """
        Execute a single task using the appropriate specialist agent.

        Phase 6.1 fix: Detect ERROR events from the runtime and mark the task
        as FAILED. Previously, a failed LLM call caused the runtime to emit an
        ERROR event and return empty text. The executor collected empty text and
        marked the task COMPLETE — incorrect. A task that produced no output due
        to a runtime error is FAILED, not COMPLETE.
        """
        from packages.agents.schemas import AgentEventType

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)

        logger.info(
            "workflow_task_start",
            task_id=task.task_id,
            agent_role=task.agent_role,
        )

        try:
            result = ""
            error_content: str | None = None

            async for event in self._orchestrator.run(
                session_id=f"{session_id}-task-{task.task_id}",
                history=[],
                user_message=instruction,
            ):
                if event.type == AgentEventType.TEXT and event.content:
                    result += event.content
                elif event.type == AgentEventType.ERROR and event.content:
                    # Capture the error — do not treat this as a successful result
                    error_content = event.content
                    logger.warning(
                        "workflow_task_runtime_error",
                        task_id=task.task_id,
                        error=event.content,
                    )

            # A task is FAILED if the runtime emitted an ERROR event,
            # regardless of whether any TEXT was also produced.
            if error_content is not None:
                task.status = TaskStatus.FAILED
                task.error = error_content
                task.completed_at = datetime.now(timezone.utc)
                logger.error(
                    "workflow_task_failed_via_error_event",
                    task_id=task.task_id,
                    error=error_content,
                )
                return f"Task failed: {error_content}"

            task.result = result
            task.status = TaskStatus.COMPLETE
            task.completed_at = datetime.now(timezone.utc)

            logger.info(
                "workflow_task_complete",
                task_id=task.task_id,
                result_length=len(result),
            )
            return result

        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.completed_at = datetime.now(timezone.utc)
            logger.error("workflow_task_failed", task_id=task.task_id, error=str(exc))
            return f"Task failed: {exc}"

    def _build_task_instruction(
        self, task: AgentTask, completed_results: dict[str, str]
    ) -> str:
        """Build the full instruction for a task, including dependency results."""
        if not task.depends_on:
            return task.instruction

        context_parts = [task.instruction, "\n\nContext from previous tasks:"]
        for dep_id in task.depends_on:
            result = completed_results.get(dep_id, "")
            if result:
                context_parts.append(f"\n[Task {dep_id} result]\n{result[:1000]}")

        return "\n".join(context_parts)
