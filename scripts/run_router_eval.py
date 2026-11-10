"""Run the deterministic routing regression set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from route_planner import plan_query


def evaluate(path: str | Path) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        case = json.loads(line)
        plan = plan_query(case["query"])
        actual = [operation.name for operation in plan.operations]
        if plan.intent != case["intent"] or actual != case["operations"]:
            failures.append(
                {
                    "line": line_number,
                    "query": case["query"],
                    "expected": {"intent": case["intent"], "operations": case["operations"]},
                    "actual": {"intent": plan.intent, "operations": actual},
                }
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    failures = evaluate(args.path)
    if failures:
        print(json.dumps(failures, ensure_ascii=False, indent=2))
        return 1
    print("router eval passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
