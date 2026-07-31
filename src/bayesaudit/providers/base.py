"""Provider-call safety gates and cost estimation."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, NonNegativeFloat, NonNegativeInt

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.monitoring.types import ProviderCallManifest
from bayesaudit.schemas import StrictModel
from bayesaudit.storage.jsonl import write_json_atomic


class ProviderConfig(StrictModel):
    provider_name: str = "mock"
    model_identifier: str | None = None
    allow_provider_calls: bool = False
    dry_run: bool = True
    max_cost: NonNegativeFloat = 0.0
    max_tokens: NonNegativeInt = 1000
    trajectory_ceiling: NonNegativeInt = 1
    request_count: NonNegativeInt = 1
    estimated_input_tokens_per_request: NonNegativeInt = 250
    estimated_output_tokens_per_request: NonNegativeInt = 100
    estimated_cost_per_1k_tokens: NonNegativeFloat = 0.0
    output_root: Path = Path("results/tables/provider_manifests")
    provider_metadata: dict[str, str] = Field(default_factory=dict)


def estimate_provider_cost(config: ProviderConfig) -> ProviderCallManifest:
    tokens_per_request = (
        config.estimated_input_tokens_per_request + config.estimated_output_tokens_per_request
    )
    estimated_tokens = tokens_per_request * config.request_count
    estimated_cost = estimated_tokens / 1000.0 * config.estimated_cost_per_1k_tokens
    status = "dry_run" if config.dry_run else "ready"
    if config.provider_name != "mock" and not config.allow_provider_calls:
        status = "blocked"
    if estimated_cost > config.max_cost or estimated_tokens > config.max_tokens:
        status = "blocked"
    manifest = ProviderCallManifest(
        provider_manifest_id="provider_" + canonical_json_hash(config.model_dump(mode="json"))[:16],
        provider_name=config.provider_name,
        model_identifier=config.model_identifier,
        allow_provider_calls=config.allow_provider_calls,
        dry_run=config.dry_run,
        estimated_cost=estimated_cost,
        max_cost=config.max_cost,
        estimated_tokens=estimated_tokens,
        max_tokens=config.max_tokens,
        trajectory_ceiling=config.trajectory_ceiling,
        request_count=config.request_count,
        status=status,
    )
    config.output_root.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        config.output_root / f"{manifest.provider_manifest_id}.json",
        manifest.model_dump(mode="json"),
    )
    return manifest


def assert_provider_allowed(config: ProviderConfig) -> None:
    manifest = estimate_provider_cost(config)
    if manifest.status == "blocked":
        raise PermissionError("provider calls are blocked by permission, token, or cost ceiling")
