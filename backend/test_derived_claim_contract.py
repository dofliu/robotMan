"""Tests for ``DERIVED-CLAIM-CONSISTENCY-V1``.

The positive test is that the repository as it stands is consistent.  The
negative tests replay, on a throwaway copy of the tree, the staleness that
``GATE-STATUS-SINGLE-SOURCE-V1`` explicitly does not cover and that
``docs/GATE_STATUS_SINGLE_SOURCE.md`` section 6 recorded as an open gap: a paper
verified in the literature map while three documents go on listing it among the
papers still to verify.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import derived_claim_contract as dcc  # noqa: E402

REPO_ROOT = dcc.REPO_ROOT


# --------------------------------------------------------------------------
# the tree as it stands
# --------------------------------------------------------------------------

def test_registry_loads_and_is_well_formed():
    registry = dcc.load_registry()
    assert registry["registry_id"] == "DERIVED-CLAIM-CONSISTENCY-V1"
    assert registry["claims"], "registry must describe at least one claim"


def test_repository_is_consistent():
    summary = dcc.verify()
    assert summary["result"] == "DERIVED_CLAIMS_CONSISTENT"


def test_every_registered_paper_resolves_to_exactly_one_level():
    registry = dcc.load_registry()
    for source in registry["sources"].values():
        levels = dcc.read_levels(source)
        assert set(levels) == set(source["papers"]), "every paper must resolve"
        assert all(level in source["levels"] for level in levels.values())


def test_the_claim_has_mirrors_so_the_check_has_something_to_do():
    registry = dcc.load_registry()
    sites = sum(len(claim["sites"]) for claim in registry["claims"].values())
    assert sites >= 3, f"only {sites} sites registered"


def test_members_are_the_papers_that_are_still_unverified():
    """The registry's member list must agree with the source, not with memory."""
    registry = dcc.load_registry()
    claim = registry["claims"]["pub_a0_priority_to_verify"]
    source = registry["sources"][claim["source"]]
    levels = dcc.read_levels(source)
    for member in claim["members"]:
        assert levels[member] == source["unverified_level"], member


# --------------------------------------------------------------------------
# reading a claim out of a sentence
# --------------------------------------------------------------------------

def test_list_segment_excludes_the_already_verified_preamble():
    """The sentence reports what was verified before saying what is left."""
    line = ("再兩篇已核對（2026-09-16：Pardo 1712.00378、Learning to Locomote "
            "2010.04304）。**優先三篇**：Colas 2019、Manski 1990／Tamer 2010、"
            "Hollenbeck & Wright 2017。另需核對 rl-zoo recipe 數值。")
    segment = dcc.list_segment(line, "優先{count}篇")
    assert "Colas 2019" in segment
    assert "Hollenbeck & Wright 2017" in segment
    assert "Pardo" not in segment, "the preamble must not be read as the list"
    assert "rl-zoo" not in segment, "the segment ends at its own sentence"


@pytest.mark.parametrize("line,expected", [
    ("**優先三篇**：a、b、c。", 3),
    ("優先兩篇：a、b。", 2),
    ("優先一篇：a。", 1),
    ("沒有數量詞", None),
])
def test_count_word(line, expected):
    assert dcc._count_word(line, "優先{count}篇") == expected


def test_correction_notes_are_skipped():
    note = "   [BLOCKER] **2026-09-17 更正**：本列原寫「優先四篇」並把 Pardo 2018 列為待核對"
    assert dcc.is_correction_note(note)
    assert not dcc.is_correction_note("**優先三篇**：Colas 2019")


# --------------------------------------------------------------------------
# the measured failure, replayed
# --------------------------------------------------------------------------

@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    registry = dcc.load_registry()
    needed = {site["doc"] for claim in registry["claims"].values()
              for site in claim["sites"]}
    for source in registry["sources"].values():
        needed |= set(source["docs"])
    needed |= set(registry.get("scan", {}).get("docs", []))
    for rel in needed:
        shutil.copy(os.path.join(REPO_ROOT, rel), root / rel)
    path = root / "derived_claim_registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return root, str(path)


def _edit(root, rel, old, new, expected=1):
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == expected, f"{old!r} occurs {text.count(old)} times in {rel}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_clean_copy_passes(tree):
    root, path = tree
    assert dcc.verify(path, str(root))["result"] == "DERIVED_CLAIMS_CONSISTENT"


def test_a_verified_paper_left_on_the_list_fails(tree):
    """The measured failure: Pardo moved U to S, three lists kept naming it."""
    root, path = tree
    _edit(root, "docs/PROJECT_STATUS.md",
          "**優先三篇**：Colas 2019",
          "**優先四篇**：Pardo 2018、Colas 2019")
    with pytest.raises(dcc.DerivedClaimError) as caught:
        dcc.verify(path, str(root))
    message = str(caught.value)
    assert "NO_VERIFIED_PAPER_NAMED" in message
    assert "Pardo 2018" in message
    assert "PROJECT_STATUS" in message


def test_the_same_staleness_seen_from_the_source_side_fails(tree):
    """If the map moves a member to verified, the member list is stale."""
    root, path = tree
    _edit(root, "docs/LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md",
          "| U | 2019 | Colas, Sigaud, Oudeyer, *A Hitchhiker",
          "| **S** | 2019 | Colas, Sigaud, Oudeyer, *A Hitchhiker")
    with pytest.raises(dcc.DerivedClaimError) as caught:
        dcc.verify(path, str(root))
    assert "MEMBERS_STILL_UNVERIFIED" in str(caught.value)


def test_a_member_silently_dropped_from_one_document_fails(tree):
    root, path = tree
    _edit(root, "docs/TRACK_A_REFRAME_2026-09-09.md",
          "**優先三篇**：Colas 2019、Manski 1990／Tamer 2010、Hollenbeck & Wright 2017。",
          "**優先三篇**：Colas 2019、Manski 1990／Tamer 2010。")
    with pytest.raises(dcc.DerivedClaimError) as caught:
        dcc.verify(path, str(root))
    assert "ALL_MEMBERS_NAMED" in str(caught.value)


def test_a_cardinality_that_no_longer_matches_fails(tree):
    """A list that loses a member while keeping its numeral is still wrong."""
    root, path = tree
    _edit(root, "docs/PROJECT_STATUS.md", "**優先三篇**：", "**優先四篇**：")
    with pytest.raises(dcc.DerivedClaimError) as caught:
        dcc.verify(path, str(root))
    assert "COUNT_WORD_MATCHES_MEMBERS" in str(caught.value)


def test_an_unregistered_fifth_copy_fails(tree):
    """One more copy appearing is the predicted failure mode."""
    root, path = tree
    target = root / "docs/ROADMAP.md"
    target.write_text(
        target.read_text(encoding="utf-8")
        + "\n\n優先三篇：Colas 2019、Manski 1990／Tamer 2010、Hollenbeck & Wright 2017。\n",
        encoding="utf-8")
    with pytest.raises(dcc.DerivedClaimError) as caught:
        dcc.verify(path, str(root))
    assert "UNREGISTERED_COPY" in str(caught.value)
    assert "ROADMAP" in str(caught.value)


def test_a_deleted_site_fails_rather_than_silently_skipping(tree):
    root, path = tree
    target = root / "docs/PUBLICATION_PLAN.md"
    kept = [line for line in target.read_text(encoding="utf-8").splitlines()
            if "1. **`PUB-A0`**：關鍵兩篇已核對" not in line]
    target.write_text("\n".join(kept), encoding="utf-8")
    with pytest.raises(dcc.DerivedClaimError) as caught:
        dcc.verify(path, str(root))
    assert "anchor matches 0 live line(s)" in str(caught.value)


def test_claim_must_retire_once_nothing_is_unverified(tree):
    """A to-verify list with nothing left to verify must go, not sit there."""
    root, path = tree
    for doc in ("docs/LITERATURE_MAP_2026-09-08_EVALUATION_VALIDITY.md",
                "docs/LITERATURE_MAP_2026-09-16_TRAINING_STRATEGY.md"):
        target = root / doc
        text = target.read_text(encoding="utf-8")
        target.write_text(
            "\n".join(line.replace("| U |", "| **S** |", 1) if line.startswith("| U |")
                      else line for line in text.splitlines()), encoding="utf-8")
    with pytest.raises(dcc.DerivedClaimError) as caught:
        dcc.verify(path, str(root))
    assert "CLAIM_RETIRES_WHEN_SOURCE_EMPTY" in str(caught.value)


def test_a_paper_at_two_levels_is_rejected(tree):
    """The source of record has to be unambiguous before anything derives from it."""
    root, path = tree
    _edit(root, "docs/LITERATURE_MAP_2026-09-16_TRAINING_STRATEGY.md",
          "| **S** | 2020 | Reda, Tao, van de Panne",
          "| U | 2020 | Reda, Tao, van de Panne")
    with pytest.raises(dcc.DerivedClaimError, match="more than one level"):
        dcc.verify(path, str(root))


# --------------------------------------------------------------------------
# registry validation
# --------------------------------------------------------------------------

def test_member_outside_the_paper_list_is_rejected(tmp_path):
    registry = dcc.load_registry()
    registry["claims"]["pub_a0_priority_to_verify"]["members"].append("no_such_paper")
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(dcc.DerivedClaimError, match="not a registered paper"):
        dcc.load_registry(str(path))


def test_unknown_rule_is_rejected(tmp_path):
    registry = dcc.load_registry()
    registry["claims"]["pub_a0_priority_to_verify"]["rules"].append("PROBABLY_FINE")
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(dcc.DerivedClaimError, match="unknown rule"):
        dcc.load_registry(str(path))


def test_paper_with_no_way_to_locate_it_is_rejected(tmp_path):
    registry = dcc.load_registry()
    papers = registry["sources"]["literature_verification"]["papers"]
    papers["ghost"] = {"display": "Ghost", "arxiv": None, "claim_names": []}
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(dcc.DerivedClaimError, match="neither an arxiv id nor a row_match"):
        dcc.load_registry(str(path))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_reports_consistency():
    assert dcc.main([]) == 0


def test_cli_list_prints_every_paper(capsys):
    assert dcc.main(["--list"]) == 0
    printed = capsys.readouterr().out
    registry = dcc.load_registry()
    for source in registry["sources"].values():
        for key in source["papers"]:
            assert key in printed


def test_cli_returns_nonzero_on_a_stale_claim(tree, capsys):
    root, path = tree
    _edit(root, "docs/PROJECT_STATUS.md",
          "**優先三篇**：Colas 2019",
          "**優先四篇**：Pardo 2018、Colas 2019")
    assert dcc.main(["--registry", path, "--repo-root", str(root)]) == 1
    assert "DERIVED CLAIM CHECK FAILED" in capsys.readouterr().err
