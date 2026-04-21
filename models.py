from pydantic import BaseModel, Field, field_validator  
from typing import List, Optional
from enum import Enum

class SeverityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    CRITICAL = "critical"

class RiskLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class PatientHistory(BaseModel):
    current_medications: List[str] = Field(
        default=[],
        description="Drugs the patient is already taking"
    )
    known_allergies: List[str] = Field(
        default=[],
        description="Drug names or drug classes (e.g., 'Penicillin', 'NSAIDs')"
    )
    conditions: List[str] = Field(
        default=[],
        description="Medical conditions (e.g., 'kidney disease', 'diabetes')"
    )
    age: Optional[int] = Field(
        default=None,
        ge=0,
        le=150,
        description="Patient age in years"
    )
    weight_kg: Optional[float] = Field(
        default=None,
        gt=0,
        description="Patient weight in kilograms"
    )

    @field_validator('current_medications', 'known_allergies', 'conditions', mode='before')
    @classmethod
    def normalize_strings(cls, v):
        if isinstance(v, list):
            cleaned = list({item.strip().lower() for item in v if item.strip()})
            return cleaned
        return v

class DrugSafetyRequest(BaseModel):
    proposed_medicines: List[str] = Field(
        ...,
        min_length=1,
        description="List of new medicines the doctor wants to prescribe"
    )
    patient_history: PatientHistory = Field(
        default_factory=PatientHistory,
        description="Patient's full medical history"
    )

    @field_validator('proposed_medicines', mode='before')
    @classmethod
    def normalize_medicines(cls, v):
        if isinstance(v, list):
            if len(v) == 0:
                raise ValueError("proposed_medicines cannot be empty")
            seen = set()
            cleaned = []
            for item in v:
                normalized = item.strip().lower()
                if not normalized:
                    continue
                if normalized not in seen:
                    seen.add(normalized)
                    cleaned.append(normalized)
            if not cleaned:
                raise ValueError("proposed_medicines contains no valid drug names")
            return cleaned
        return v

class DrugInteraction(BaseModel):
    drug_a: str
    drug_b: str
    severity: SeverityLevel
    mechanism: str
    clinical_recommendation: str
    source_confidence: str

class AllergyAlert(BaseModel):
    medicine: str
    reason: str
    severity: SeverityLevel

class ContraindicationAlert(BaseModel):
    medicine: str
    condition: str
    reason: str
    severity: SeverityLevel

class RiskScoreBreakdown(BaseModel):
    base_score: int
    interaction_penalty: int
    allergy_penalty: int
    contraindication_penalty: int
    high_severity_multiplier: float

class DrugSafetyResponse(BaseModel):
    interactions: List[DrugInteraction] = []
    allergy_alerts: List[AllergyAlert] = []
    contraindication_alerts: List[ContraindicationAlert] = []
    safe_to_prescribe: bool
    overall_risk_level: RiskLevel
    requires_doctor_review: bool
    patient_risk_score: int = Field(ge=0, le=100)
    risk_score_breakdown: Optional[RiskScoreBreakdown] = None
    source: str
    cache_hit: bool
    processing_time_ms: int