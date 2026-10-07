"""
Unit Test Suite for Triage Engine (Part B: White-Box Testing).
Provides 100% branch coverage and rigorous Boundary Value Analysis (BVA)
for vital signs thresholds (SpO2, Heart Rate, Systolic BP, Pain Scale).
"""

import pytest
from src.models import (
    TriageVitals,
    TriageCategory,
    MedicalValidationError,
)
from src.triage_engine import evaluate_triage, record_patient_triage
from src.auth_security import verify_record_checksum


# =============================================================================
# 1. Branch Coverage Testing (All Decision Paths)
# =============================================================================

class TestTriageBranchCoverage:
    """Tests every if/elif/else branch in the triage classification logic."""

    def test_branch_cat1_hypoxemia_only(self):
        """Cat 1 branch triggered exclusively by SpO2 < 90%."""
        vitals = TriageVitals(patient_id=1, heart_rate=75, systolic_bp=120, sp02=88.5, pain_score=2)
        res = evaluate_triage(vitals)
        assert res.category == TriageCategory.CATEGORY_1
        assert res.priority_score == 100
        assert res.max_wait_minutes == 0
        assert any("SpO2" in r for r in res.clinical_rationale)

    def test_branch_cat1_extreme_tachycardia_only(self):
        """Cat 1 branch triggered exclusively by HR > 140 bpm."""
        vitals = TriageVitals(patient_id=1, heart_rate=145, systolic_bp=120, sp02=98.0, pain_score=3)
        res = evaluate_triage(vitals)
        assert res.category == TriageCategory.CATEGORY_1
        assert res.priority_score == 100
        assert res.max_wait_minutes == 0
        assert any("Heart Rate" in r for r in res.clinical_rationale)

    def test_branch_cat1_hypotension_only(self):
        """Cat 1 branch triggered exclusively by Systolic BP < 80 mmHg."""
        vitals = TriageVitals(patient_id=1, heart_rate=80, systolic_bp=75, sp02=98.0, pain_score=1)
        res = evaluate_triage(vitals)
        assert res.category == TriageCategory.CATEGORY_1
        assert res.priority_score == 100
        assert any("Systolic BP" in r for r in res.clinical_rationale)

    def test_branch_cat1_multiple_critical_vitals(self):
        """Cat 1 branch with multiple simultaneous life-threatening parameters."""
        vitals = TriageVitals(patient_id=1, heart_rate=155, systolic_bp=70, sp02=82.0, pain_score=10)
        res = evaluate_triage(vitals)
        assert res.category == TriageCategory.CATEGORY_1
        assert res.priority_score == 100
        assert len(res.clinical_rationale) >= 3

    def test_branch_cat2_moderate_hypoxia_only(self):
        """Cat 2 branch triggered exclusively by 90% <= SpO2 <= 94%."""
        vitals = TriageVitals(patient_id=1, heart_rate=85, systolic_bp=120, sp02=92.0, pain_score=2)
        res = evaluate_triage(vitals)
        assert res.category == TriageCategory.CATEGORY_2
        assert res.priority_score == 75
        assert res.max_wait_minutes == 15

    def test_branch_cat2_moderate_tachycardia_only(self):
        """Cat 2 branch triggered exclusively by 110 <= HR <= 140 bpm."""
        vitals = TriageVitals(patient_id=1, heart_rate=125, systolic_bp=120, sp02=98.0, pain_score=3)
        res = evaluate_triage(vitals)
        assert res.category == TriageCategory.CATEGORY_2
        assert res.priority_score == 75
        assert res.max_wait_minutes == 15

    def test_branch_cat2_severe_pain_only(self):
        """Cat 2 branch triggered exclusively by Pain Score >= 8."""
        vitals = TriageVitals(patient_id=1, heart_rate=80, systolic_bp=120, sp02=98.0, pain_score=9)
        res = evaluate_triage(vitals)
        assert res.category == TriageCategory.CATEGORY_2
        assert res.priority_score == 75

    def test_branch_cat3_mild_tachycardia_only(self):
        """Cat 3 branch triggered exclusively by 100 <= HR < 110 bpm."""
        vitals = TriageVitals(patient_id=1, heart_rate=105, systolic_bp=120, sp02=98.0, pain_score=2)
        res = evaluate_triage(vitals)
        assert res.category == TriageCategory.CATEGORY_3
        assert res.priority_score == 50
        assert res.max_wait_minutes == 60

    def test_branch_cat3_moderate_pain_only(self):
        """Cat 3 branch triggered exclusively by 5 <= Pain Score <= 7."""
        vitals = TriageVitals(patient_id=1, heart_rate=78, systolic_bp=120, sp02=98.0, pain_score=6)
        res = evaluate_triage(vitals)
        assert res.category == TriageCategory.CATEGORY_3
        assert res.priority_score == 50
        assert res.max_wait_minutes == 60

    def test_branch_cat4_all_normal_vitals(self):
        """Cat 4 routine branch when all parameters are completely normal."""
        vitals = TriageVitals(patient_id=1, heart_rate=72, systolic_bp=120, sp02=99.0, pain_score=1)
        res = evaluate_triage(vitals)
        assert res.category == TriageCategory.CATEGORY_4
        assert res.priority_score == 20
        assert res.max_wait_minutes == 120


# =============================================================================
# 2. Boundary Value Analysis (BVA) Testing
# =============================================================================

class TestTriageBoundaryValueAnalysis:
    """Exhaustive boundary testing around critical medical cutoffs."""

    @pytest.mark.parametrize("spo2,expected_category,expected_score", [
        (89.0, TriageCategory.CATEGORY_1, 100),  # Just below 90%
        (89.9, TriageCategory.CATEGORY_1, 100),  # Immediately below 90%
        (90.0, TriageCategory.CATEGORY_2, 75),   # Exactly on 90% boundary
        (94.0, TriageCategory.CATEGORY_2, 75),   # Exactly on 94% boundary
        (94.1, TriageCategory.CATEGORY_4, 20),   # Immediately above 94%
        (95.0, TriageCategory.CATEGORY_4, 20),   # Normal baseline
    ])
    def test_bva_spo2_thresholds(self, spo2, expected_category, expected_score):
        """Tests exact mathematical boundaries for Blood Oxygen (SpO2)."""
        vitals = TriageVitals(patient_id=1, heart_rate=75, systolic_bp=120, sp02=spo2, pain_score=1)
        res = evaluate_triage(vitals)
        assert res.category == expected_category
        assert res.priority_score == expected_score

    @pytest.mark.parametrize("hr,expected_category,expected_score", [
        (99, TriageCategory.CATEGORY_4, 20),   # Upper bound of normal HR
        (100, TriageCategory.CATEGORY_3, 50),  # Lower bound of Cat 3
        (109, TriageCategory.CATEGORY_3, 50),  # Upper bound of Cat 3
        (110, TriageCategory.CATEGORY_2, 75),  # Lower bound of Cat 2
        (140, TriageCategory.CATEGORY_2, 75),  # Upper bound of Cat 2
        (141, TriageCategory.CATEGORY_1, 100), # Lower bound of Cat 1
    ])
    def test_bva_heart_rate_thresholds(self, hr, expected_category, expected_score):
        """Tests exact integer boundaries for Heart Rate (bpm)."""
        vitals = TriageVitals(patient_id=1, heart_rate=hr, systolic_bp=120, sp02=98.0, pain_score=1)
        res = evaluate_triage(vitals)
        assert res.category == expected_category
        assert res.priority_score == expected_score

    @pytest.mark.parametrize("sbp,expected_category,expected_score", [
        (79, TriageCategory.CATEGORY_1, 100),  # Critical Hypotension (< 80)
        (80, TriageCategory.CATEGORY_4, 20),   # Normotensive threshold
        (81, TriageCategory.CATEGORY_4, 20),   # Above cutoff
    ])
    def test_bva_systolic_bp_thresholds(self, sbp, expected_category, expected_score):
        """Tests exact integer boundaries for Systolic Blood Pressure (mmHg)."""
        vitals = TriageVitals(patient_id=1, heart_rate=75, systolic_bp=sbp, sp02=98.0, pain_score=1)
        res = evaluate_triage(vitals)
        assert res.category == expected_category
        assert res.priority_score == expected_score

    @pytest.mark.parametrize("pain,expected_category,expected_score", [
        (0, TriageCategory.CATEGORY_4, 20),   # No pain
        (4, TriageCategory.CATEGORY_4, 20),   # Mild pain upper limit
        (5, TriageCategory.CATEGORY_3, 50),   # Moderate pain lower limit
        (7, TriageCategory.CATEGORY_3, 50),   # Moderate pain upper limit
        (8, TriageCategory.CATEGORY_2, 75),   # Severe pain lower limit
        (10, TriageCategory.CATEGORY_2, 75),  # Max VAS pain score
    ])
    def test_bva_pain_score_thresholds(self, pain, expected_category, expected_score):
        """Tests exact integer boundaries for Visual Analog Pain Scale (0-10)."""
        vitals = TriageVitals(patient_id=1, heart_rate=75, systolic_bp=120, sp02=98.0, pain_score=pain)
        res = evaluate_triage(vitals)
        assert res.category == expected_category
        assert res.priority_score == expected_score


# =============================================================================
# 3. Input Validation & Error Handling
# =============================================================================

class TestTriageValidationExceptions:
    """Verifies that out-of-range physiological values raise MedicalValidationError."""

    def test_negative_heart_rate_rejected(self):
        v = TriageVitals(patient_id=1, heart_rate=-10, systolic_bp=120, sp02=98.0, pain_score=1)
        with pytest.raises(MedicalValidationError, match="Heart rate"):
            evaluate_triage(v)

    def test_excessive_heart_rate_rejected(self):
        v = TriageVitals(patient_id=1, heart_rate=350, systolic_bp=120, sp02=98.0, pain_score=1)
        with pytest.raises(MedicalValidationError, match="Heart rate"):
            evaluate_triage(v)

    def test_invalid_spo2_above_100_rejected(self):
        v = TriageVitals(patient_id=1, heart_rate=80, systolic_bp=120, sp02=105.0, pain_score=1)
        with pytest.raises(MedicalValidationError, match="SpO2"):
            evaluate_triage(v)

    def test_invalid_negative_spo2_rejected(self):
        v = TriageVitals(patient_id=1, heart_rate=80, systolic_bp=120, sp02=-5.0, pain_score=1)
        with pytest.raises(MedicalValidationError, match="SpO2"):
            evaluate_triage(v)

    def test_invalid_negative_systolic_bp_rejected(self):
        v = TriageVitals(patient_id=1, heart_rate=80, systolic_bp=-20, sp02=98.0, pain_score=1)
        with pytest.raises(MedicalValidationError, match="Systolic BP"):
            evaluate_triage(v)

    def test_invalid_pain_score_above_10_rejected(self):
        v = TriageVitals(patient_id=1, heart_rate=80, systolic_bp=120, sp02=98.0, pain_score=11)
        with pytest.raises(MedicalValidationError, match="Pain score"):
            evaluate_triage(v)


# =============================================================================
# 4. Database Triage Persistence & HMAC Checksum Verification
# =============================================================================

class TestTriagePersistence:
    """Verifies recording triage results into SQLite and validating tamper signatures."""

    def test_record_patient_triage_persists_and_signs(self, in_memory_db, sample_patient_1):
        v = TriageVitals(
            patient_id=sample_patient_1.id,
            heart_rate=145,
            systolic_bp=75,
            sp02=85.0,
            pain_score=9
        )
        result, record = record_patient_triage(in_memory_db, v)

        assert record.id is not None
        assert record.urgency_category == TriageCategory.CATEGORY_1.value
        assert record.priority_score == 100
        assert record.checksum is not None

        # Verify HMAC checksum integrity
        payload = (
            f"patient_id={v.patient_id}|hr={v.heart_rate}|"
            f"sbp={v.systolic_bp}|sp02={v.sp02}|pain={v.pain_score}|"
            f"cat={result.category.value}|score={result.priority_score}"
        )
        assert verify_record_checksum(payload, record.checksum) is True
