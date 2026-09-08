"""Fail-closed tests for SELECT-V7-CANDIDATE-FORMAL-V1.

The protocol was written after its author saw the development result, so the
tests here are mostly about the rule being unable to bend: no deciding on
inspected data, no deciding without authorization, no deciding while the
measured execution preconditions stand, and no candidate from a missing input.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

import environment_lock as lock_module
from environment_lock import SYNTHETIC_LOCK_CLASS, capture_environment_lock
import v7_candidate_selection_contract as sel
from v7_candidate_selection_contract import (
    CONDITION_IDS,
    SCOPE_SELECTION,
    SCOPE_SELF_CHECK,
    DEFAULT_PROTOCOL,
    PROTOCOL_SHA256,
    SEED_CLASS_DEVELOPMENT_EXHAUSTED,
    SEED_CLASS_RETIRED,
    SEED_CLASS_SEALED_FORMAL,
    STATE_FAIL,
    STATE_NOT_APPLICABLE,
    STATE_NOT_REACHED,
    STATE_PASS,
    STATUS_NO_CANDIDATE,
    SelectionError,
    assert_executable,
    check_rule_on_development_evidence,
    evaluate_conditions,
    load_protocol,
    select_candidate,
    unresolved_execution_preconditions,
    validate_protocol,
)


BACKEND_ROOT = Path(__file__).resolve().parent
CONTRACT_PATH = BACKEND_ROOT / "v7_candidate_selection_contract.py"
DEV_SUMMARY = (
    BACKEND_ROOT / "seed_variance_evidence" / "2026-09-08" / "analysis" / "seed_variance_summary.json"
)
REFERENCE_ARM = "V7A_REWARD_ONLY"
CANDIDATE_ARM = "V7B_REDUCED_JOINT_ENVELOPE"


@pytest.fixture(scope="module")
def protocol() -> dict:
    return load_protocol(DEFAULT_PROTOCOL)


@pytest.fixture(scope="module")
def dev_summary() -> dict:
    return json.loads(DEV_SUMMARY.read_text(encoding="utf-8"))


@pytest.fixture
def authorization() -> dict:
    return {
        "authority": "project owner",
        "reference": "AUTH-TEST-0001",
        "granted_at_utc": "2026-09-08T00:00:00Z",
        "scope_git_sha": "c" * 40,
        "protocol_sha256": PROTOCOL_SHA256,
    }


def _condition(conditions: list[dict], identifier: str) -> dict:
    return next(item for item in conditions if item["id"] == identifier)


def _formal_summary(dev_summary: dict) -> dict:
    """A hypothetical clean FORMAL summary, so the accept path is reachable at all."""
    payload = deepcopy(dev_summary)
    payload["evaluation_seed_first"] = 20000
    payload["evaluation_seed_last"] = 20029
    for replicate in payload["replicates"]:
        for cell in replicate["arms"]:
            episodes = cell["episode_count"]
            cell["cell_state"] = "POINT_IDENTIFIED"
            cell["comparability_counts"] = {
                "COMPARABLE": episodes,
                "EXPOSURE_CENSORED": 0,
                "METHOD_FAILURE_NOT_CENSORING": 0,
            }
    for candidate in payload["candidates"]:
        method_level = candidate["method_level"]
        method_level["theta_bound_pp"] = {
            "state": "OBSERVED",
            "lower_pp": -13.5,
            "upper_pp": -12.4,
            "width_pp": 1.1,
            "reason": None,
        }
        method_level["between_replicate_sd_pp"] = 1.9
        method_level["between_replicate_sd_reason"] = None
    return payload


def _gate_report(replicates: int = 5) -> dict:
    return {
        arm: {
            str(index): {"all_gates_passed": True, "required_null_or_nonfinite": False}
            for index in range(replicates)
        }
        for arm in (REFERENCE_ARM, CANDIDATE_ARM, "V7C_FILTERED_ACTION")
    }


# --------------------------------------------------------------------------- #
# SEL-01 the disclosure is load-bearing
# --------------------------------------------------------------------------- #


def test_protocol_loads_at_its_pinned_digest(protocol: dict) -> None:
    assert protocol["protocol_id"] == "SELECT-V7-CANDIDATE-FORMAL-V1"
    assert sel.sha256_file(DEFAULT_PROTOCOL) == PROTOCOL_SHA256


def test_protocol_declares_itself_not_preregistered(protocol: dict) -> None:
    """A post-hoc rule may be used only while it says it is post-hoc."""
    assert protocol["preregistered"] is False
    disclosure = protocol["post_hoc_disclosure"]
    assert "SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1" in disclosure["authored_after_seeing"]
    assert "-13.503408" in disclosure["known_at_freeze_time"]
    assert "never be described as preregistered" in disclosure["consequence"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p.update({"preregistered": True}), "preregistered"),
        (lambda p: p.pop("post_hoc_disclosure"), "post_hoc_disclosure"),
        (
            lambda p: p["post_hoc_disclosure"].update({"known_at_freeze_time": ""}),
            "known_at_freeze_time",
        ),
        (
            lambda p: p.update({"selected_candidate_arm_id": CANDIDATE_ARM}),
            "must not preselect",
        ),
        (lambda p: p.update({"paper_data_ready": True}), "paper_data_ready"),
        (
            lambda p: p["evaluation_data"].update({"permitted_seed_class": "DEVELOPMENT_EXHAUSTED"}),
            "only SEALED_FORMAL",
        ),
        (
            lambda p: p["evaluation_data"].update({"development_exhausted_seed_range": [19999, 20005]}),
            "overlaps the FORMAL range",
        ),
        (lambda p: p["authorization"].update({"required": False}), "require formal authorization"),
        (
            lambda p: p["decision_rule"].update({"default_outcome": "SELECT_BEST"}),
            "default decision outcome must be no candidate",
        ),
        (
            lambda p: p["decision_rule"].update({"single_application": False}),
            "single application",
        ),
        (
            lambda p: p["decision_rule"]["eligibility_conditions"].pop(),
            "eligibility conditions must be exactly",
        ),
    ],
)
def test_protocol_semantic_invariants(protocol: dict, mutate, message: str) -> None:
    payload = deepcopy(protocol)
    mutate(payload)
    with pytest.raises(SelectionError, match=message):
        validate_protocol(payload)


def test_protocol_digest_drift_fails_closed(tmp_path: Path, protocol: dict) -> None:
    edited = tmp_path / "protocol.json"
    payload = deepcopy(protocol)
    payload["decision_rule"]["tie_break"] = "pick the first"
    edited.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SelectionError, match="protocol digest drift"):
        load_protocol(edited)


# --------------------------------------------------------------------------- #
# SEL-06 executability was measured before the freeze
# --------------------------------------------------------------------------- #


def test_execution_preconditions_are_all_blocking_today(protocol: dict) -> None:
    blocking = unresolved_execution_preconditions(protocol)
    assert [item["id"] for item in blocking] == ["EP-01", "EP-02", "EP-03"]
    assert "SEALED_SEED_RANGE" in blocking[0]["finding"]
    assert "SEED_SCHEDULE_OVERRIDE_FORBIDDEN" in blocking[1]["finding"]
    assert "authorization" in blocking[2]["finding"]


def test_selection_refuses_while_preconditions_stand(protocol: dict) -> None:
    with pytest.raises(SelectionError, match="not executable, 3 unresolved precondition"):
        assert_executable(protocol)


def test_measured_preconditions_still_match_the_code() -> None:
    """The preconditions are claims about this repository; check them.

    A stale precondition would be worse than none: it would assert a blocker
    that no longer exists, or hide one that appeared.
    """
    import v7_exposure_audit_contract as audit

    assert 20000 in audit.SEALED_SEED_RANGE and 20029 in audit.SEALED_SEED_RANGE
    with pytest.raises(Exception, match="sealed"):
        audit._episode_exposure(
            {"evaluation_seed": 20000},
            {},
            [],
            [],
            "formal probe",
        )
    eval_source = (BACKEND_ROOT / "rl" / "eval_policy.py").read_text(encoding="utf-8")
    assert "V7_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN" in eval_source
    assert "SEEDVAR_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN" in eval_source


def test_precondition_digests_match_the_pinned_sources(protocol: dict) -> None:
    digests = protocol["execution_precondition_source_digests"]
    assert digests["verified_before_freeze"] is True
    assert sel.sha256_file(BACKEND_ROOT / "v7_exposure_audit_contract.py") == (
        digests["audit_contract_source_sha256"]
    )
    assert sel.sha256_file(BACKEND_ROOT / "rl" / "eval_policy.py") == (
        digests["evaluation_driver_source_sha256"]
    )


# --------------------------------------------------------------------------- #
# SEL-02 and SEL-03 authority to decide
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed_class", [SEED_CLASS_DEVELOPMENT_EXHAUSTED, SEED_CLASS_RETIRED])
def test_inspected_seed_classes_cannot_decide(
    protocol: dict, dev_summary: dict, seed_class: str
) -> None:
    conditions = evaluate_conditions(protocol, dev_summary, CANDIDATE_ARM, seed_class=seed_class)
    first = _condition(conditions, "SEL-C1")
    assert first["state"] == STATE_FAIL
    assert "only SEALED_FORMAL may decide" in first["detail"]
    assert all(
        _condition(conditions, identifier)["state"] == STATE_NOT_REACHED
        for identifier in CONDITION_IDS[1:]
    )


def test_unknown_seed_class_fails_closed(protocol: dict, dev_summary: dict) -> None:
    with pytest.raises(SelectionError, match="unknown seed class"):
        evaluate_conditions(protocol, dev_summary, CANDIDATE_ARM, seed_class="PROBABLY_FINE")


def test_unknown_scope_fails_closed(protocol: dict, dev_summary: dict) -> None:
    with pytest.raises(SelectionError, match="unknown evaluation scope"):
        evaluate_conditions(
            protocol,
            dev_summary,
            CANDIDATE_ARM,
            seed_class=SEED_CLASS_SEALED_FORMAL,
            scope="LENIENT",
        )


def test_selection_without_authorization_emits_nothing(
    protocol: dict, dev_summary: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Authorization is checked before any verdict is computed on sealed data."""
    monkeypatch.setattr(sel, "assert_executable", lambda _protocol: None)
    with pytest.raises(SelectionError, match="formal authorization evidence is required"):
        select_candidate(protocol, _formal_summary(dev_summary), formal_evidence_sha256="sha256:x")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda a: a.pop("authority"), "authority"),
        (lambda a: a.update({"scope_git_sha": "abc"}), "40-character Git SHA"),
        (lambda a: a.update({"protocol_sha256": "sha256:" + "0" * 64}), "must name this protocol"),
    ],
)
def test_authorization_evidence_is_checked(
    protocol: dict,
    dev_summary: dict,
    authorization: dict,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
    message: str,
) -> None:
    monkeypatch.setattr(sel, "assert_executable", lambda _protocol: None)
    mutate(authorization)
    with pytest.raises(SelectionError, match=message):
        select_candidate(
            protocol,
            _formal_summary(dev_summary),
            authorization=authorization,
            formal_evidence_sha256="sha256:x",
        )


# --------------------------------------------------------------------------- #
# SEL-07 the rule self-check, which cannot select
# --------------------------------------------------------------------------- #


def test_rule_self_check_selects_nothing_on_the_seen_evidence(
    protocol: dict, dev_summary: dict
) -> None:
    """The strongest available protection against post-hoc design bias.

    A rule written to let V7B through would let V7B through here, on the only
    data its author has seen. It does not.
    """
    report = check_rule_on_development_evidence(protocol, dev_summary)
    assert report["purpose"] == "RULE_SELF_CHECK_NOT_A_SELECTION"
    assert report["outcome"] == STATUS_NO_CANDIDATE
    assert report["selected_candidate_arm_id"] is None
    for arm in protocol["arms"]["candidate_arm_ids"]:
        assert report["per_candidate"][arm]["eligible"] is False


def test_rule_self_check_actually_exercises_the_substantive_conditions(
    protocol: dict, dev_summary: dict
) -> None:
    """It must not stop at 'development seeds are not FORMAL', which proves nothing."""
    report = check_rule_on_development_evidence(protocol, dev_summary)
    for arm, comparable in (
        (CANDIDATE_ARM, "120/150"),
        ("V7C_FILTERED_ACTION", "0/150"),
    ):
        conditions = report["per_candidate"][arm]["conditions"]
        assert _condition(conditions, "SEL-C1")["state"] == STATE_PASS
        blocking = _condition(conditions, "SEL-C2")
        assert blocking["state"] == STATE_FAIL
        assert comparable in blocking["detail"]
        assert "143/150" in blocking["detail"]


def test_rule_self_check_refuses_a_rule_that_passes_on_its_own_inspiration(
    protocol: dict, dev_summary: dict
) -> None:
    """A post-hoc rule that passes on the data it was written after is not a rule."""
    with pytest.raises(SelectionError, match="provides no protection against"):
        check_rule_on_development_evidence(protocol, _formal_summary(dev_summary))


def test_the_self_check_could_have_passed_which_is_what_makes_it_evidence(
    protocol: dict, dev_summary: dict
) -> None:
    """The self-check must be answerable, not vacuously blocked.

    My first version failed SEL-C5 for a missing gate report on every input, so
    it could never have passed for any data and was therefore no evidence at all
    about the rule. SEL-C5 and SEL-C6 are now NOT_APPLICABLE in a self-check -
    neither discriminates between candidates - so a clean summary really does
    get through, and the refusal on the real evidence really does come from
    SEL-C2.
    """
    clean = evaluate_conditions(
        protocol,
        _formal_summary(dev_summary),
        CANDIDATE_ARM,
        seed_class=SEED_CLASS_DEVELOPMENT_EXHAUSTED,
        scope=SCOPE_SELF_CHECK,
    )
    assert sel._self_check_unblocked(clean) is True
    assert _condition(clean, "SEL-C5")["state"] == STATE_NOT_APPLICABLE
    assert _condition(clean, "SEL-C6")["state"] == STATE_NOT_APPLICABLE
    # And not applicable is still not eligible for a selection.
    assert sel._eligible(clean) is False

    real = evaluate_conditions(
        protocol,
        dev_summary,
        CANDIDATE_ARM,
        seed_class=SEED_CLASS_DEVELOPMENT_EXHAUSTED,
        scope=SCOPE_SELF_CHECK,
    )
    assert sel._self_check_unblocked(real) is False
    assert _condition(real, "SEL-C2")["state"] == STATE_FAIL


# --------------------------------------------------------------------------- #
# SEL-04 every condition must be an explicit PASS
# --------------------------------------------------------------------------- #


def test_a_clean_formal_summary_reaches_every_condition(
    protocol: dict, dev_summary: dict
) -> None:
    conditions = evaluate_conditions(
        protocol,
        _formal_summary(dev_summary),
        CANDIDATE_ARM,
        seed_class=SEED_CLASS_SEALED_FORMAL,
        gate_report=_gate_report(),
        environment_lock_record=_pinned_lock(),
    )
    assert [item["state"] for item in conditions] == [STATE_PASS] * len(CONDITION_IDS)
    assert sel._eligible(conditions) is True


def _pinned_lock() -> dict:
    import os

    previous = os.environ.get("OMP_NUM_THREADS")
    os.environ["OMP_NUM_THREADS"] = "1"
    try:
        return capture_environment_lock()
    finally:
        if previous is None:
            os.environ.pop("OMP_NUM_THREADS", None)
        else:
            os.environ["OMP_NUM_THREADS"] = previous


@pytest.mark.parametrize(
    ("condition_id", "mutate"),
    [
        (
            "SEL-C1",
            lambda summary, kwargs: summary.update({"terminal_record_count": 449}),
        ),
        (
            "SEL-C2",
            lambda summary, kwargs: summary["replicates"][0]["arms"][0][
                "comparability_counts"
            ].update({"COMPARABLE": 29, "EXPOSURE_CENSORED": 1}),
        ),
        (
            "SEL-C3",
            lambda summary, kwargs: summary["candidates"][0]["method_level"][
                "theta_bound_pp"
            ].update({"lower_pp": -1.0, "upper_pp": 1.0}),
        ),
        (
            "SEL-C4",
            lambda summary, kwargs: summary["candidates"][0]["method_level"].update(
                {"between_replicate_sd_pp": None, "between_replicate_sd_reason": "BLOCKED"}
            ),
        ),
        ("SEL-C5", lambda summary, kwargs: kwargs.update({"gate_report": None})),
        ("SEL-C6", lambda summary, kwargs: kwargs.update({"environment_lock_record": None})),
    ],
)
def test_each_condition_can_block_on_its_own(
    protocol: dict, dev_summary: dict, condition_id: str, mutate
) -> None:
    summary = _formal_summary(dev_summary)
    kwargs = {"gate_report": _gate_report(), "environment_lock_record": _pinned_lock()}
    mutate(summary, kwargs)
    conditions = evaluate_conditions(
        protocol, summary, CANDIDATE_ARM, seed_class=SEED_CLASS_SEALED_FORMAL, **kwargs
    )
    assert _condition(conditions, condition_id)["state"] == STATE_FAIL
    assert sel._eligible(conditions) is False


def test_not_reached_is_never_treated_as_agreement(protocol: dict, dev_summary: dict) -> None:
    conditions = evaluate_conditions(
        protocol, dev_summary, CANDIDATE_ARM, seed_class=SEED_CLASS_DEVELOPMENT_EXHAUSTED
    )
    assert any(item["state"] == STATE_NOT_REACHED for item in conditions)
    assert sel._eligible(conditions) is False


def test_a_missing_gate_report_blocks_rather_than_passes(
    protocol: dict, dev_summary: dict
) -> None:
    """The gate subset is not derivable from the summary and may not be assumed."""
    conditions = evaluate_conditions(
        protocol,
        _formal_summary(dev_summary),
        CANDIDATE_ARM,
        seed_class=SEED_CLASS_SEALED_FORMAL,
        gate_report=None,
        environment_lock_record=_pinned_lock(),
    )
    blocked = _condition(conditions, "SEL-C5")
    assert blocked["state"] == STATE_FAIL
    assert "may not be assumed" in blocked["detail"]


def test_an_unpinned_or_synthetic_lock_blocks_selection(
    protocol: dict, dev_summary: dict
) -> None:
    record = _pinned_lock()
    record["lock_class"] = SYNTHETIC_LOCK_CLASS
    conditions = evaluate_conditions(
        protocol,
        _formal_summary(dev_summary),
        CANDIDATE_ARM,
        seed_class=SEED_CLASS_SEALED_FORMAL,
        gate_report=_gate_report(),
        environment_lock_record=record,
    )
    assert _condition(conditions, "SEL-C6")["state"] == STATE_FAIL


# --------------------------------------------------------------------------- #
# SEL-05 and SEL-08 tie handling and single application
# --------------------------------------------------------------------------- #


def test_exact_tie_selects_neither(
    protocol: dict, dev_summary: dict, authorization: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sel, "assert_executable", lambda _protocol: None)
    summary = _formal_summary(dev_summary)
    receipt = select_candidate(
        protocol,
        summary,
        authorization=authorization,
        gate_report=_gate_report(),
        environment_lock_record=_pinned_lock(),
        formal_evidence_sha256="sha256:" + "1" * 64,
    )
    assert receipt["exact_tie_unresolved"] is True
    assert receipt["selected_candidate_arm_id"] is None
    assert receipt["selection_status"] == STATUS_NO_CANDIDATE
    assert sorted(receipt["eligible_candidate_arm_ids"]) == sorted(
        protocol["arms"]["candidate_arm_ids"]
    )


def test_the_better_candidate_wins_when_bounds_differ(
    protocol: dict, dev_summary: dict, authorization: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sel, "assert_executable", lambda _protocol: None)
    summary = _formal_summary(dev_summary)
    summary["candidates"][1]["method_level"]["theta_bound_pp"].update(
        {"lower_pp": -8.0, "upper_pp": -7.0}
    )
    receipt = select_candidate(
        protocol,
        summary,
        authorization=authorization,
        gate_report=_gate_report(),
        environment_lock_record=_pinned_lock(),
        formal_evidence_sha256="sha256:" + "2" * 64,
    )
    assert receipt["selected_candidate_arm_id"] == CANDIDATE_ARM
    assert receipt["selection_status"] == "SELECTION_COMPLETE_CANDIDATE_SELECTED"
    # Even a selection keeps every downstream readiness flag false.
    assert receipt["method_level_power_ready"] is False
    assert receipt["paper_data_ready"] is False
    assert receipt["preregistered"] is False
    assert "PERMANENT_FOR_THE_V7_LINE" in receipt["training_replicate_scope_permanence"]


def test_the_rule_applies_once_per_formal_evidence_set(
    tmp_path: Path,
    protocol: dict,
    dev_summary: dict,
    authorization: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sel, "assert_executable", lambda _protocol: None)
    summary = _formal_summary(dev_summary)
    digest = "sha256:" + "3" * 64
    select_candidate(
        protocol,
        summary,
        authorization=authorization,
        gate_report=_gate_report(),
        environment_lock_record=_pinned_lock(),
        formal_evidence_sha256=digest,
        output_root=tmp_path,
    )
    with pytest.raises(SelectionError, match="already been decided"):
        select_candidate(
            protocol,
            summary,
            authorization=authorization,
            gate_report=_gate_report(),
            environment_lock_record=_pinned_lock(),
            formal_evidence_sha256=digest,
            output_root=tmp_path,
        )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CONTRACT_PATH), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=BACKEND_ROOT,
    )


def test_cli_status_reports_the_blockers_and_exits_one() -> None:
    result = _cli("status")
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["executable"] is False
    assert payload["preregistered"] is False
    assert payload["authorization_state"] == "NOT_OBTAINED"
    assert [item["id"] for item in payload["unresolved_execution_preconditions"]] == [
        "EP-01",
        "EP-02",
        "EP-03",
    ]


def test_cli_rule_check_exits_one_with_no_candidate() -> None:
    result = _cli("rule-check", str(DEV_SUMMARY))
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["outcome"] == STATUS_NO_CANDIDATE
    assert payload["selected_candidate_arm_id"] is None


def test_cli_structural_failure_exits_two(tmp_path: Path) -> None:
    broken = tmp_path / "summary.json"
    broken.write_text("{not json", encoding="utf-8")
    result = _cli("rule-check", str(broken))
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["validation_status"] == "STRUCTURAL_FAILURE"
    assert payload["selected_candidate_arm_id"] is None


def test_the_protocols_documented_self_check_matches_what_the_code_reports(
    protocol: dict, dev_summary: dict
) -> None:
    """Keep the frozen narrative and the executable rule from drifting apart.

    The protocol states, per candidate, which condition stops it. If the code
    ever reported a different chain, the frozen document would be describing a
    rule nobody runs.
    """
    documented = protocol["rule_self_check_on_development_evidence"]["per_candidate"]
    report = check_rule_on_development_evidence(protocol, dev_summary)
    assert (
        protocol["rule_self_check_on_development_evidence"]["expected_outcome"]
        == report["outcome"]
        == STATUS_NO_CANDIDATE
    )
    for arm, expected in documented.items():
        actual = {
            item["id"]: item["state"] for item in report["per_candidate"][arm]["conditions"]
        }
        for condition_id, text in expected.items():
            assert actual[condition_id] == text.split(":", 1)[0], (
                arm,
                condition_id,
                text,
                actual[condition_id],
            )
