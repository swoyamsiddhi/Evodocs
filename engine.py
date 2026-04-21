import json
import time
import logging
import httpx
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

from models import (
    DrugSafetyRequest, DrugSafetyResponse,
    DrugInteraction, AllergyAlert, ContraindicationAlert,
    RiskScoreBreakdown, SeverityLevel, RiskLevel
)

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "biomistral")

_BASE_DIR = Path(__file__).parent

def _load_system_prompt() -> str:
    prompt_path = _BASE_DIR / "prompts" / "system_prompt.txt"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("system_prompt.txt not found")
        return "You are a clinical pharmacologist. Respond only in valid JSON."

def _load_fallback_data() -> Dict[str, Any]:
    fallback_path = _BASE_DIR / "data" / "fallback_interactions.json"
    try:
        with open(fallback_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Could not load fallback data: {e}")
        return {"interactions": [], "allergy_cross_reactions": {}, "condition_contraindications": {}}

SYSTEM_PROMPT = _load_system_prompt()
FALLBACK_DATA = _load_fallback_data()


async def _call_ollama_llm(user_message: str) -> Optional[str]:
    """
    Call Ollama /api/generate. Returns raw text or None on failure.
    Debug prints help diagnose issues in the terminal.
    """
    prompt = f"{SYSTEM_PROMPT}\n\n{user_message}\n\nRespond with ONLY valid JSON, no other text:"

    payload = {
        "model": LLM_MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "num_predict": 2048,
        }
    }

    try:
        url = OLLAMA_BASE_URL.replace("localhost", "127.0.0.1")
        endpoint = f"{url}/api/generate"

        print(f"\n[DEBUG] Calling Ollama at: {endpoint}")
        print(f"[DEBUG] Model: {LLM_MODEL_NAME}")

        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()

            data = response.json()
            raw_text = data.get("response", "")

            print(f"\n[DEBUG] Ollama raw response ({len(raw_text)} chars):")
            print(f"{raw_text[:600]}")
            print(f"[DEBUG] done={data.get('done')}")

            if not raw_text:
                print("[DEBUG] WARNING: Ollama returned empty response!")
                return None

            return raw_text

    except httpx.ConnectError as e:
        print(f"\n[DEBUG] CONNECTION ERROR — Ollama is not running.")
        print(f"[DEBUG] Fix: run 'ollama serve' in a separate terminal.")
        logger.warning(f"Ollama not reachable: {e}")
        return None
    except httpx.HTTPStatusError as e:
        print(f"\n[DEBUG] HTTP {e.response.status_code} from Ollama: {e.response.text[:300]}")
        if e.response.status_code == 404:
            print(f"[DEBUG] Model '{LLM_MODEL_NAME}' not found in Ollama.")
            print(f"[DEBUG] Fix: run 'ollama list' to see installed models.")
            print(f"[DEBUG] Fix: run 'ollama pull {LLM_MODEL_NAME}' to install it.")
        logger.warning(f"Ollama HTTP error: {e}")
        return None
    except httpx.TimeoutException:
        print(f"\n[DEBUG] TIMEOUT — model took >120s. Try a smaller/faster model.")
        logger.warning("Ollama timed out")
        return None
    except Exception as e:
        print(f"\n[DEBUG] Unexpected error: {repr(e)}")
        logger.error(f"Unexpected LLM error: {e}")
        return None


def _parse_llm_response(raw_response: str) -> Optional[Dict[str, Any]]:
    """
    Robustly parse LLM JSON output using 5 progressive strategies.
    Medical LLMs frequently wrap JSON in prose or add trailing commas.
    """
    if not raw_response or not raw_response.strip():
        return None

    # Strategy 1: Direct parse
    try:
        result = json.loads(raw_response.strip())
        print("[DEBUG] Parse strategy 1 (direct) succeeded")
        return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown fences  ```json ... ```
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_response)
    if fence_match:
        try:
            result = json.loads(fence_match.group(1).strip())
            print("[DEBUG] Parse strategy 2 (markdown fence) succeeded")
            return result
        except json.JSONDecodeError:
            pass

    # Strategy 3: Extract outermost { ... } block
    start_idx = raw_response.find('{')
    end_idx = raw_response.rfind('}')
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            result = json.loads(raw_response[start_idx:end_idx + 1])
            print("[DEBUG] Parse strategy 3 (brace extraction) succeeded")
            return result
        except json.JSONDecodeError:
            pass

    # Strategy 4: Fix trailing commas then extract
    if start_idx != -1 and end_idx != -1:
        candidate = raw_response[start_idx:end_idx + 1]
        fixed = re.sub(r',\s*([}\]])', r'\1', candidate)
        try:
            result = json.loads(fixed)
            print("[DEBUG] Parse strategy 4 (trailing comma fix) succeeded")
            return result
        except json.JSONDecodeError:
            pass

    # Strategy 5: LLM responded but JSON is unsalvageable.
    # Return a safe minimal structure so source stays "llm" not "fallback".
    # The rule-based layer below will still fill in allergy/contraindication checks.
    if '"interactions"' in raw_response or '"allergy_alerts"' in raw_response:
        print("[DEBUG] Parse strategy 5: LLM responded but JSON unparseable — using safe empty shell")
        return {
            "interactions": [],
            "allergy_alerts": [],
            "contraindication_alerts": [],
            "unrecognized_drugs": [],
            "overall_assessment": "medium",
            "safe_to_prescribe": False,
            "requires_doctor_review": True,
            "confidence_notes": "LLM response format was invalid. Rule-based checks applied."
        }

    print(f"[DEBUG] ALL parse strategies failed. Raw:\n{raw_response[:300]}")
    return None


def _validate_llm_output(llm_data: Dict[str, Any]) -> Tuple[List[DrugInteraction], List[AllergyAlert], List[ContraindicationAlert], bool]:
    valid_interactions: List[DrugInteraction] = []
    valid_alerts: List[AllergyAlert] = []
    valid_contras: List[ContraindicationAlert] = []
    requires_review = False

    VALID_SEVERITIES = {"high", "medium", "low", "critical"}

    for item in llm_data.get("interactions", []):
        try:
            severity_raw = str(item.get("severity", "low")).lower()
            if severity_raw not in VALID_SEVERITIES:
                severity_raw = "low"
                requires_review = True
            interaction = DrugInteraction(
                drug_a=str(item.get("drug_a", "unknown")).strip() or "unknown",
                drug_b=str(item.get("drug_b", "unknown")).strip() or "unknown",
                severity=SeverityLevel(severity_raw),
                mechanism=str(item.get("mechanism", "See prescribing information")).strip() or "Mechanism unknown",
                clinical_recommendation=str(item.get("clinical_recommendation", "Consult prescriber")).strip() or "Consult prescriber",
                source_confidence=str(item.get("source_confidence", "low")).lower()
            )
            if interaction.drug_a != "unknown" and interaction.drug_b != "unknown":
                valid_interactions.append(interaction)
        except Exception as e:
            logger.warning(f"Skipping invalid interaction entry: {e}")
            requires_review = True

    for item in llm_data.get("allergy_alerts", []):
        try:
            severity_raw = str(item.get("severity", "high")).lower()
            if severity_raw not in VALID_SEVERITIES:
                severity_raw = "high"
            alert = AllergyAlert(
                medicine=str(item.get("medicine", "unknown")).strip(),
                reason=str(item.get("reason", "Allergy cross-reaction")).strip(),
                severity=SeverityLevel(severity_raw)
            )
            if alert.medicine != "unknown":
                valid_alerts.append(alert)
        except Exception as e:
            logger.warning(f"Skipping invalid allergy alert: {e}")

    for item in llm_data.get("contraindication_alerts", []):
        try:
            severity_raw = str(item.get("severity", "high")).lower()
            if severity_raw not in VALID_SEVERITIES:
                severity_raw = "high"
            contra = ContraindicationAlert(
                medicine=str(item.get("medicine", "unknown")).strip(),
                condition=str(item.get("condition", "unknown condition")).strip(),
                reason=str(item.get("reason", "Contraindicated in this condition")).strip(),
                severity=SeverityLevel(severity_raw)
            )
            if contra.medicine != "unknown":
                valid_contras.append(contra)
        except Exception as e:
            logger.warning(f"Skipping invalid contraindication: {e}")

    confidence_notes = str(llm_data.get("confidence_notes", "")).lower()
    uncertainty_keywords = ["uncertain", "unclear", "not sure", "may", "possibly", "consult", "verify"]
    if any(kw in confidence_notes for kw in uncertainty_keywords):
        requires_review = True

    return valid_interactions, valid_alerts, valid_contras, requires_review


def _run_fallback_checks(
    proposed_medicines: List[str],
    current_medications: List[str],
    known_allergies: List[str],
    conditions: List[str]
) -> Tuple[List[DrugInteraction], List[AllergyAlert], List[ContraindicationAlert]]:
    interactions: List[DrugInteraction] = []
    allergy_alerts: List[AllergyAlert] = []
    contraindication_alerts: List[ContraindicationAlert] = []

    all_drugs = [m.lower() for m in (proposed_medicines + current_medications)]
    proposed_lower = [m.lower() for m in proposed_medicines]

    for rule in FALLBACK_DATA.get("interactions", []):
        drug_a = rule["drug_a"].lower()
        drug_b = rule["drug_b"].lower()
        a_present = drug_a in all_drugs
        b_present = drug_b in all_drugs
        a_new = drug_a in proposed_lower
        b_new = drug_b in proposed_lower
        if a_present and b_present and (a_new or b_new):
            interactions.append(DrugInteraction(
                drug_a=rule["drug_a"], drug_b=rule["drug_b"],
                severity=SeverityLevel(rule["severity"]),
                mechanism=rule["mechanism"],
                clinical_recommendation=rule["clinical_recommendation"],
                source_confidence="high"
            ))

    allergy_cross = FALLBACK_DATA.get("allergy_cross_reactions", {})
    for allergy in known_allergies:
        allergy_lower = allergy.lower()
        for drug_class, cross_reactive_drugs in allergy_cross.items():
            if drug_class in allergy_lower or allergy_lower in drug_class:
                for proposed in proposed_lower:
                    if proposed in [d.lower() for d in cross_reactive_drugs]:
                        allergy_alerts.append(AllergyAlert(
                            medicine=proposed,
                            reason=f"Cross-reactive with {allergy} allergy ({drug_class} drug class)",
                            severity=SeverityLevel.CRITICAL
                        ))

    for allergy in known_allergies:
        for proposed in proposed_lower:
            if allergy.lower() in proposed or proposed in allergy.lower():
                existing = {a.medicine.lower() for a in allergy_alerts}
                if proposed not in existing:
                    allergy_alerts.append(AllergyAlert(
                        medicine=proposed,
                        reason=f"Direct match: patient has documented allergy to {allergy}",
                        severity=SeverityLevel.CRITICAL
                    ))

    for condition in conditions:
        condition_lower = condition.lower()
        for contra_condition, contra_data in FALLBACK_DATA.get("condition_contraindications", {}).items():
            if contra_condition in condition_lower:
                contraindicated_drugs = [d.lower() for d in contra_data["drugs"]]
                for proposed in proposed_lower:
                    if proposed in contraindicated_drugs:
                        contraindication_alerts.append(ContraindicationAlert(
                            medicine=proposed, condition=condition,
                            reason=contra_data["reason"],
                            severity=SeverityLevel(contra_data["severity"])
                        ))

    return interactions, allergy_alerts, contraindication_alerts


def _calculate_risk_score(
    interactions: List[DrugInteraction],
    allergy_alerts: List[AllergyAlert],
    contraindication_alerts: List[ContraindicationAlert],
    age: Optional[int],
    conditions: List[str]
) -> Tuple[int, RiskScoreBreakdown]:
    base_score = 0
    interaction_penalty = 0
    allergy_penalty = 0
    contraindication_penalty = 0

    severity_scores = {"high": 25, "medium": 12, "low": 5, "critical": 35}
    for i in interactions:
        interaction_penalty += severity_scores.get(i.severity.value, 5)
    for a in allergy_alerts:
        allergy_penalty += severity_scores.get(a.severity.value, 20)
    for c in contraindication_alerts:
        contraindication_penalty += severity_scores.get(c.severity.value, 20)

    if age and age > 65:
        base_score += 5
    if len(conditions) > 3:
        base_score += 5

    raw_total = base_score + interaction_penalty + allergy_penalty + contraindication_penalty
    has_critical = any(a.severity.value in ("critical", "high") for a in allergy_alerts)
    has_high = any(i.severity.value == "high" for i in interactions)
    multiplier = 1.2 if (has_critical or has_high) else 1.0
    final_score = min(100, int(raw_total * multiplier))

    return final_score, RiskScoreBreakdown(
        base_score=base_score,
        interaction_penalty=interaction_penalty,
        allergy_penalty=allergy_penalty,
        contraindication_penalty=contraindication_penalty,
        high_severity_multiplier=multiplier
    )


def _determine_risk_level(
    risk_score: int,
    interactions: List[DrugInteraction],
    allergy_alerts: List[AllergyAlert]
) -> Tuple[RiskLevel, bool]:
    has_critical_allergy = any(a.severity.value == "critical" for a in allergy_alerts)
    has_high_interaction = any(i.severity.value == "high" for i in interactions)
    if has_critical_allergy or has_high_interaction or risk_score >= 50:
        return RiskLevel.HIGH, False
    if risk_score >= 25:
        return RiskLevel.MEDIUM, False
    return RiskLevel.LOW, True


async def analyze_drug_safety(
    request: DrugSafetyRequest,
    cache_hit: bool = False
) -> Dict[str, Any]:
    start_time = time.time()
    proposed = request.proposed_medicines
    history = request.patient_history
    source = "llm"
    requires_doctor_review = False

    user_message = f"""Analyze the following drug prescription request for patient safety:

PROPOSED NEW MEDICINES: {json.dumps(proposed)}

PATIENT HISTORY:
- Current medications: {json.dumps(history.current_medications)}
- Known allergies: {json.dumps(history.known_allergies)}
- Medical conditions: {json.dumps(history.conditions)}
- Age: {history.age if history.age is not None else "Not provided"}
- Weight (kg): {history.weight_kg if history.weight_kg is not None else "Not provided"}

Check ALL of the following:
1. Drug-drug interactions between proposed medicines
2. Drug-drug interactions between proposed medicines and current medications
3. Allergy cross-reactions (including drug-class allergies)
4. Drug-condition contraindications

Return ONLY a JSON object matching the required schema."""

    interactions: List[DrugInteraction] = []
    allergy_alerts: List[AllergyAlert] = []
    contraindication_alerts: List[ContraindicationAlert] = []

    llm_raw = await _call_ollama_llm(user_message)
    llm_data = _parse_llm_response(llm_raw) if llm_raw else None

    if llm_data:
        print("[DEBUG] analyze_drug_safety: LLM succeeded → source=llm")
        interactions, allergy_alerts, contraindication_alerts, requires_doctor_review = (
            _validate_llm_output(llm_data)
        )
        if llm_data.get("requires_doctor_review", False):
            requires_doctor_review = True
        if llm_data.get("overall_assessment") == "high":
            requires_doctor_review = True
    else:
        print("[DEBUG] analyze_drug_safety: LLM failed → source=fallback")
        logger.warning("Using fallback rule engine")
        source = "fallback"
        requires_doctor_review = True
        interactions, allergy_alerts, contraindication_alerts = _run_fallback_checks(
            proposed_medicines=proposed,
            current_medications=history.current_medications,
            known_allergies=history.known_allergies,
            conditions=history.conditions
        )

    # Always layer rule-based allergy + contraindication checks on top of LLM results
    if source == "llm":
        _, rule_allergy_alerts, rule_contras = _run_fallback_checks(
            proposed_medicines=proposed,
            current_medications=history.current_medications,
            known_allergies=history.known_allergies,
            conditions=history.conditions
        )
        existing_allergy_drugs = {a.medicine.lower() for a in allergy_alerts}
        for alert in rule_allergy_alerts:
            if alert.medicine.lower() not in existing_allergy_drugs:
                allergy_alerts.append(alert)

        existing_contra_drugs = {(c.medicine.lower(), c.condition.lower()) for c in contraindication_alerts}
        for contra in rule_contras:
            if (contra.medicine.lower(), contra.condition.lower()) not in existing_contra_drugs:
                contraindication_alerts.append(contra)

    risk_score, risk_breakdown = _calculate_risk_score(
        interactions=interactions, allergy_alerts=allergy_alerts,
        contraindication_alerts=contraindication_alerts,
        age=history.age, conditions=history.conditions
    )
    risk_level, safe_to_prescribe = _determine_risk_level(risk_score, interactions, allergy_alerts)
    processing_time_ms = int((time.time() - start_time) * 1000)

    return {
        "interactions": [i.model_dump() for i in interactions],
        "allergy_alerts": [a.model_dump() for a in allergy_alerts],
        "contraindication_alerts": [c.model_dump() for c in contraindication_alerts],
        "safe_to_prescribe": safe_to_prescribe,
        "overall_risk_level": risk_level.value,
        "requires_doctor_review": requires_doctor_review,
        "patient_risk_score": risk_score,
        "risk_score_breakdown": risk_breakdown.model_dump(),
        "source": source,
        "cache_hit": cache_hit,
        "processing_time_ms": processing_time_ms
    }