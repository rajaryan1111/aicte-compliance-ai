"""Regression tests for the server-side rule activation gate.

All rules here are synthetic test fixtures. No AICTE rule is defined, activated
or evaluated by this repository.
"""
from __future__ import annotations

import re
import warnings
from datetime import date
from pathlib import Path

import pytest

from backend.app.rule_catalog import (
    RuleActivationError,
    RuleLifecycle,
    RuleRegistry,
    RuleVersionDraft,
    activation_blockers,
)

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _payload():
    from backend.tests.test_rule_catalog import valid_rule_payload

    return valid_rule_payload()


def _in_review_rule():
    return RuleVersionDraft.model_validate({**_payload(), "lifecycle": "in_review"})


def test_registry_starts_empty_and_has_no_evaluator():
    registry = RuleRegistry()

    assert registry.active_rules() == ()
    assert len(registry) == 0
    for forbidden in ("evaluate", "execute", "run"):
        assert not hasattr(registry, forbidden)


def test_no_rule_instances_are_defined_in_application_code():
    """Guard against shipping a real (or self-declared active) rule by accident."""
    offenders: list[str] = []
    for path in APP_DIR.glob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if line.lstrip().startswith("class "):
                continue
            if re.search(r"\bRuleVersionDraft\s*\(", line):
                offenders.append(f"{path.name}:{number}")

    assert offenders == []


def test_gate_activates_only_reviewed_verified_approved_rule():
    registry = RuleRegistry()
    rule = _in_review_rule()

    active = registry.activate(rule)

    assert active.lifecycle is RuleLifecycle.ACTIVE
    stored = registry.get_active("TEST_DOCUMENT_RULE")
    assert stored is not None
    assert stored == active
    assert stored is not active  # snapshots are detached copies
    assert [item.version for item in registry.active_rules()] == [1]


def test_gate_rejects_self_declared_active_lifecycle():
    registry = RuleRegistry()
    active_payload = {**_payload(), "lifecycle": "active"}
    already_active = RuleVersionDraft.model_validate(active_payload)

    with pytest.raises(RuleActivationError, match="draft or in-review"):
        registry.activate(already_active)
    assert len(registry) == 0


def test_gate_rejects_rule_with_unverified_source_even_if_validators_bypassed():
    registry = RuleRegistry()
    rule = _in_review_rule()
    tampered = rule.model_copy(
        update={
            "source_provenance": rule.source_provenance.model_copy(
                update={
                    "status": "unverified",
                    "verified_by": None,
                    "verified_at": None,
                }
            )
        }
    )

    with pytest.raises(RuleActivationError, match="verified"):
        registry.activate(tampered)
    assert len(registry) == 0


def test_gate_rejects_rule_without_approval_even_if_validators_bypassed():
    registry = RuleRegistry()
    rule = _in_review_rule()
    unapproved = rule.model_copy(update={"approval": None})

    with pytest.raises(RuleActivationError, match="approval record"):
        registry.activate(unapproved)
    assert len(registry) == 0


def test_gate_rejects_rejected_approval_decision():
    registry = RuleRegistry()
    rule = _in_review_rule()
    rejected = rule.model_copy(
        update={"approval": rule.approval.model_copy(update={"decision": "rejected"})}
    )

    with pytest.raises(RuleActivationError, match="approved"):
        registry.activate(rejected)
    assert len(registry) == 0


def test_gate_rejects_missing_effective_date():
    registry = RuleRegistry()
    rule = _in_review_rule().model_copy(update={"effective_from": None})

    with pytest.raises(RuleActivationError, match="effective_from"):
        registry.activate(rule)


def test_gate_rejects_incomplete_test_coverage():
    registry = RuleRegistry()
    rule = _in_review_rule()
    rule = rule.model_copy(update={"test_cases": rule.test_cases[:3]})

    with pytest.raises(RuleActivationError, match="exception"):
        registry.activate(rule)


def test_gate_refuses_duplicate_active_version():
    registry = RuleRegistry()
    registry.activate(_in_review_rule())

    with pytest.raises(RuleActivationError, match="already active"):
        registry.activate(_in_review_rule())

    assert len(registry) == 1


def test_gate_refuses_second_active_version_of_same_rule():
    registry = RuleRegistry()
    registry.activate(_in_review_rule())

    payload = {**_payload(), "version": 2, "lifecycle": "in_review"}
    second_version = RuleVersionDraft.model_validate(payload)

    with pytest.raises(RuleActivationError, match="supersession is not implemented"):
        registry.activate(second_version)

    assert [rule.version for rule in registry.active_rules()] == [1]


def test_gate_activates_rejected_draft_only_after_approval_changes_to_new_version():
    registry = RuleRegistry()
    rejected = RuleVersionDraft.model_validate(
        {
            **_payload(),
            "lifecycle": "in_review",
            "approval": {
                **_payload()["approval"],
                "decision": "rejected",
            },
        }
    )

    with pytest.raises(RuleActivationError):
        registry.activate(rejected)

    approved_v2 = RuleVersionDraft.model_validate(
        {**_payload(), "version": 2, "lifecycle": "in_review"}
    )
    active = registry.activate(approved_v2)

    assert active.version == 2
    assert registry.get_active("TEST_DOCUMENT_RULE").version == 2


# --- regression tests added by the 2026-10-23 foundation audit -------------
# Each case below reproduced a real gap in the gate before the fix.


def test_gate_raises_rule_activation_error_for_tampered_objects():
    """model_construct bypasses must fail as gate errors, not AttributeError."""
    registry = RuleRegistry()
    rule = _in_review_rule()
    base = dict(rule.__dict__)

    tampered_variants = {
        "string lifecycle": {**base, "lifecycle": "active"},
        "missing provenance": {
            key: value
            for key, value in base.items()
            if key != "source_provenance"
        },
        "missing approval": {**base, "approval": None},
        "null test cases": {**base, "test_cases": None},
        "string approval": {**base, "approval": "approved"},
    }

    for name, attributes in tampered_variants.items():
        candidate = RuleVersionDraft.model_construct(**attributes)
        with pytest.raises(RuleActivationError):
            registry.activate(candidate)
        assert len(registry) == 0, name


def test_gate_rejects_non_model_objects():
    with pytest.raises(RuleActivationError, match="RuleVersionDraft"):
        RuleRegistry().activate({"rule_id": "TEST_DOCUMENT_RULE"})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RuleVersionDraft"):
        activation_blockers({"lifecycle": "in_review"})  # type: ignore[arg-type]


def test_gate_accepts_plain_string_lifecycle_after_revalidation():
    """A validated-equivalent object built with a plain string still revalidates."""
    registry = RuleRegistry()
    rule = _in_review_rule()
    constructed = RuleVersionDraft.model_construct(
        **{**rule.__dict__, "lifecycle": "in_review"}
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # model_dump warns about the raw string
        active = registry.activate(constructed)

    assert active.lifecycle is RuleLifecycle.ACTIVE
    assert len(registry) == 1


def test_returned_active_snapshot_cannot_mutate_registry_state():
    registry = RuleRegistry()
    active = registry.activate(_in_review_rule())

    active.lifecycle = RuleLifecycle.DRAFT
    active.test_cases[0].category = "exception"
    active.limitations.append("mutated after activation")

    stored = registry.get_active("TEST_DOCUMENT_RULE")
    assert stored is not None
    assert stored.lifecycle is RuleLifecycle.ACTIVE
    assert stored.test_cases[0].category == "positive"
    assert "mutated after activation" not in stored.limitations


def test_active_rules_returns_detached_copies():
    registry = RuleRegistry()
    registry.activate(_in_review_rule())

    first = registry.active_rules()[0]
    first.approval = None

    second = registry.active_rules()[0]
    assert second.approval is not None
    assert second.approval.decision.value == "approved"


def test_failed_activation_leaves_registry_unchanged():
    registry = RuleRegistry()
    registry.activate(_in_review_rule())
    before = registry.active_rules()

    with pytest.raises(RuleActivationError):
        registry.activate(_in_review_rule().model_copy(update={"approval": None}))

    assert registry.active_rules() == before
    assert len(registry) == 1


def test_failed_activation_on_empty_registry_creates_no_entry():
    registry = RuleRegistry()

    with pytest.raises(RuleActivationError):
        registry.activate(_in_review_rule().model_copy(update={"effective_from": None}))

    assert len(registry) == 0


def test_gate_blocks_effective_date_before_publication():
    registry = RuleRegistry()
    rule = _in_review_rule().model_copy(
        update={"publication_date": date(2026, 6, 1), "effective_from": date(2026, 1, 1)}
    )

    with pytest.raises(RuleActivationError, match="publication_date"):
        registry.activate(rule)
    assert len(registry) == 0


def test_gate_blocks_effective_to_before_effective_from_without_revalidation():
    registry = RuleRegistry()
    rule = _in_review_rule().model_copy(
        update={"effective_from": date(2026, 5, 1), "effective_to": date(2026, 4, 1)}
    )

    with pytest.raises(RuleActivationError, match="effective_to"):
        registry.activate(rule)
