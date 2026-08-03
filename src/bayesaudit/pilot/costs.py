"""Versioned Decimal cost accounting for Phase 7 provider runs."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.types import (
    CostAccountingRecord,
    CostReconciliationStatus,
    PricingRecord,
    ProviderAttemptCostInput,
)

PRICING_ROOT = Path("configs/pricing")
PER_MILLION = Decimal("1000000")


def load_pricing_record(
    provider: str, model_identifier: str, *, pricing_root: Path = PRICING_ROOT
) -> PricingRecord:
    for path in sorted(pricing_root.glob("*.yaml")):
        record = load_pricing_record_path(path)
        if record.provider == provider and record.model_identifier == model_identifier:
            return record
    raise KeyError(f"missing pricing record for provider={provider} model={model_identifier}")


def load_pricing_record_path(path: Path) -> PricingRecord:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"pricing YAML must be a mapping: {path}")
    pricing_payload = payload.get("pricing", payload)
    if not isinstance(pricing_payload, dict):
        raise ValueError(f"pricing YAML must contain a pricing mapping: {path}")
    declared_hash = pricing_payload.get("configuration_hash")
    hash_payload = {
        key: value for key, value in pricing_payload.items() if key != "configuration_hash"
    }
    calculated_hash = canonical_json_hash(hash_payload)
    if declared_hash and declared_hash != calculated_hash:
        raise ValueError(
            f"pricing configuration hash mismatch for {path}: "
            f"declared {declared_hash}, calculated {calculated_hash}"
        )
    return PricingRecord.model_validate({**pricing_payload, "configuration_hash": calculated_hash})


def calculate_cost_accounting(
    *,
    provider: str,
    model_identifier: str,
    attempts: list[ProviderAttemptCostInput],
    pricing: PricingRecord | None,
    estimated_cost_usd: Decimal | str | int | float | None = None,
    conservative_upper_bound_usd: Decimal | str | int | float | None = None,
    billed_cost_usd: Decimal | str | int | float | None = None,
) -> CostAccountingRecord:
    estimated = _optional_decimal(estimated_cost_usd)
    upper_bound = _optional_decimal(conservative_upper_bound_usd)
    billed_cost = _optional_decimal(billed_cost_usd)
    billed_attempts = [
        attempt for attempt in attempts if attempt.billed and attempt.status != "cached"
    ]
    cache_hits = [attempt for attempt in attempts if attempt.status == "cached"]
    unbilled_attempt_count = len(attempts) - len(billed_attempts)
    provider_reported_costs = [
        attempt.provider_reported_cost_usd
        for attempt in billed_attempts
        if attempt.provider_reported_cost_usd is not None
    ]
    provider_reported_cost = (
        sum(provider_reported_costs, Decimal("0")) if provider_reported_costs else None
    )
    if billed_cost is not None:
        status: CostReconciliationStatus = "externally_billed"
    elif provider_reported_cost is not None:
        status = "provider_reported"
    else:
        status = "unreconciled"

    if not billed_attempts:
        token_cost = Decimal("0") if cache_hits else None
        if status == "unreconciled":
            status = (
                "token_derived"
                if cache_hits
                else ("estimated_only" if estimated is not None else "unreconciled")
            )
        return CostAccountingRecord(
            provider=provider,
            model_identifier=model_identifier,
            estimated_cost_usd=estimated,
            token_derived_cost_usd=token_cost,
            provider_reported_cost_usd=provider_reported_cost,
            billed_cost_usd=billed_cost,
            conservative_upper_bound_usd=upper_bound,
            cost_reconciliation_status=status,
            billed_attempt_count=0,
            unbilled_attempt_count=unbilled_attempt_count,
            cache_hit_count=len(cache_hits),
            notes=["cache hits add zero incremental provider cost"] if cache_hits else [],
        )

    if pricing is None:
        if status == "unreconciled":
            status = "estimated_only" if estimated is not None else "unreconciled"
        return CostAccountingRecord(
            provider=provider,
            model_identifier=model_identifier,
            estimated_cost_usd=estimated,
            provider_reported_cost_usd=provider_reported_cost,
            billed_cost_usd=billed_cost,
            conservative_upper_bound_usd=upper_bound,
            cost_reconciliation_status=status,
            billed_attempt_count=len(billed_attempts),
            unbilled_attempt_count=unbilled_attempt_count,
            cache_hit_count=len(cache_hits),
            notes=["pricing record unavailable; token-derived cost not calculated"],
        )
    if pricing.provider != provider or pricing.model_identifier != model_identifier:
        raise ValueError("pricing record does not match provider/model")

    usage_attempts = [attempt for attempt in billed_attempts if attempt.usage_present]
    if not usage_attempts:
        if status == "unreconciled":
            status = "estimated_only" if estimated is not None else "unreconciled"
        return CostAccountingRecord(
            provider=provider,
            model_identifier=model_identifier,
            pricing_table_version=pricing.pricing_table_version,
            pricing_configuration_hash=pricing.configuration_hash,
            estimated_cost_usd=estimated,
            provider_reported_cost_usd=provider_reported_cost,
            billed_cost_usd=billed_cost,
            conservative_upper_bound_usd=upper_bound,
            cost_reconciliation_status=status,
            billed_attempt_count=len(billed_attempts),
            unbilled_attempt_count=unbilled_attempt_count,
            cache_hit_count=len(cache_hits),
            notes=["provider usage unavailable; token-derived cost not calculated"],
        )

    input_tokens = sum(max(0, attempt.input_tokens) for attempt in usage_attempts)
    cached_input_tokens = sum(max(0, attempt.cached_input_tokens) for attempt in usage_attempts)
    cached_input_tokens = min(cached_input_tokens, input_tokens)
    output_tokens = sum(max(0, attempt.output_tokens) for attempt in usage_attempts)
    reasoning_tokens = sum(max(0, attempt.reasoning_tokens) for attempt in usage_attempts)
    noncached_input_tokens = input_tokens - cached_input_tokens
    input_cost = (
        Decimal(noncached_input_tokens) * pricing.input_price_per_million_tokens / PER_MILLION
    )
    cached_input_cost = (
        Decimal(cached_input_tokens)
        * pricing.cached_input_price_per_million_tokens
        / PER_MILLION
    )
    output_cost = Decimal(output_tokens) * pricing.output_price_per_million_tokens / PER_MILLION
    subtotal = input_cost + cached_input_cost + output_cost
    regional_uplift = subtotal * (pricing.regional_uplift_multiplier - Decimal("1"))
    fixed_fee = pricing.additional_fixed_fee_usd
    fixed_tool_charge = pricing.fixed_tool_charge_usd
    token_cost = subtotal + regional_uplift + fixed_fee + fixed_tool_charge
    if status == "unreconciled":
        status = "token_derived"
    notes = []
    if reasoning_tokens:
        notes.append("reasoning tokens are usage metadata and are not double counted")
    if cache_hits:
        notes.append("cache hits add zero incremental provider cost")
    return CostAccountingRecord(
        provider=provider,
        model_identifier=model_identifier,
        pricing_table_version=pricing.pricing_table_version,
        pricing_configuration_hash=pricing.configuration_hash,
        estimated_cost_usd=estimated,
        token_derived_cost_usd=token_cost,
        provider_reported_cost_usd=provider_reported_cost,
        billed_cost_usd=billed_cost,
        conservative_upper_bound_usd=upper_bound,
        cost_reconciliation_status=status,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        noncached_input_tokens=noncached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        input_cost_usd=input_cost,
        cached_input_cost_usd=cached_input_cost,
        output_cost_usd=output_cost,
        regional_uplift_usd=regional_uplift,
        additional_fixed_fee_usd=fixed_fee,
        fixed_tool_charge_usd=fixed_tool_charge,
        billed_attempt_count=len(billed_attempts),
        unbilled_attempt_count=unbilled_attempt_count,
        cache_hit_count=len(cache_hits),
        notes=notes,
    )


def response_attempt_from_usage(
    payload: dict[str, Any], *, status: str = "completed"
) -> ProviderAttemptCostInput:
    usage_present = bool(payload)
    input_tokens = int(payload.get("input_tokens", 0) or 0)
    cached_input_tokens = int(payload.get("cached_input_tokens", 0) or 0)
    output_tokens = int(payload.get("output_tokens", 0) or 0)
    reasoning_tokens = int(payload.get("reasoning_tokens", 0) or 0)
    if status not in {"completed", "failed", "cached"}:
        raise ValueError(f"unsupported attempt status: {status}")
    return ProviderAttemptCostInput(
        status=status,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        usage_present=usage_present,
        billed=status != "cached",
    )


def cost_record_json(record: CostAccountingRecord) -> dict[str, Any]:
    return record.model_dump(mode="json")


def _optional_decimal(value: Decimal | str | int | float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
