"""Check that the teaching application imports no research module.

``TEACHING-BOUNDARY-V1``, registered in
``backend/teaching_boundary_registry.json`` and specified in
``docs/TEACHING_BOUNDARY.md``.

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
                             "teaching_boundary_registry.json")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TeachingBoundaryError(Exception):
    """The teaching application's import closure disagrees with the registry."""


class Violation(NamedTuple):
    kind: str
    module: str
    detail: str

    def render(self) -> str:
        return f"{self.kind}: {self.module}\n    {self.detail}"


def load_registry(path: str = REGISTRY_PATH) -> dict:
    """Read the registry and reject a shape the checker cannot act on."""
    with open(path, encoding="utf-8") as handle:
        registry = json.load(handle)
    for key in ("registry_id", "package_root", "entry_points", "teaching_modules"):
        if key not in registry:
            raise TeachingBoundaryError(f"registry is missing the {key!r} key")
    if not registry["entry_points"]:
        raise TeachingBoundaryError("registry lists no entry points")
    if not registry["teaching_modules"]:
        raise TeachingBoundaryError("registry lists no teaching modules")
    for entry in registry["entry_points"]:
        if entry not in registry["teaching_modules"]:
            raise TeachingBoundaryError(
                f"entry point {entry!r} is not itself a registered teaching module")
    if len(set(registry["teaching_modules"])) != len(registry["teaching_modules"]):
        raise TeachingBoundaryError("teaching_modules contains a duplicate")
    return registry


def module_path(root: str, module: str) -> Optional[str]:
    """The file backing a dotted module name under *root*, or None."""
    base = os.path.join(root, module.replace(".", os.sep))
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
    return names


def closure(registry: dict, repo_root: str = REPO_ROOT) -> Dict[str, List[str]]:
    """Reachable local modules, each with the import path that first reached it."""
    root = os.path.join(repo_root, registry["package_root"])
    reached: Dict[str, List[str]] = {}
    queue: List[List[str]] = [[entry] for entry in registry["entry_points"]]
    while queue:
        trail = queue.pop(0)
        module = trail[-1]
        if module in reached:
            continue
        path = module_path(root, module)
        if path is None:
            raise TeachingBoundaryError(
                f"registered entry point {module!r} has no file under {registry['package_root']}/")
        reached[module] = trail
        for name in sorted(imported_names(path)):
            if module_path(root, name) is not None:
                queue.append(trail + [name])
    return reached


def check(registry: dict, repo_root: str = REPO_ROOT) -> List[Violation]:
    """Check the closure against the registry. Empty result means clean."""
    reached = closure(registry, repo_root)
    registered = set(registry["teaching_modules"])
    violations: List[Violation] = []

    for module in sorted(set(reached) - registered):
        violations.append(Violation(
            "RESEARCH_MODULE_IN_TEACHING_CLOSURE", module,
            "reached by " + " -> ".join(reached[module]) + ". The teaching application "
            "must not import research code; cut the import, or register the module "
            "deliberately if it really is part of the teaching product."))

    for module in sorted(registered - set(reached)):
        violations.append(Violation(
            "STALE_REGISTRY_ENTRY", module,
            "registered as a teaching module but nothing in the closure loads it. An "
            "allowlist that keeps entries nothing uses would admit a module back "
            "unnoticed; remove it from the registry."))
    return violations


def verify(registry_path: str = REGISTRY_PATH, repo_root: str = REPO_ROOT) -> dict:
    """Fail closed: raise TeachingBoundaryError unless the closure matches exactly."""
    registry = load_registry(registry_path)
    violations = check(registry, repo_root)
    if violations:
        body = "\n\n".join(violation.render() for violation in violations)
        raise TeachingBoundaryError(
            f"{len(violations)} teaching-boundary violation(s) against "
            f"{os.path.basename(registry_path)}:\n\n{body}")
    reached = closure(registry, repo_root)
    root = os.path.join(repo_root, registry["package_root"])
    lines = sum(sum(1 for _ in open(module_path(root, m), encoding="utf-8")) for m in reached)
    return {
        "registry_id": registry["registry_id"],
        "modules": len(reached),
        "lines": lines,
        "result": "TEACHING_BOUNDARY_CLEAN",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default=REGISTRY_PATH)
    parser.add_argument("--repo-root", default=REPO_ROOT)
    parser.add_argument("--list", action="store_true",
                        help="print the teaching closure with line counts and exit")
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.registry)
    except TeachingBoundaryError as error:
        print(f"REGISTRY INVALID: {error}", file=sys.stderr)
        return 2

    if args.list:
        root = os.path.join(args.repo_root, registry["package_root"])
        reached = closure(registry, args.repo_root)
        total = 0
        for module in sorted(reached):
            count = sum(1 for _ in open(module_path(root, module), encoding="utf-8"))
            total += count
            print(f"  {count:6d}  {module}")
        print(f"  {total:6d}  TOTAL ({len(reached)} modules)")
        return 0

    try:
        summary = verify(args.registry, args.repo_root)
    except TeachingBoundaryError as error:
        print(f"TEACHING BOUNDARY CHECK FAILED\n\n{error}", file=sys.stderr)
        return 1
    print(f"{summary['result']}: {summary['modules']} modules, {summary['lines']} lines, "
          f"registry {summary['registry_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
