"""Feedback capture and candidate rule generation for the Xiaoman router."""

from __future__ import annotations

from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SENSITIVE_KEY_PARTS = (
    "secret",
    "token",
    "password",
    "authorization",
    "email",
    "tel",
    "phone",
    "mobile",
    "contact",
    "content",
)


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact_trace(value: Any, *, _key: str = "") -> Any:
    """Return a JSON-safe trace with credentials and direct contact data removed."""

    if _key and _is_sensitive(_key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(key): redact_trace(item, _key=str(key)) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact_trace(item, _key=_key) for item in value]
    return value


def build_candidate(trace: dict[str, Any], user_correction: str | None = None) -> dict[str, Any]:
    """Turn an observed trace and optional correction into a reviewable case."""

    redacted = redact_trace(deepcopy(trace))
    intent = str(redacted.get("intent", "unknown"))
    operations = list(redacted.get("operations", []))
    correction = (user_correction or "").strip()

    if correction:
        category = "intent_or_operation"
        confidence = "high"
        proposed_action = "review the intent and operation sequence against the correction"
    elif redacted.get("status") in {"error", "partial"}:
        category = "execution"
        confidence = "medium"
        proposed_action = "add a regression case for the observed failure"
    else:
        category = "observation"
        confidence = "low"
        proposed_action = "retain as evidence without changing routing rules"

    evidence = [intent, *[str(operation) for operation in operations]]
    if correction:
        evidence.append(correction)
    case_id = hashlib.sha256("|".join(evidence).encode("utf-8")).hexdigest()[:12]
    return {
        "case_id": case_id,
        "category": category,
        "confidence": confidence,
        "observed_intent": intent,
        "observed_operations": operations,
        "query": redacted.get("query"),
        "expected_intent": redacted.get("expected_intent"),
        "expected_operations": redacted.get("expected_operations"),
        "evidence": evidence,
        "user_correction": correction or None,
        "proposed_action": proposed_action,
    }


def record_trace(path: str | Path, trace: dict[str, Any]) -> None:
    """Append one redacted trace as JSONL, creating parent directories."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact_trace(trace), ensure_ascii=False) + "\n")


def append_candidate(path: str | Path, candidate: dict[str, Any]) -> None:
    """Append a human-readable candidate case to the learned-cases ledger."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n- **{case_id}** `{category}` / confidence `{confidence}`: {proposed_action}\n"
            "  - observed intent: `{observed_intent}`\n"
            "  - observed operations: `{operations}`\n".format(
                case_id=candidate["case_id"],
                category=candidate["category"],
                confidence=candidate["confidence"],
                proposed_action=candidate["proposed_action"],
                observed_intent=candidate["observed_intent"],
                operations=", ".join(candidate["observed_operations"]),
            )
        )
        if candidate.get("query"):
            handle.write(f"  - query: {candidate['query']}\n")
        if candidate.get("expected_intent"):
            handle.write(
                f"  - expected route: `{candidate['expected_intent']}` -> {', '.join(candidate.get('expected_operations') or [])}\n"
            )


def promote_case(path: str | Path, candidate: dict[str, Any], *, eval_path: str | Path) -> None:
    """Promote a candidate only after the current regression suite passes."""

    if not candidate.get("query") or not candidate.get("expected_intent") or not isinstance(candidate.get("expected_operations"), list):
        raise ValueError("candidate must include query, expected_intent, and expected_operations")
    from run_router_eval import evaluate

    evaluation_file = Path(eval_path)
    try:
        original = evaluation_file.read_text(encoding="utf-8")
        candidate_case = {
            "query": candidate["query"],
            "intent": candidate["expected_intent"],
            "operations": candidate["expected_operations"],
        }
        evaluation_file.write_text(
            original.rstrip() + "\n" + json.dumps(candidate_case, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        failures = evaluate(evaluation_file)
    except OSError as error:
        raise ValueError(f"regression suite is unavailable: {eval_path}") from error
    finally:
        if "original" in locals() and evaluation_file.exists():
            evaluation_file.write_text(original, encoding="utf-8")
    if failures:
        raise ValueError(f"candidate cannot be promoted: {len(failures)} regression failures")
    append_candidate(path, candidate)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Record or review redacted Xiaoman route evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record")
    record.add_argument("--path", required=True)
    record.add_argument("--trace-json", required=True)

    candidate = subparsers.add_parser("candidate")
    candidate.add_argument("--review-path", required=True, help="review ledger path")
    candidate.add_argument("--trace-json", required=True)
    candidate.add_argument("--correction")

    promote = subparsers.add_parser("promote")
    promote.add_argument("--learned-path", required=True, help="validated learned-cases path")
    promote.add_argument("--eval-path", required=True)
    promote.add_argument("--candidate-json", required=True)

    args = parser.parse_args()
    if args.command == "record":
        trace = json.loads(args.trace_json)
        if not isinstance(trace, dict):
            raise SystemExit("trace-json must be a JSON object")
        record_trace(args.path, trace)
    elif args.command == "candidate":
        trace = json.loads(args.trace_json)
        if not isinstance(trace, dict):
            raise SystemExit("trace-json must be a JSON object")
        review_path = Path(args.review_path)
        if review_path.name != "review-ledger.md":
            raise SystemExit("candidate output must be named review-ledger.md")
        append_candidate(review_path, build_candidate(trace, args.correction))
    else:
        candidate_value = json.loads(args.candidate_json)
        if not isinstance(candidate_value, dict):
            raise SystemExit("candidate-json must be a JSON object")
        learned_path = Path(args.learned_path)
        if learned_path.name != "learned-cases.md":
            raise SystemExit("promoted output must be named learned-cases.md")
        promote_case(learned_path, candidate_value, eval_path=args.eval_path)


if __name__ == "__main__":
    _main()

