"""Tests for ``GATE-STATUS-SINGLE-SOURCE-V1``.

The positive test is that the repository as it stands is consistent.  The
negative tests replay, on a throwaway copy of the tree, the four staleness
failures measured between 2026-09-14 and 2026-09-16 and recorded in
``docs/PROJECT_ASSESSMENT_2026-09-16.md`` section 4.3.1.  A contract that only
passed on a clean tree would prove nothing: what has to be shown is that each
of those four, reintroduced, now fails closed.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gate_status_contract as gsc  # noqa: E402

REPO_ROOT = gsc.REPO_ROOT


# --------------------------------------------------------------------------
# the tree as it stands
# --------------------------------------------------------------------------

def test_registry_loads_and_is_well_formed():
    registry = gsc.load_registry()
    assert registry["registry_id"] == "GATE-STATUS-SINGLE-SOURCE-V1"
    assert registry["gates"], "registry must describe at least one gate"


def test_every_gate_has_exactly_one_authority():
    registry = gsc.load_registry()
    for gate, entry in registry["gates"].items():
        kinds = [site["kind"] for site in entry["sites"]]
        assert kinds.count("AUTHORITY") == 1, gate


def test_repository_is_consistent():
    summary = gsc.verify()
    assert summary["result"] == "GATE_STATUS_SINGLE_SOURCE_CONSISTENT"
    assert summary["sites_checked"] >= summary["gates_checked"]


def test_mirrors_exist_so_the_check_has_something_to_do():
    """A registry of gates with no mirror anywhere would pass trivially."""
    registry = gsc.load_registry()
    mirrors = sum(1 for entry in registry["gates"].values()
                  for site in entry["sites"] if site["kind"] == "MIRROR")
    assert mirrors >= 20, f"only {mirrors} mirrors registered"


def test_evidence_paths_exist():
    registry = gsc.load_registry()
    for gate, entry in registry["gates"].items():
        for rel in entry["evidence"]:
            assert os.path.exists(os.path.join(REPO_ROOT, rel)), f"{gate} -> {rel}"


# --------------------------------------------------------------------------
# reading a status out of a cell
# --------------------------------------------------------------------------

VOCAB = {
    "PASS": ["PASS"],
    "PARTIAL": ["PARTIAL"],
    "IN_PROGRESS": ["IN_PROGRESS", "IN PROGRESS"],
    "NOT_STARTED": ["NOT_STARTED", "NOT STARTED"],
    "BLOCKED": ["BLOCKED"],
    "ATTAINED": ["ATTAINED"],
    "NOT_ATTAINED": ["NOT_ATTAINED"],
    "CLOSED_NOT_ATTAINED": ["CLOSED_NOT_ATTAINED"],
    "FOUNDATION_SOFTWARE_PARTIAL": ["FOUNDATION_SOFTWARE_PARTIAL",
                                    "FOUNDATION SOFTWARE PARTIAL"],
    "PARTIAL_IMPLEMENTED_NOT_PASS": ["PARTIAL_IMPLEMENTED_NOT_PASS",
                                     "PARTIAL IMPLEMENTED / NOT PASS"],
}


@pytest.mark.parametrize("cell,expected", [
    # a descriptive tail must not be read as the status
    ("IN PROGRESS / content-sensitive Git identity PASS", "IN_PROGRESS"),
    ("PARTIAL / static V4 replay PASS；articulated dynamic 缺", "PARTIAL"),
    # the longest form at the earliest position wins over a prefix of it
    ("PARTIAL IMPLEMENTED / NOT PASS", "PARTIAL_IMPLEMENTED_NOT_PASS"),
    ("FOUNDATION SOFTWARE PARTIAL / FORMAL NOT STARTED", "FOUNDATION_SOFTWARE_PARTIAL"),
    # containment: NOT_ATTAINED is not ATTAINED, CLOSED_NOT_ATTAINED is neither
    ("**`NOT_ATTAINED`**（2026-09-14）", "NOT_ATTAINED"),
    ("**`CLOSED_NOT_ATTAINED`**（2026-09-09）", "CLOSED_NOT_ATTAINED"),
    ("**`ATTAINED`**（2026-09-14 執行完成）", "ATTAINED"),
    # emphasis, backticks and a leading particle
    ("仍 `BLOCKED` by B2（2026-09-14 實測未過）", "BLOCKED"),
    ("`IN_PROGRESS` — **`FOUR_VERIFIED_REMAINING_U`**", "IN_PROGRESS"),
    # a status buried in prose is not this cell's status
    ("因為某個上游原因，後續才會 PASS", None),
])
def test_leading_status(cell, expected):
    assert gsc.leading_status(cell, VOCAB) == expected


def test_correction_note_is_not_read_as_the_status():
    """先立後撤 keeps superseded wording in place; it must not be read as current."""
    cell = ("**PARTIAL IMPLEMENTED / NOT PASS**（**2026-09-16 更正**；"
            "此格原寫 `BLOCKED BY V0`，低估了已量到的部分結果）")
    assert gsc.leading_status(cell, VOCAB) == "PARTIAL_IMPLEMENTED_NOT_PASS"
    assert "BLOCKED" not in gsc.normalise_cell(cell)


# --------------------------------------------------------------------------
# the four measured failures, replayed
# --------------------------------------------------------------------------

@pytest.fixture
def tree(tmp_path):
    """A copy of the documents and registry the contract reads."""
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    registry = gsc.load_registry()
    needed = {site["doc"] for entry in registry["gates"].values()
              for site in entry["sites"]}
    needed |= {rel for entry in registry["gates"].values() for rel in entry["evidence"]}
    for rel in needed:
        shutil.copy(os.path.join(REPO_ROOT, rel), root / rel)
    registry_path = root / "gate_status_registry.json"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return root, str(registry_path)


def _edit(root, rel, old, new):
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} occurs {text.count(old)} times in {rel}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_clean_copy_passes(tree):
    root, registry_path = tree
    assert gsc.verify(registry_path, str(root))["result"] == \
        "GATE_STATUS_SINGLE_SOURCE_CONSISTENT"


def test_stale_mirror_fails(tree):
    """Instance 3: PUB-A0 moved in two files, missed in the third."""
    root, registry_path = tree
    _edit(root, "docs/TRACK_A_REFRAME_2026-09-09.md",
          "| `IN_PROGRESS` — `FOUR_VERIFIED_REMAINING_U`（2026-09-16） |",
          "| `NOT_STARTED` |")
    with pytest.raises(gsc.GateStatusError) as caught:
        gsc.verify(registry_path, str(root))
    assert "PUB-A0" in str(caught.value)
    assert "TRACK_A_REFRAME" in str(caught.value)


def test_stale_authority_fails_too(tree):
    """A status regressed at its own source is caught by its mirrors."""
    root, registry_path = tree
    _edit(root, "docs/PUBLICATION_PLAN.md", "| **`PASS`** |", "| `NOT_STARTED` |")
    with pytest.raises(gsc.GateStatusError) as caught:
        gsc.verify(registry_path, str(root))
    assert "PUB-A1a" in str(caught.value)


def test_executed_line_still_marked_not_started_fails(tree):
    """Instances 1 and 2: a line that had run still reading NOT STARTED."""
    root, registry_path = tree
    _edit(root, "docs/PUBLICATION_PLAN.md",
          "| **`ATTAINED`**（2026-09-14 執行完成",
          "| `NOT_STARTED`（2026-09-14 執行完成")
    with pytest.raises(gsc.GateStatusError) as caught:
        gsc.verify(registry_path, str(root))
    assert "PUB-B1" in str(caught.value)


def test_deleted_row_fails_rather_than_silently_skipping(tree):
    """A check that stops covering a gate must fail, not pass quietly."""
    root, registry_path = tree
    path = root / "docs/PAPER_DATA_READINESS.md"
    text = path.read_text(encoding="utf-8")
    kept = [line for line in text.splitlines() if not line.startswith("| PDR-4 ")]
    path.write_text("\n".join(kept), encoding="utf-8")
    with pytest.raises(gsc.GateStatusError) as caught:
        gsc.verify(registry_path, str(root))
    assert "PDR-4" in str(caught.value)
    assert "anchor not found" in str(caught.value)


def test_registry_status_outside_the_vocabulary_is_rejected(tmp_path):
    registry = gsc.load_registry()
    registry["gates"]["PUB-A0"]["status"] = "PROBABLY_FINE"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(gsc.GateStatusError, match="not in the vocabulary"):
        gsc.load_registry(str(path))


def test_registry_with_two_authorities_is_rejected(tmp_path):
    registry = gsc.load_registry()
    for site in registry["gates"]["PUB-A0"]["sites"]:
        site["kind"] = "AUTHORITY"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(gsc.GateStatusError, match="exactly one AUTHORITY"):
        gsc.load_registry(str(path))


def test_missing_evidence_file_is_reported(tree):
    root, registry_path = tree
    registry = json.loads(open(registry_path, encoding="utf-8").read())
    registry["gates"]["PUB-B1"]["evidence"] = ["docs/NO_SUCH_RECEIPT.md"]
    open(registry_path, "w", encoding="utf-8").write(
        json.dumps(registry, ensure_ascii=False))
    with pytest.raises(gsc.GateStatusError, match="evidence file does not exist"):
        gsc.verify(registry_path, str(root))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_reports_consistency():
    assert gsc.main([]) == 0


def test_cli_list_prints_every_gate(capsys):
    assert gsc.main(["--list"]) == 0
    printed = capsys.readouterr().out
    registry = gsc.load_registry()
    for gate in registry["gates"]:
        assert gate in printed


def test_cli_returns_nonzero_on_drift(tree, capsys):
    root, registry_path = tree
    _edit(root, "docs/PUBLICATION_PLAN.md", "| **`PASS`** |", "| `BLOCKED` |")
    assert gsc.main(["--registry", registry_path, "--repo-root", str(root)]) == 1
    assert "GATE STATUS CHECK FAILED" in capsys.readouterr().err
