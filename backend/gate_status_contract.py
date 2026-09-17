"""Check every documented gate status against one authoritative record.

``GATE-STATUS-SINGLE-SOURCE-V1``, registered in
``backend/gate_status_registry.json`` and specified in
``docs/GATE_STATUS_SINGLE_SOURCE.md``.

The failure this exists to catch was measured, not imagined.  Between
2026-09-14 and 2026-09-16 the same fact went stale in four places: the
tracked-lineage line read ``NOT STARTED`` in ``RESEARCH_EXECUTION_PLAN`` and
"not yet executed" in ``PUBLICATION_PLAN`` two days after it had run to
completion; ``PUB-A0`` was moved to ``FOUR_VERIFIED_REMAINING_U`` in two files
and not the third; and a paper verified on 2026-09-16 stayed on a to-verify
list in three documents, one of which contradicted its own gate table.  None of
the four was caught by a mechanism.  All four were caught by someone happening
to look back.  ``docs/PROJECT_ASSESSMENT_2026-09-16.md`` section 4.3.1 records
the measurement: one gate's status had twenty-four copies across eight files and
nothing reported a missed one.  Contract code here fails closed; documentation
did not.

Three design points are load-bearing rather than incidental.

First, sites are *enumerated*, never matched by pattern.  In this repository
``V1`` denotes both a V&V gate and a version number -- "analytical fixture V1",
``PAPER_RUN_MANIFEST_V2``, ``PUBLICATION-PLAN-V3`` -- so any scan for ``V\\d``
mixes the two, and a scan tuned to avoid that silently stops covering the gate.
Each site instead names its document and an *anchor*: the leading table cell or
distinctive phrase that identifies the row, chosen so that it does not itself
contain the status.  An anchor that no longer occurs, or occurs more than once,
is a failure rather than a skipped check: a renamed row must be re-registered
deliberately.

Second, a status is a token with *accepted forms*, not a string to compare.
The same status is written ``PARTIAL_IMPLEMENTED_NOT_PASS`` in
``PROJECT_STATUS`` and ``PARTIAL IMPLEMENTED / NOT PASS`` in ``ROADMAP``, and
``PDR-6`` reads ``SOFTWARE CONTRACT PARTIAL`` in one document and
``SOFTWARE PARTIAL`` in the other.  Requiring one literal spelling would force a
cosmetic rewrite of documents that are already correct; allowing any spelling
would check nothing.  The registry therefore lists, per token, the forms that
count as asserting it, and adding a new phrasing is a deliberate registry edit.

Third, a status is read from the *leading position of its own cell*, not from
anywhere on the row.  Checking the whole row does not work and the measurement
is in this repository: eleven rows say ``PASS`` in a neighbouring column --
"path/bytes/SHA-256 readback PASS", "16/14 exact" -- while the gate itself is
``IN PROGRESS``.  Those are descriptions of sub-items, not the gate's status.
Reading the leading form of the status cell also settles token containment for
free, since the longest form starting at the earliest position wins:
``PARTIAL IMPLEMENTED / NOT PASS`` beats ``PARTIAL``, and the descriptive tail
after it is never mistaken for a second status.  A correction note -- text from
a ``（**<date> 更正`` marker onward, which the project's correct-in-place norm
requires to keep the superseded wording -- is history and is stripped first.

What follows from that third point is the check's real bite: a cell whose
leading status is not the registry's fails, whatever else the row says.  A stale
status left in place of a corrected one cannot pass.

What this contract does not do is decide whether a status is *true*.  It decides
whether the project says the same thing everywhere.  Truth against the receipts
is the audit recorded in ``CHANGELOG`` entry (ah); this is the mechanism that
keeps that audit from having to be repeated by hand.

Every top-level import is stdlib, so the check runs under ``python -I -S`` with
no site packages at all.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, List, NamedTuple, Sequence, Tuple

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "gate_status_registry.json")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SITE_KINDS = ("AUTHORITY", "MIRROR")


class GateStatusError(Exception):
    """A documented gate status disagrees with the registry, or cannot be checked."""


class Violation(NamedTuple):
    gate: str
    doc: str
    anchor: str
    problem: str
    detail: str

    def render(self) -> str:
        return (f"{self.gate} in {self.doc}\n"
                f"    anchor : {self.anchor}\n"
                f"    problem: {self.problem}\n"
                f"    detail : {self.detail}")


def load_registry(path: str = REGISTRY_PATH) -> dict:
    """Read the registry and reject a shape the checker cannot act on."""
    with open(path, encoding="utf-8") as handle:
        registry = json.load(handle)

    for key in ("registry_id", "status_vocabulary", "gates"):
        if key not in registry:
            raise GateStatusError(f"registry is missing the {key!r} key")

    vocab = registry["status_vocabulary"]
    if not isinstance(vocab, dict) or not vocab:
        raise GateStatusError("status_vocabulary must be a non-empty object")
    for token, forms in vocab.items():
        if not isinstance(forms, list) or not forms:
            raise GateStatusError(f"status token {token!r} has no accepted forms")
        if token not in forms:
            raise GateStatusError(
                f"status token {token!r} must be one of its own accepted forms")

    gates = registry["gates"]
    if not isinstance(gates, dict) or not gates:
        raise GateStatusError("gates must be a non-empty object")
    for gate, entry in gates.items():
        status = entry.get("status")
        if status not in vocab:
            raise GateStatusError(
                f"gate {gate!r} has status {status!r}, which is not in the vocabulary")
        sites = entry.get("sites")
        if not isinstance(sites, list) or not sites:
            raise GateStatusError(f"gate {gate!r} has no assertion sites")
        kinds = [site.get("kind") for site in sites]
        for kind in kinds:
            if kind not in SITE_KINDS:
                raise GateStatusError(f"gate {gate!r} has a site of unknown kind {kind!r}")
        if kinds.count("AUTHORITY") != 1:
            raise GateStatusError(
                f"gate {gate!r} must have exactly one AUTHORITY site, found "
                f"{kinds.count('AUTHORITY')}")
        for site in sites:
            if not site.get("doc") or not site.get("anchor"):
                raise GateStatusError(f"gate {gate!r} has a site without doc or anchor")
    return registry


CORRECTION_NOTE = re.compile(r"（\*{0,2}\d{4}-\d{2}-\d{2}\s*更正.*$")

#: How far into a cell a status may begin. A cell may open with a particle
#: (``仍 BLOCKED``) or emphasis leftovers; a token buried deeper than this is
#: prose about some other thing, not this cell's status.
LEADING_WINDOW = 12


def normalise_cell(cell: str) -> str:
    """Strip what is not part of the asserted status: emphasis, backticks, notes."""
    cell = CORRECTION_NOTE.sub("", cell)
    cell = cell.replace("**", "").replace("`", "")
    return cell.strip()


def leading_status(cell: str, vocab: Dict[str, List[str]]) -> str | None:
    """The status token a cell asserts, read from the front of the cell.

    The earliest position wins; at one position the longest accepted form wins,
    so ``PARTIAL IMPLEMENTED / NOT PASS`` is never read as ``PARTIAL``.
    """
    text = normalise_cell(cell)
    best: Tuple[int, int, str] | None = None
    for token, forms in vocab.items():
        for form in forms:
            pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(form) + r"(?![A-Za-z0-9_])")
            match = pattern.search(text)
            if match is None or match.start() > LEADING_WINDOW:
                continue
            candidate = (match.start(), -(match.end() - match.start()), token)
            if best is None or candidate < best:
                best = candidate
    return None if best is None else best[2]


def statuses_in_text(text: str, vocab: Dict[str, List[str]]) -> List[str]:
    """Every registered status token asserted anywhere in *text* (prose sites)."""
    spans: List[Tuple[int, int, str]] = []
    for token, forms in vocab.items():
        for form in forms:
            pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(form) + r"(?![A-Za-z0-9_])")
            for match in pattern.finditer(text):
                spans.append((match.start(), match.end(), token))
    found: List[str] = []
    for start, end, token in spans:
        inside = any(other_start <= start and end <= other_end
                     and (other_end - other_start) > (end - start)
                     for other_start, other_end, _ in spans)
        if not inside and token not in found:
            found.append(token)
    return found


def _locate(text: str, anchor: str) -> List[str]:
    """Return the lines of *text* containing *anchor*."""
    return [line for line in text.splitlines() if anchor in line]


def _cell_of(line: str, index: int) -> str | None:
    """The *index*-th cell of a markdown table row, or None if it has no such cell."""
    if not line.strip().startswith("|"):
        return None
    cells = [part.strip() for part in line.strip().strip("|").split("|")]
    return cells[index] if index < len(cells) else None


def check(registry: dict, repo_root: str = REPO_ROOT) -> List[Violation]:
    """Check every registered site. Returns the violations; empty means clean."""
    vocab = registry["status_vocabulary"]
    violations: List[Violation] = []
    cache: Dict[str, str] = {}

    for gate, entry in sorted(registry["gates"].items()):
        expected = entry["status"]
        for site in entry["sites"]:
            doc, anchor = site["doc"], site["anchor"]
            path = os.path.join(repo_root, doc)
            if doc not in cache:
                if not os.path.exists(path):
                    violations.append(Violation(
                        gate, doc, anchor, "document does not exist",
                        "a registered site points at a file that is not in the tree"))
                    cache[doc] = ""
                    continue
                with open(path, encoding="utf-8") as handle:
                    cache[doc] = handle.read()
            text = cache[doc]
            if not text:
                continue

            hits = _locate(text, anchor)
            if len(hits) == 0:
                violations.append(Violation(
                    gate, doc, anchor, "anchor not found",
                    "the row was renamed, moved or deleted; re-register the site "
                    "instead of letting the check silently stop covering it"))
                continue
            if len(hits) > 1:
                violations.append(Violation(
                    gate, doc, anchor, f"anchor is ambiguous ({len(hits)} matches)",
                    "an anchor must identify one row; narrow it"))
                continue

            line = hits[0]
            index = site.get("cell")

            if index is None:
                found = statuses_in_text(line, vocab)
                if expected not in found:
                    violations.append(Violation(
                        gate, doc, anchor, "status missing",
                        f"registry says {expected!r}; this prose site asserts "
                        f"{found if found else 'no registered status'}"))
                continue

            cell = _cell_of(line, index)
            if cell is None:
                violations.append(Violation(
                    gate, doc, anchor, f"row has no cell {index}",
                    "the table's columns changed; re-register the site's cell index"))
                continue

            found = leading_status(cell, vocab)
            if found is None:
                violations.append(Violation(
                    gate, doc, anchor, "status cell asserts no registered status",
                    f"registry says {expected!r}; the cell begins {cell[:60]!r}"))
            elif found != expected:
                violations.append(Violation(
                    gate, doc, anchor, "status disagrees with the registry",
                    f"registry says {expected!r}; this cell asserts {found!r}. "
                    "A status that reached some copies and not others is the failure "
                    "this check exists for"))

    for gate, entry in sorted(registry["gates"].items()):
        for rel in entry.get("evidence", []):
            if not os.path.exists(os.path.join(repo_root, rel)):
                violations.append(Violation(
                    gate, rel, "(evidence)", "evidence file does not exist",
                    "a gate's status cites a receipt that is not in the tree"))
    return violations


def verify(registry_path: str = REGISTRY_PATH, repo_root: str = REPO_ROOT) -> dict:
    """Fail closed: raise GateStatusError unless every registered site agrees."""
    registry = load_registry(registry_path)
    violations = check(registry, repo_root)
    if violations:
        body = "\n\n".join(violation.render() for violation in violations)
        raise GateStatusError(
            f"{len(violations)} documented gate status(es) disagree with "
            f"{os.path.basename(registry_path)}:\n\n{body}")
    return {
        "registry_id": registry["registry_id"],
        "gates_checked": len(registry["gates"]),
        "sites_checked": sum(len(entry["sites"]) for entry in registry["gates"].values()),
        "result": "GATE_STATUS_SINGLE_SOURCE_CONSISTENT",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default=REGISTRY_PATH)
    parser.add_argument("--repo-root", default=REPO_ROOT)
    parser.add_argument("--list", action="store_true",
                        help="print each gate's authoritative status and exit")
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.registry)
    except GateStatusError as error:
        print(f"REGISTRY INVALID: {error}", file=sys.stderr)
        return 2

    if args.list:
        for gate, entry in sorted(registry["gates"].items()):
            detail = f" — {entry['detail']}" if entry.get("detail") else ""
            mirrors = sum(1 for site in entry["sites"] if site["kind"] == "MIRROR")
            print(f"{gate:9s} {entry['status']}{detail}  "
                  f"(as of {entry['as_of']}, {mirrors} mirror(s))")
        return 0

    try:
        summary = verify(args.registry, args.repo_root)
    except GateStatusError as error:
        print(f"GATE STATUS CHECK FAILED\n\n{error}", file=sys.stderr)
        return 1
    print(f"{summary['result']}: {summary['gates_checked']} gates, "
          f"{summary['sites_checked']} sites, registry {summary['registry_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
