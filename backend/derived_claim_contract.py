"""Check prose claims derived from a source of record against that source.

``DERIVED-CLAIM-CONSISTENCY-V1``, registered in
``backend/derived_claim_registry.json`` and specified in
``docs/DERIVED_CLAIM_CONSISTENCY.md``.

A *derived claim* restates in prose something that follows from a source of
record: "the papers still to read are Colas 2019, Manski/Tamer and
Hollenbeck & Wright" follows from the verification levels in the literature
maps.  It goes stale when the source changes and the prose does not.

This is a different failure from the one ``gate_status_contract`` catches, and
the difference is why that contract could not be stretched to cover it.  There,
a document *copies* a status and the check is equality against the copy's
source.  Here nothing is copied: three documents each hold a list whose
membership is a *function* of ten rows in two other files, and the stale copy
does not disagree with a status anywhere -- it names a paper that has since
moved from ``U`` to ``S``.  ``docs/GATE_STATUS_SINGLE_SOURCE.md`` section 6
recorded that gap rather than let it pass as covered; this closes it.

The instance is measured.  On 2026-09-16 ``arXiv 1712.00378`` (Pardo) was read
in full and moved ``U`` to ``S`` in the map.  Three documents went on listing it
among the papers still to verify, and in one of them -- ``TRACK_A_REFRAME`` --
the stale list sat in section 10 while section 8 of the same file already read
``FOUR_VERIFIED_REMAINING_U``.  One file, two answers.  It was found on
2026-09-17 by someone reading back over the section that describes the problem.

Four design points are load-bearing rather than incidental.

First, a paper has two independent identities and both are registered.  A map
row spells it "Colas, Sigaud, Oudeyer, *A Hitchhiker's Guide to Statistical
Comparisons*"; a claim spells the same paper "Colas 2019".  Neither string
appears in the other place.  The row is found by arXiv id, or by a registered
``row_match`` for the papers that have no arXiv id at all (Manski 1990, Tamer
2010, Hollenbeck & Wright 2017); the prose is matched by registered
``claim_names``.

Second, the strongest rule is the negative one, and it reads the claim's *list
segment* rather than the whole line.  ``ALL_MEMBERS_NAMED`` catches a member
silently dropped, but ``NO_VERIFIED_PAPER_NAMED`` is what catches the measured
failure: the list may not name *any* paper the source now marks verified,
whether or not that paper is still in the registry's member list, so the check
does not depend on someone having remembered to update ``members``.  Reading the
whole line does not work, and the measurement is again in this repository: all
three sites open by reporting which papers *were* verified -- "再兩篇已核對
（2026-09-16：Pardo 1712.00378、Learning to Locomote 2010.04304）" -- before
listing what is left.  That preamble is correct and naming a verified paper
there is the point of it.  The segment runs from the cardinality word to the end
of its sentence.

Third, the count word is part of the claim.  "優先三篇" asserts a cardinality,
and a list that loses a member while keeping its numeral is wrong in a way no
membership check would see.

Fourth, the registry scans for unregistered copies.  A fifth document that grows
its own version of this list would otherwise be unprotected -- and one more copy
appearing is the failure mode
``docs/PROJECT_ASSESSMENT_2026-09-16.md`` section 4.3.1 predicts.  Every
occurrence of the claim's shape must be a registered site, a correction note, or
an entry a human put on the acknowledged list with a reason.

Correction notes are skipped throughout.  The project's correct-in-place norm
keeps superseded wording next to the correction, so the very sentence recording
"this list used to name Pardo 2018" would otherwise trip the negative rule.

Every top-level import is stdlib, so the check runs under ``python -I -S`` with
no site packages at all.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, List, NamedTuple, Sequence

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "derived_claim_registry.json")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CORRECTION_NOTE = re.compile(r"\*{0,2}\d{4}-\d{2}-\d{2}\s*更正")

CHINESE_NUMERALS = {"一": 1, "兩": 2, "二": 2, "三": 3, "四": 4, "五": 5,
                    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

KNOWN_RULES = ("MEMBERS_STILL_UNVERIFIED", "NO_VERIFIED_PAPER_NAMED",
               "ALL_MEMBERS_NAMED", "COUNT_WORD_MATCHES_MEMBERS",
               "CLAIM_RETIRES_WHEN_SOURCE_EMPTY")


class DerivedClaimError(Exception):
    """A derived claim disagrees with the source it is derived from."""


class Violation(NamedTuple):
    claim: str
    where: str
    rule: str
    detail: str

    def render(self) -> str:
        return (f"{self.claim} in {self.where}\n"
                f"    rule  : {self.rule}\n"
                f"    detail: {self.detail}")


def is_correction_note(line: str) -> bool:
    """A line preserving superseded wording is history, not a live claim."""
    return CORRECTION_NOTE.search(line) is not None


def load_registry(path: str = REGISTRY_PATH) -> dict:
    """Read the registry and reject a shape the checker cannot act on."""
    with open(path, encoding="utf-8") as handle:
        registry = json.load(handle)

    for key in ("registry_id", "sources", "claims"):
        if key not in registry:
            raise DerivedClaimError(f"registry is missing the {key!r} key")

    for name, source in registry["sources"].items():
        if not source.get("docs"):
            raise DerivedClaimError(f"source {name!r} lists no documents")
        if source.get("unverified_level") not in (source.get("levels") or []):
            raise DerivedClaimError(
                f"source {name!r} has an unverified_level outside its levels")
        for key, paper in (source.get("papers") or {}).items():
            if not paper.get("arxiv") and not paper.get("row_match"):
                raise DerivedClaimError(
                    f"paper {key!r} has neither an arxiv id nor a row_match, "
                    "so it cannot be located in the source")

    for name, claim in registry["claims"].items():
        if claim.get("source") not in registry["sources"]:
            raise DerivedClaimError(f"claim {name!r} names an unknown source")
        if not claim.get("members"):
            raise DerivedClaimError(f"claim {name!r} has no members")
        if not claim.get("sites"):
            raise DerivedClaimError(f"claim {name!r} has no sites")
        papers = registry["sources"][claim["source"]]["papers"]
        for member in claim["members"]:
            if member not in papers:
                raise DerivedClaimError(
                    f"claim {name!r} names member {member!r}, which is not a "
                    "registered paper")
        for rule in claim.get("rules", []):
            if rule not in KNOWN_RULES:
                raise DerivedClaimError(f"claim {name!r} names unknown rule {rule!r}")
    return registry


def read_levels(source: dict, repo_root: str = REPO_ROOT) -> Dict[str, str]:
    """Each registered paper's verification level, read from the source documents.

    A paper found in no row, or found at two different levels, is an error: the
    source of record has to be unambiguous before anything can be derived from it.
    """
    rows: List[str] = []
    column = source.get("level_column", 0)
    allowed = set(source["levels"])
    for rel in source["docs"]:
        path = os.path.join(repo_root, rel)
        if not os.path.exists(path):
            raise DerivedClaimError(f"source document {rel} does not exist")
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if not line.startswith("|"):
                    continue
                cells = [part.strip() for part in line.strip().strip("|").split("|")]
                if column >= len(cells):
                    continue
                if cells[column].replace("*", "").strip() in allowed:
                    rows.append(line)

    levels: Dict[str, str] = {}
    for key, paper in source["papers"].items():
        needle = paper.get("arxiv") or paper["row_match"]
        found = set()
        for line in rows:
            if needle in line:
                cells = [part.strip() for part in line.strip().strip("|").split("|")]
                found.add(cells[column].replace("*", "").strip())
        if not found:
            raise DerivedClaimError(
                f"paper {key!r} ({paper['display']}) matches no row in the source; "
                f"searched for {needle!r}")
        if len(found) > 1:
            raise DerivedClaimError(
                f"paper {key!r} ({paper['display']}) appears at more than one level "
                f"{sorted(found)}; the source of record must be unambiguous")
        levels[key] = found.pop()
    return levels


def _locate(text: str, anchor: str) -> List[str]:
    return [line for line in text.splitlines() if anchor in line]


def _count_match(line: str, template: str):
    pattern = re.escape(template).replace(r"\{count\}", "(.)")
    return re.search(pattern, line)


def _count_word(line: str, template: str) -> int | None:
    """The cardinality a claim states, e.g. 3 from 優先三篇."""
    match = _count_match(line, template)
    return None if match is None else CHINESE_NUMERALS.get(match.group(1))


def list_segment(line: str, template: str, terminator: str = "。") -> str:
    """The part of *line* that is the claim's list.

    A site's sentence usually opens by reporting what has already been verified
    and only then says what is left; naming a verified paper in that preamble is
    correct. The list runs from the cardinality word to the end of its sentence.
    """
    match = _count_match(line, template)
    if match is None:
        return line
    rest = line[match.start():]
    end = rest.find(terminator)
    return rest if end == -1 else rest[:end + len(terminator)]


def check(registry: dict, repo_root: str = REPO_ROOT) -> List[Violation]:
    """Check every registered claim and scan for unregistered copies."""
    violations: List[Violation] = []
    cache: Dict[str, str] = {}

    def text_of(rel: str) -> str | None:
        if rel not in cache:
            path = os.path.join(repo_root, rel)
            if not os.path.exists(path):
                return None
            with open(path, encoding="utf-8") as handle:
                cache[rel] = handle.read()
        return cache[rel]

    for claim_name, claim in sorted(registry["claims"].items()):
        source = registry["sources"][claim["source"]]
        levels = read_levels(source, repo_root)
        unverified = source["unverified_level"]
        papers = source["papers"]
        rules = claim.get("rules", [])
        members = claim["members"]

        if "MEMBERS_STILL_UNVERIFIED" in rules:
            for member in members:
                if levels[member] != unverified:
                    violations.append(Violation(
                        claim_name, "(registry)", "MEMBERS_STILL_UNVERIFIED",
                        f"{papers[member]['display']} is now {levels[member]!r} in the "
                        f"source but is still a member of this to-verify claim"))

        source_empty = all(level != unverified for level in levels.values())
        if "CLAIM_RETIRES_WHEN_SOURCE_EMPTY" in rules and source_empty:
            violations.append(Violation(
                claim_name, "(registry)", "CLAIM_RETIRES_WHEN_SOURCE_EMPTY",
                "no registered paper is unverified any more, so this claim has "
                "nothing left to assert and its sites must be retired"))

        for site in claim["sites"]:
            rel, anchor = site["doc"], site["anchor"]
            where = f"{rel} [{anchor[:40]}...]"
            text = text_of(rel)
            if text is None:
                violations.append(Violation(
                    claim_name, where, "site", "document does not exist"))
                continue
            hits = [line for line in _locate(text, anchor) if not is_correction_note(line)]
            if len(hits) != 1:
                violations.append(Violation(
                    claim_name, where, "site",
                    f"anchor matches {len(hits)} live line(s); it must identify "
                    "exactly one, so re-register it rather than let the check "
                    "silently stop covering this claim"))
                continue
            line = hits[0]

            segment = line
            if claim.get("count_template"):
                segment = list_segment(line, claim["count_template"],
                                       claim.get("list_terminator", "。"))

            if "ALL_MEMBERS_NAMED" in rules:
                for member in members:
                    names = papers[member].get("claim_names") or []
                    if names and not any(name in segment for name in names):
                        violations.append(Violation(
                            claim_name, where, "ALL_MEMBERS_NAMED",
                            f"{papers[member]['display']} is a member but this "
                            f"claim's list names none of {names}"))

            if "NO_VERIFIED_PAPER_NAMED" in rules:
                for key, paper in papers.items():
                    if levels[key] == unverified:
                        continue
                    for name in paper.get("claim_names") or []:
                        if name in segment:
                            violations.append(Violation(
                                claim_name, where, "NO_VERIFIED_PAPER_NAMED",
                                f"this claim's list still names {name!r}, but the "
                                f"source marks it {levels[key]!r}. A list of papers "
                                "still to verify may not name one already verified"))

            if "COUNT_WORD_MATCHES_MEMBERS" in rules and claim.get("count_template"):
                stated = _count_word(line, claim["count_template"])
                if stated is None:
                    violations.append(Violation(
                        claim_name, where, "COUNT_WORD_MATCHES_MEMBERS",
                        f"no cardinality matching {claim['count_template']!r} on this line"))
                elif stated != len(members):
                    violations.append(Violation(
                        claim_name, where, "COUNT_WORD_MATCHES_MEMBERS",
                        f"the line states {stated} but the claim has {len(members)} members"))

    scan = registry.get("scan")
    if scan:
        registered = {(site["doc"], site["anchor"])
                      for claim in registry["claims"].values() for site in claim["sites"]}
        allowed = {(entry["doc"], entry["anchor"])
                   for entry in scan.get("acknowledged_non_claims", [])}
        pattern = re.compile(scan["pattern"])
        for rel in scan["docs"]:
            text = text_of(rel)
            if text is None:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if not pattern.search(line) or is_correction_note(line):
                    continue
                known = any(rel == doc and anchor in line
                            for doc, anchor in registered | allowed)
                if not known:
                    violations.append(Violation(
                        "(scan)", f"{rel}:{number}", "UNREGISTERED_COPY",
                        f"this line looks like the claim ({scan['pattern']}) but is "
                        "neither a registered site nor an acknowledged non-claim. "
                        "A copy nothing checks is the failure this registry exists for"))
    return violations


def verify(registry_path: str = REGISTRY_PATH, repo_root: str = REPO_ROOT) -> dict:
    """Fail closed: raise DerivedClaimError unless every claim matches its source."""
    registry = load_registry(registry_path)
    violations = check(registry, repo_root)
    if violations:
        body = "\n\n".join(violation.render() for violation in violations)
        raise DerivedClaimError(
            f"{len(violations)} derived claim problem(s) against "
            f"{os.path.basename(registry_path)}:\n\n{body}")
    return {
        "registry_id": registry["registry_id"],
        "claims_checked": len(registry["claims"]),
        "sites_checked": sum(len(claim["sites"]) for claim in registry["claims"].values()),
        "papers_tracked": sum(len(source["papers"])
                              for source in registry["sources"].values()),
        "result": "DERIVED_CLAIMS_CONSISTENT",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default=REGISTRY_PATH)
    parser.add_argument("--repo-root", default=REPO_ROOT)
    parser.add_argument("--list", action="store_true",
                        help="print each source's papers with their level and exit")
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.registry)
    except DerivedClaimError as error:
        print(f"REGISTRY INVALID: {error}", file=sys.stderr)
        return 2

    if args.list:
        for name, source in registry["sources"].items():
            print(f"{name} ({source['what']})")
            try:
                levels = read_levels(source, args.repo_root)
            except DerivedClaimError as error:
                print(f"  UNREADABLE: {error}", file=sys.stderr)
                return 2
            for key, level in sorted(levels.items(), key=lambda item: (item[1], item[0])):
                print(f"  {level}  {key:28s} {source['papers'][key]['display']}")
        return 0

    try:
        summary = verify(args.registry, args.repo_root)
    except DerivedClaimError as error:
        print(f"DERIVED CLAIM CHECK FAILED\n\n{error}", file=sys.stderr)
        return 1
    print(f"{summary['result']}: {summary['claims_checked']} claim(s), "
          f"{summary['sites_checked']} sites, {summary['papers_tracked']} papers tracked, "
          f"registry {summary['registry_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
