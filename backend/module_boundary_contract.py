"""Check each declared product boundary against what its entry points import.

``MODULE-BOUNDARY-V1``, registered in ``backend/module_boundary_registry.json``.
The teaching boundary is specified in ``docs/TEACHING_BOUNDARY.md``, the toolkit
boundary in ``docs/TOOLKIT_PORTABILITY.md``.

``PROJECT_ASSESSMENT`` section 4.1 proposes splitting this repository into two
products. Each split is a claim about imports, and both claims are checked here
by one rule, because they are the same rule: a boundary's transitive local
import closure must equal its registered module list exactly.

This supersedes ``TEACHING-BOUNDARY-V1``, which ran this code under a name that
could only ever describe one of the two boundaries. Copying it for the second
product would have reproduced the very failure this repository spent
``GATE-STATUS-SINGLE-SOURCE-V1`` and ``DERIVED-CLAIM-CONSISTENCY-V1`` learning
to catch: one fact, two implementations, drifting apart unwatched.

The two boundaries point in opposite directions, and that is the interesting
part. The teaching boundary stops the *application* reaching into research code.
The toolkit boundary stops the *library* reaching into the project at all --
strictly stronger, and measured true on 2026-09-17: the toolkit's closure is
exactly its seven modules while thirteen non-test project modules depend on it.
It already sits at the bottom of the dependency graph, where a library has to
sit; this keeps it there.

What this contract does NOT check is portability. An outside project can import
every toolkit module and still be unable to use it, because of closed ``Literal``
vocabularies and frozen claim boundaries. That audit lives in
``docs/TOOLKIT_PORTABILITY.md``. A clean boundary here must never be read as
"the toolkit is reusable today".

``PROJECT_ASSESSMENT`` section 4.1 claims the teaching simulator and the
research infrastructure "are already completely decoupled at the code level" and
that splitting them "needs no refactor, only a move".  Measured on 2026-09-17,
that was true of twelve of the thirteen modules the application loads and false
of one import line: ``main.py`` took ``public_training_inventory`` from
``rl/train_ppo.py``, so serving a read-only list of profiles reached a
1,292-line training driver whose profile schema validates against
``TRACKED-LINEAGE-TRAINING-V1``/``V2`` and the seed-variance protocol.  The
claim was one line away from true, and nothing would have told anyone if a
second line had appeared.

This contract is what makes the claim checkable.  The rule is a single
equality: the transitive *local* import closure of the registered entry points
must be exactly the registered module list.

Both directions of that equality earn their place.

A module in the closure but not the registry is the failure the boundary
exists for -- a research import crossing into the teaching product.  The error
names the import path that reached it, because "something imports
``v7_pilot_contract``" is not actionable and "``main`` imports ``live_sim``
imports ``v7_pilot_contract``" is.

A module in the registry but not the closure is a stale allowlist.  It sounds
harmless and is not: an allowlist that keeps entries nothing loads any more
grows into a list that would admit a module back without anyone noticing.  It
fails too, and is fixed by editing the registry deliberately.

The boundary is drawn around research *modules*, not around third-party weight.
The teaching closure does import ``stable_baselines3``, through ``controller_rl``
loading a PPO policy for the Live view; that is the teaching product doing its
job.  ``backend/rl/`` holds both sides -- ``policy_registry`` and
``training_inventory`` are teaching, ``train_ppo``, ``eval_policy``,
``humanoid_env`` and the runners are research -- which is exactly why the
boundary is enumerated rather than drawn at a directory.

Tests are out of scope: ``backend/test_*.py`` may import anything, because a
test is not the shipped application.

Imports are read statically from the AST, never by importing the modules, so
the check needs neither MuJoCo nor a GPU and runs under ``python -I -S``.  A
conditional or function-local import counts the same as a top-level one: the
question is what the application can reach, not what it reaches on one path.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from typing import Dict, List, NamedTuple, Optional, Sequence, Set

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "module_boundary_registry.json")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ModuleBoundaryError(Exception):
    """A product's import closure disagrees with its registered module list."""


class Violation(NamedTuple):
    boundary: str
    kind: str
    module: str
    detail: str

    def render(self) -> str:
        return f"[{self.boundary}] {self.kind}: {self.module}\n    {self.detail}"


def load_registry(path: str = REGISTRY_PATH) -> dict:
    """Read the registry and reject a shape the checker cannot act on."""
    with open(path, encoding="utf-8") as handle:
        registry = json.load(handle)
    for key in ("registry_id", "package_root", "boundaries"):
        if key not in registry:
            raise ModuleBoundaryError(f"registry is missing the {key!r} key")
    if not registry["boundaries"]:
        raise ModuleBoundaryError("registry declares no boundaries")
    for name, boundary in registry["boundaries"].items():
        if not boundary.get("entry_points"):
            raise ModuleBoundaryError(f"boundary {name!r} lists no entry points")
        if not boundary.get("modules"):
            raise ModuleBoundaryError(f"boundary {name!r} lists no modules")
        if len(set(boundary["modules"])) != len(boundary["modules"]):
            raise ModuleBoundaryError(f"boundary {name!r} lists a duplicate module")
        for entry in boundary["entry_points"]:
            if entry not in boundary["modules"]:
                raise ModuleBoundaryError(
                    f"boundary {name!r}: entry point {entry!r} is not one of its own modules")
    return registry


def module_path(root: str, module: str,
                search_path: Sequence[str] = ("",)) -> Optional[str]:
    """The file backing a dotted module name, or None.

    *search_path* holds directories relative to *root*, tried in order, and it
    models the real ``sys.path`` rather than an assumption about layout.  The
    assumption it replaces was that every module sits directly under
    ``package_root``; that stopped being true when section 4.1 product B moved
    into ``backend/toolkit/`` while keeping its FLAT sibling imports, and a
    flat name that resolves at runtime but not here would leave the closure
    blind to exactly the imports this contract exists to catch.
    """
    for directory in search_path:
        base = os.path.join(root, directory, module.replace(".", os.sep))
        for candidate in (base + ".py", os.path.join(base, "__init__.py")):
            if os.path.exists(candidate):
                return candidate
    return None


def imported_names(path: str) -> Set[str]:
    """Every module name *path* imports, from the AST, at any nesting depth."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            elif node.level:
                # ``from . import sibling`` carries no node.module at all, so
                # reading node.module alone makes a relative sibling import
                # invisible to the closure — a fail-open in a fail-closed
                # contract.  The imported names are the siblings.
                for alias in node.names:
                    names.add(alias.name)
    return names


def closure(registry: dict, boundary_name: str, repo_root: str = REPO_ROOT) -> Dict[str, List[str]]:
    """Reachable local modules for one boundary, each with its first import trail."""
    boundary = registry["boundaries"][boundary_name]
    root = os.path.join(repo_root, registry["package_root"])
    search_path = registry.get("module_search_path", [""])
    reached: Dict[str, List[str]] = {}
    queue: List[List[str]] = [[entry] for entry in boundary["entry_points"]]
    while queue:
        trail = queue.pop(0)
        module = trail[-1]
        if module in reached:
            continue
        path = module_path(root, module, search_path)
        if path is None:
            raise ModuleBoundaryError(
                f"boundary {boundary_name!r}: entry point {module!r} has no file under "
                f"{registry['package_root']}/")
        reached[module] = trail
        for name in sorted(imported_names(path)):
            if module_path(root, name, search_path) is not None:
                queue.append(trail + [name])
    return reached


def check(registry: dict, repo_root: str = REPO_ROOT) -> List[Violation]:
    """Check every declared boundary. Empty result means all are clean."""
    violations: List[Violation] = []
    for name in sorted(registry["boundaries"]):
        reached = closure(registry, name, repo_root)
        registered = set(registry["boundaries"][name]["modules"])

        for module in sorted(set(reached) - registered):
            violations.append(Violation(
                name, "MODULE_OUTSIDE_BOUNDARY", module,
                "reached by " + " -> ".join(reached[module]) + ". This product must not import "
                "it; cut the import, or register the module deliberately if it really belongs "
                "to the product."))

        for module in sorted(registered - set(reached)):
            violations.append(Violation(
                name, "STALE_REGISTRY_ENTRY", module,
                "registered for this boundary but nothing in its closure loads it. A list that "
                "keeps entries nothing uses would admit a module back unnoticed; remove it."))
    return violations


def verify(registry_path: str = REGISTRY_PATH, repo_root: str = REPO_ROOT) -> dict:
    """Fail closed: raise ModuleBoundaryError unless every boundary matches exactly."""
    registry = load_registry(registry_path)
    violations = check(registry, repo_root)
    if violations:
        body = "\n\n".join(violation.render() for violation in violations)
        raise ModuleBoundaryError(
            f"{len(violations)} module-boundary violation(s) against "
            f"{os.path.basename(registry_path)}:\n\n{body}")
    root = os.path.join(repo_root, registry["package_root"])
    search_path = registry.get("module_search_path", [""])
    summary = {}
    for name in sorted(registry["boundaries"]):
        reached = closure(registry, name, repo_root)
        summary[name] = {
            "modules": len(reached),
            "lines": sum(sum(1 for _ in open(module_path(root, m, search_path),
                                             encoding="utf-8"))
                         for m in reached),
        }
    return {
        "registry_id": registry["registry_id"],
        "boundaries": summary,
        "result": "MODULE_BOUNDARIES_CLEAN",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default=REGISTRY_PATH)
    parser.add_argument("--repo-root", default=REPO_ROOT)
    parser.add_argument("--list", action="store_true",
                        help="print each boundary's closure with line counts and exit")
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.registry)
    except ModuleBoundaryError as error:
        print(f"REGISTRY INVALID: {error}", file=sys.stderr)
        return 2

    if args.list:
        root = os.path.join(args.repo_root, registry["package_root"])
        search_path = registry.get("module_search_path", [""])
        for name in sorted(registry["boundaries"]):
            reached = closure(registry, name, args.repo_root)
            print(f"{name}: {registry['boundaries'][name]['what']}")
            total = 0
            for module in sorted(reached):
                count = sum(1 for _ in open(module_path(root, module, search_path),
                                            encoding="utf-8"))
                total += count
                print(f"  {count:6d}  {module}")
            print(f"  {total:6d}  TOTAL ({len(reached)} modules)\n")
        return 0

    try:
        summary = verify(args.registry, args.repo_root)
    except ModuleBoundaryError as error:
        print(f"MODULE BOUNDARY CHECK FAILED\n\n{error}", file=sys.stderr)
        return 1
    parts = ", ".join(f"{n} {d['modules']} modules/{d['lines']} lines"
                      for n, d in summary["boundaries"].items())
    print(f"{summary['result']}: {parts}, registry {summary['registry_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
