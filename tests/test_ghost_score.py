"""Offline unit tests for the ghost-job scoring engine (no LLM, no network).

Run: ``pytest tests/test_ghost_score.py -q``
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.services.ghost_score import (
    GhostAnalyzer,
    days_since,
    heuristic_signals,
    _extract_json,
)

SPECIFIC_JD = (
    "We run Kubernetes on AWS with Terraform. Services are written in Go and Python, "
    "backed by Postgres and Kafka. You will own the quarterly roadmap for our RAG "
    "pipeline and vector database, and join the on-call rotation. " * 3
)

GHOSTY_JD = (
    "Our client is seeking a rockstar ninja for a fast-paced environment. "
    "Do all assigned tasks. Other duties as assigned. Join our talent pool for "
    "future opportunities. Competitive salary and excellent communication skills."
)


def test_fresh_specific_posting_is_low_risk():
    signals = heuristic_signals(
        "Senior Platform Engineer", "Acme", 5, "greenhouse", SPECIFIC_JD, "open"
    )
    assert signals["ghost_score"] <= 20
    assert signals["is_ghost_job"] is False
    assert signals["recommendation"] == "直接投递"


def test_stale_agency_evergreen_posting_is_high_risk():
    signals = heuristic_signals(
        "Software Engineer", "Mystery Staffing", 95, "unknown", GHOSTY_JD, "unknown"
    )
    assert signals["ghost_score"] >= 80
    assert signals["is_ghost_job"] is True
    assert signals["recommendation"] == "建议忽略"
    # The heaviest signals must surface, not whichever matched first
    assert any("95 天" in f for f in signals["risk_factors"])
    assert any("talent pool" in f for f in signals["risk_factors"])


def test_source_closed_forces_top_score_without_llm():
    verdict = GhostAnalyzer(provider="heuristic").analyze(
        job_title="Platform Engineer",
        company_name="Acme",
        post_age_days=3,
        source_type="greenhouse",
        jd_text=SPECIFIC_JD,
        source_status="closed",
    )
    assert verdict.ghost_score >= 95
    assert verdict.is_ghost_job is True
    assert verdict.recommendation == "建议忽略"
    assert verdict.provider == "source_ats"
    assert "已下架" in verdict.risk_factors[0]
    assert verdict.one_liner


def test_thresholds_30_and_60_days():
    young = heuristic_signals("Eng", "A", 10, "greenhouse", SPECIFIC_JD)
    mid = heuristic_signals("Eng", "A", 45, "greenhouse", SPECIFIC_JD)
    old = heuristic_signals("Eng", "A", 75, "greenhouse", SPECIFIC_JD)
    assert young["ghost_score"] < mid["ghost_score"] < old["ghost_score"]
    assert mid["ghost_score"] >= 30
    assert old["ghost_score"] >= 50


def test_missing_jd_penalised():
    signals = heuristic_signals("Eng", "A", 1, "greenhouse", "")
    assert any("JD 内容过短" in f for f in signals["risk_factors"])


def test_agency_wording_detected():
    signals = heuristic_signals(
        "Eng", "A", 1, "unknown",
        "On behalf of our client we are hiring. " + SPECIFIC_JD,
    )
    assert any("中介代招" in f or "中介" in f for f in signals["risk_factors"])


def test_heuristic_provider_never_calls_llm():
    analyzer = GhostAnalyzer(provider="keyword")
    assert analyzer._provider_chain() == []
    verdict = analyzer.analyze(job_title="Eng", company_name="A", post_age_days=1,
                               source_type="greenhouse", jd_text=SPECIFIC_JD)
    assert verdict.provider == "heuristic"


def test_days_since_accepts_many_formats():
    assert days_since(None) is None
    assert days_since("") is None
    assert days_since("garbage") is None
    iso = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    assert 2.9 < days_since(iso) < 3.1
    naive = (datetime.utcnow() - timedelta(days=10))
    assert 9.9 < days_since(naive) < 10.1
    epoch_ms = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp() * 1000)
    assert 0.9 < days_since(epoch_ms) < 1.1


def test_extract_json_handles_llm_noise():
    assert _extract_json('{"ghost_score": 80}')["ghost_score"] == 80
    assert _extract_json('```json\n{"ghost_score": 70}\n```')["ghost_score"] == 70
    assert _extract_json('Sure! {"ghost_score": 60,}')["ghost_score"] == 60
    assert _extract_json("no json here") is None
    assert _extract_json("[1,2,3]") is None


def test_merge_prefers_llm_but_clamps_bounds():
    baseline = heuristic_signals("Eng", "A", 5, "greenhouse", SPECIFIC_JD)
    verdict = GhostAnalyzer._merge(
        {"ghost_score": 999, "risk_factors": ["x"], "recommendation": "建议忽略",
         "one_liner": "hi", "_provider": "deepseek"},
        baseline,
    )
    assert verdict.ghost_score == 100
    assert verdict.provider == "deepseek"
    assert verdict.is_ghost_job is True


def test_merge_falls_back_when_llm_fields_missing():
    baseline = heuristic_signals("Eng", "A", 95, "unknown", GHOSTY_JD)
    verdict = GhostAnalyzer._merge({"ghost_score": "not-a-number"}, baseline)
    assert verdict.ghost_score == baseline["ghost_score"]
    assert verdict.risk_factors == baseline["risk_factors"]
    assert verdict.one_liner
