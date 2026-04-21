import pytest
import asyncio
from unittest.mock import AsyncMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import DrugSafetyRequest, PatientHistory
from cache import build_cache_key, get_cached, set_cached
from engine import (
    _parse_llm_response,
    _validate_llm_output,
    _run_fallback_checks,
    _calculate_risk_score,
    analyze_drug_safety
)

class TestCacheKeyDeterminism:

    def test_order_independence_proposed(self):
        key1 = build_cache_key(["Aspirin", "Warfarin"], [])
        key2 = build_cache_key(["Warfarin", "Aspirin"], [])
        assert key1 == key2

    def test_order_independence_current_meds(self):
        key1 = build_cache_key(["Aspirin"], ["Metformin", "Lisinopril"])
        key2 = build_cache_key(["Aspirin"], ["Lisinopril", "Metformin"])
        assert key1 == key2

    def test_case_independence(self):
        key1 = build_cache_key(["ASPIRIN"], [])
        key2 = build_cache_key(["aspirin"], [])
        assert key1 == key2

    def test_different_drugs_different_keys(self):
        key1 = build_cache_key(["Aspirin"], [])
        key2 = build_cache_key(["Warfarin"], [])
        assert key1 != key2

    def test_cache_set_and_get(self):
        key = build_cache_key(["TestDrug"], [])
        test_data = {"interactions": [], "cache_hit": False}
        set_cached(key, test_data)
        retrieved = get_cached(key)
        assert retrieved is not None
        assert retrieved["interactions"] == []

class TestLLMResponseParsing:

    def test_valid_json(self):
        raw = '{"interactions": [], "allergy_alerts": []}'
        result = _parse_llm_response(raw)
        assert result is not None
        assert result["interactions"] == []

    def test_strips_markdown_fences(self):
        raw = '```json\n{"interactions": []}\n```'
        result = _parse_llm_response(raw)
        assert result is not None

    def test_extracts_json_from_surrounding_text(self):
        raw = 'Here is my analysis:\n{"interactions": []}\nEnd of response.'
        result = _parse_llm_response(raw)
        assert result is not None

    def test_invalid_json_returns_none(self):
        result = _parse_llm_response("This is not JSON at all")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_llm_response("")
        assert result is None

class TestFallbackEngine:

    def test_penicillin_allergy_flags_amoxicillin(self):
        _, allergy_alerts, _ = _run_fallback_checks(
            proposed_medicines=["amoxicillin"],
            current_medications=[],
            known_allergies=["penicillin"],
            conditions=[]
        )
        assert len(allergy_alerts) > 0
        assert any("penicillin" in a.reason.lower() for a in allergy_alerts)

    def test_warfarin_aspirin_interaction(self):
        interactions, _, _ = _run_fallback_checks(
            proposed_medicines=["aspirin"],
            current_medications=["warfarin"],
            known_allergies=[],
            conditions=[]
        )
        assert len(interactions) > 0
        assert any(i.severity.value == "high" for i in interactions)

    def test_kidney_disease_nsaid_contraindication(self):
        _, _, contras = _run_fallback_checks(
            proposed_medicines=["ibuprofen"],
            current_medications=[],
            known_allergies=[],
            conditions=["kidney disease"]
        )
        assert len(contras) > 0

    def test_no_false_positives_for_safe_combo(self):
        interactions, alerts, contras = _run_fallback_checks(
            proposed_medicines=["paracetamol"],
            current_medications=[],
            known_allergies=[],
            conditions=[]
        )
        assert len(alerts) == 0

class TestRiskScoring:

    def test_no_alerts_low_score(self):
        score, _ = _calculate_risk_score([], [], [], age=30, conditions=[])
        assert score == 0

    def test_high_severity_interaction_raises_score(self):
        from models import DrugInteraction, SeverityLevel
        interactions = [DrugInteraction(
            drug_a="warfarin", drug_b="aspirin",
            severity=SeverityLevel.HIGH,
            mechanism="test", clinical_recommendation="test",
            source_confidence="high"
        )]
        score, _ = _calculate_risk_score(interactions, [], [], age=30, conditions=[])
        assert score > 0

    def test_score_capped_at_100(self):
        from models import DrugInteraction, AllergyAlert, SeverityLevel
        interactions = [
            DrugInteraction(
                drug_a=f"drug{i}", drug_b=f"drug{i+1}",
                severity=SeverityLevel.HIGH,
                mechanism="test", clinical_recommendation="test",
                source_confidence="high"
            ) for i in range(10)
        ]
        score, _ = _calculate_risk_score(interactions, [], [], age=30, conditions=[])
        assert score <= 100

class TestFullPipeline:

    @pytest.mark.asyncio
    async def test_full_pipeline_with_llm_failure(self):
        request = DrugSafetyRequest(
            proposed_medicines=["ibuprofen"],
            patient_history=PatientHistory(
                current_medications=["warfarin"],
                known_allergies=[],
                conditions=["kidney disease"],
                age=65
            )
        )

        with patch("engine._call_ollama_llm", new_callable=AsyncMock, return_value=None):
            result = await analyze_drug_safety(request, cache_hit=False)

        assert result is not None
        assert "interactions" in result
        assert "allergy_alerts" in result
        assert "cache_hit" in result
        assert result["source"] == "fallback"
        assert result["requires_doctor_review"] is True
        assert len(result.get("contraindication_alerts", [])) > 0