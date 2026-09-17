#!/usr/bin/env python3
"""
Live smoke test for the source-verification engine.

Hits the real ATS APIs (needs network). For every supported ATS it discovers a
genuinely open requisition from the public board, then verifies both the open
one and a deliberately-bogus one. Any mismatch is a regression.

    python scripts/verify_source_smoke.py
    python scripts/verify_source_smoke.py --verbose
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests  # noqa: E402

from src.services.source_verify import (  # noqa: E402
    SourceVerifier,
    STATUS_CLOSED,
    STATUS_OPEN,
)

TIMEOUT = 15


def first_job(api_url: str, picker) -> Optional[Dict[str, Any]]:
    try:
        resp = requests.get(api_url, timeout=TIMEOUT)
        resp.raise_for_status()
        return picker(resp.json())
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  discovery failed for {api_url}: {exc}")
        return None


def build_cases() -> List[Tuple[str, str, Optional[str], str]]:
    """
    Returns (label, url, token_hint, expected_status) tuples.

    ``expected_status`` is what the engine must return; ``unknown`` cases are
    reported but never fail the run (upstream may be down or rate-limiting).
    """
    cases: List[Tuple[str, str, Optional[str], str]] = []
    gh = first_job(
        "https://boards-api.greenhouse.io/v1/boards/stripe/jobs",
        lambda d: d["jobs"][0],
    )
    if gh:
        cases += [
            ("greenhouse open", f"https://job-boards.greenhouse.io/stripe/jobs/{gh['id']}", None, STATUS_OPEN),
            ("greenhouse closed", "https://job-boards.greenhouse.io/stripe/jobs/999999999", None, STATUS_CLOSED),
            ("greenhouse gh_jid", f"https://stripe.com/jobs/search?gh_jid={gh['id']}", "stripe", STATUS_OPEN),
        ]

    lever = first_job(
        "https://api.lever.co/v0/postings/palantir?mode=json",
        lambda d: d[0],
    )
    if lever:
        cases += [
            ("lever open", lever["hostedUrl"], None, STATUS_OPEN),
            ("lever closed",
             "https://jobs.lever.co/palantir/00000000-0000-0000-0000-000000000000", None, STATUS_CLOSED),
        ]

    ashby = first_job(
        "https://api.ashbyhq.com/posting-api/job-board/snowflake",
        lambda d: d["jobs"][0],
    )
    if ashby:
        cases += [
            ("ashby open", f"https://jobs.ashbyhq.com/snowflake/{ashby['id']}", None, STATUS_OPEN),
            ("ashby closed",
             "https://jobs.ashbyhq.com/snowflake/00000000-0000-0000-0000-000000000000", None, STATUS_CLOSED),
        ]

    workable = first_job(
        "https://apply.workable.com/api/v1/widget/accounts/huggingface?details=true",
        lambda d: d["jobs"][0],
    )
    if workable:
        cases += [
            ("workable open",
             f"https://apply.workable.com/huggingface/j/{workable['shortcode']}", None, STATUS_OPEN),
            ("workable closed", "https://apply.workable.com/huggingface/j/ZZZZZZZZZZ", None, STATUS_CLOSED),
        ]

    cases += [
        ("workday open",
         "https://sailpoint.wd1.myworkdayjobs.com/en-US/SailPoint/job/United-States/"
         "Principal-Customer-Success-Manager_R014152", None, "any"),
        ("workday closed",
         "https://sailpoint.wd1.myworkdayjobs.com/en-US/SailPoint/job/United-States/"
         "Nonexistent-Job_R999999", None, STATUS_CLOSED),
        ("redirect unwrap",
         "https://www.linkedin.com/redir/redirect?url="
         "https%3A%2F%2Fjobs.lever.co%2Fpalantir%2F00000000-0000-0000-0000-000000000000", None, STATUS_CLOSED),
        ("garbage url", "not a url at all", None, "any"),
    ]
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    verifier = SourceVerifier(timeout=TIMEOUT)
    cases = build_cases()
    failures = 0
    for label, url, hint, expected in cases:
        result = verifier.verify(url, token_hint=hint)
        ok = expected == "any" or result.status == expected
        if not ok:
            failures += 1
        flag = "✅" if ok else "❌"
        print(f"{flag} {label:18} {result.status:8} conf={result.confidence:<5} "
              f"ats={result.ats:15} {result.reason[:58]}")
        if args.verbose:
            print(f"     {url}")

    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
