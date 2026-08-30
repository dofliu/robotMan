"""Execute the currently implemented bounded V1 oracle inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from vv_oracles import run_static_double_support_oracle


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bounded V1 physics oracles")
    parser.add_argument(
        "--raw-output",
        type=Path,
        help="write a non-overwriting JSON evidence bundle with every physics step",
    )
    args = parser.parse_args()

    result = run_static_double_support_oracle(include_raw_trace=args.raw_output is not None)
    if args.raw_output is not None:
        payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        # 使用 exclusive-create，避免同名 evidence 被悄悄覆寫。
        with args.raw_output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
        raw_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        result.pop("raw_trace")
        result["raw_artifact"] = {
            "path": str(args.raw_output),
            "sha256": raw_sha256,
            "size_bytes": len(payload.encode("utf-8")),
            "write_policy": "EXCLUSIVE_CREATE_NO_OVERWRITE",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
