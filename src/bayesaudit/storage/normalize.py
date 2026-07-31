"""Normalize trajectories and scores into long-form analysis tables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from bayesaudit.oversight.types import OversightRunResult
from bayesaudit.schemas import ScoreResult, Trajectory


def normalized_records(
    trajectory: Trajectory, score: ScoreResult | None = None
) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {
        "steps": [],
        "messages": [],
        "tool_calls": [],
        "constraint_snapshots": [],
        "detections": [],
        "interventions": [],
        "violations": [],
        "score_components": [],
        "usage": [],
        "errors": [],
        "constraint_registries": [],
        "constraint_envelopes": [],
        "mutation_events": [],
        "verification_events": [],
        "repair_events": [],
        "constraint_comparisons": [],
        "retention_metrics": [],
        "aggregation_provenance": [],
    }
    for step in trajectory.steps:
        tables["steps"].append(
            {
                "trajectory_id": trajectory.trajectory_id,
                "run_id": trajectory.run_id,
                "step_id": step.step_id,
                "sequence_index": step.sequence_index,
                "parent_step_id": step.parent_step_id,
                "depth": step.depth,
                "kind": step.kind,
                "agent_id": step.agent_id,
                "role": step.role,
            }
        )
        for message in step.input_messages:
            tables["messages"].append(
                {
                    "trajectory_id": trajectory.trajectory_id,
                    "step_id": step.step_id,
                    "role": message.role,
                    "agent_id": message.agent_id,
                    "content": message.content,
                    "message_kind": "input",
                }
            )
        if step.model_response is not None:
            tables["messages"].append(
                {
                    "trajectory_id": trajectory.trajectory_id,
                    "step_id": step.step_id,
                    "role": step.model_response.message.role,
                    "agent_id": step.model_response.message.agent_id,
                    "content": step.model_response.message.content,
                    "message_kind": "model_response",
                }
            )
        for call in step.tool_calls:
            record = call.model_dump(mode="json")
            record.update({"trajectory_id": trajectory.trajectory_id, "step_id": step.step_id})
            tables["tool_calls"].append(record)
        for snapshot in step.constraint_snapshots:
            record = snapshot.model_dump(mode="json")
            record.update({"trajectory_id": trajectory.trajectory_id, "step_id": step.step_id})
            tables["constraint_snapshots"].append(record)
        for detection in step.detections:
            record = detection.model_dump(mode="json")
            record.update({"trajectory_id": trajectory.trajectory_id, "step_id": step.step_id})
            tables["detections"].append(record)
        for intervention in step.interventions:
            record = intervention.model_dump(mode="json")
            record.update({"trajectory_id": trajectory.trajectory_id, "step_id": step.step_id})
            tables["interventions"].append(record)
    if score is not None:
        for violation in score.violations:
            record = violation.model_dump(mode="json")
            record.update(
                {"trajectory_id": trajectory.trajectory_id, "task_id": trajectory.task_id}
            )
            tables["violations"].append(record)
        for name, value in score.component_scores.items():
            tables["score_components"].append(
                {
                    "trajectory_id": trajectory.trajectory_id,
                    "task_id": trajectory.task_id,
                    "component": name,
                    "value": value,
                }
            )
    tables["usage"].append(
        {
            "trajectory_id": trajectory.trajectory_id,
            "run_id": trajectory.run_id,
            **trajectory.usage_totals.model_dump(mode="json"),
        }
    )
    if trajectory.error is not None:
        tables["errors"].append(
            {
                "trajectory_id": trajectory.trajectory_id,
                "run_id": trajectory.run_id,
                **trajectory.error.model_dump(mode="json"),
            }
        )
    inheritance = trajectory.metadata.get("inheritance")
    if isinstance(inheritance, dict):
        registry = inheritance.get("registry")
        if isinstance(registry, dict):
            tables["constraint_registries"].append(
                {
                    "trajectory_id": trajectory.trajectory_id,
                    "run_id": trajectory.run_id,
                    **registry,
                }
            )
        _extend_inheritance_table(
            tables,
            "constraint_envelopes",
            trajectory,
            inheritance.get("envelopes"),
        )
        _extend_inheritance_table(
            tables,
            "mutation_events",
            trajectory,
            inheritance.get("mutation_events"),
        )
        _extend_inheritance_table(
            tables,
            "verification_events",
            trajectory,
            inheritance.get("verification_events"),
        )
        _extend_inheritance_table(
            tables,
            "repair_events",
            trajectory,
            inheritance.get("repair_events"),
        )
        _extend_inheritance_table(
            tables,
            "constraint_comparisons",
            trajectory,
            inheritance.get("comparisons"),
        )
        _extend_inheritance_table(
            tables,
            "retention_metrics",
            trajectory,
            inheritance.get("metrics"),
        )
        aggregation = inheritance.get("aggregation_provenance")
        if isinstance(aggregation, dict):
            tables["aggregation_provenance"].append(
                {
                    "trajectory_id": trajectory.trajectory_id,
                    "run_id": trajectory.run_id,
                    **aggregation,
                }
            )
    return tables


def write_parquet_tables(root: Path, tables: dict[str, list[dict[str, Any]]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        if rows:
            pd.DataFrame([_flatten(row) for row in rows]).to_parquet(
                root / f"{name}.parquet", index=False
            )


def normalized_oversight_records(result: OversightRunResult) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {
        "oversight_policy_runs": [
            {
                "policy_run_id": result.policy_run_id,
                "trajectory_id": result.trajectory_id,
                "run_id": result.run_id,
                "experiment_id": result.experiment_id,
                "policy_name": result.policy_name,
                "policy_version": result.policy_version,
                "mode": result.mode,
                "synthetic": result.synthetic,
                "metadata": result.metadata,
            }
        ],
        "oversight_audit_decisions": [],
        "oversight_audit_feedback": [],
        "oversight_audit_findings": [],
        "oversight_intervention_decisions": [],
        "oversight_intervention_outcomes": [],
        "oversight_budget_transactions": [],
        "oversight_detection_matches": [],
        "oversight_counterfactuals": [],
        "oversight_metrics": [],
    }
    for decision in result.decisions:
        tables["oversight_audit_decisions"].append(
            {"policy_run_id": result.policy_run_id, **decision.model_dump(mode="json")}
        )
    for feedback in result.feedback:
        payload = feedback.model_dump(mode="json")
        findings = payload.pop("findings")
        tables["oversight_audit_feedback"].append(
            {"policy_run_id": result.policy_run_id, **payload}
        )
        for index, finding in enumerate(findings):
            tables["oversight_audit_findings"].append(
                {
                    "policy_run_id": result.policy_run_id,
                    "audit_id": feedback.audit_id,
                    "finding_index": index,
                    **finding,
                }
            )
    for intervention_decision in result.intervention_decisions:
        tables["oversight_intervention_decisions"].append(
            {
                "policy_run_id": result.policy_run_id,
                **intervention_decision.model_dump(mode="json"),
            }
        )
    for outcome in result.intervention_outcomes:
        tables["oversight_intervention_outcomes"].append(
            {"policy_run_id": result.policy_run_id, **outcome.model_dump(mode="json")}
        )
    for transaction in result.budget_transactions:
        tables["oversight_budget_transactions"].append(
            {"policy_run_id": result.policy_run_id, **transaction.model_dump(mode="json")}
        )
    for match in result.detection_matches:
        tables["oversight_detection_matches"].append(
            {"policy_run_id": result.policy_run_id, **match.model_dump(mode="json")}
        )
    for counterfactual in result.counterfactuals:
        tables["oversight_counterfactuals"].append(
            {"policy_run_id": result.policy_run_id, **counterfactual.model_dump(mode="json")}
        )
    for metric in result.metrics:
        tables["oversight_metrics"].append(
            {"policy_run_id": result.policy_run_id, **metric.model_dump(mode="json")}
        )
    return tables


def merge_tables(*table_sets: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for tables in table_sets:
        for name, rows in tables.items():
            merged.setdefault(name, []).extend(rows)
    return merged


def _flatten(row: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            flattened[key] = json.dumps(value, sort_keys=True, default=str)
        else:
            flattened[key] = value
    return flattened


def _extend_inheritance_table(
    tables: dict[str, list[dict[str, Any]]],
    table_name: str,
    trajectory: Trajectory,
    rows: object,
) -> None:
    if not isinstance(rows, list):
        return
    for row in rows:
        if isinstance(row, dict):
            tables[table_name].append(
                {
                    "trajectory_id": trajectory.trajectory_id,
                    "run_id": trajectory.run_id,
                    **row,
                }
            )
