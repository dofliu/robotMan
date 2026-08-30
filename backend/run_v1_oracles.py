"""Execute the currently implemented bounded V1 oracle inventory."""

from __future__ import annotations

import json

from vv_oracles import run_static_double_support_oracle


def main() -> None:
    print(json.dumps(run_static_double_support_oracle(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
