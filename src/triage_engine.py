"""
Deterministic Medical Triage Engine (Emergency Severity Index - ESI inspired).
Evaluates patient vital signs (SpO2, Heart Rate, Systolic BP, Pain Scale)
and produces a clinical priority classification and wait time limit.
"""

from __future__ import annotations
from typing import Tuple, List

from .models import (
    TriageVitals,
    TriageResult,
    TriageRecord,
    TriageCategory,
    MedicalValidationError,
)
from .database import DatabaseManager
from .auth_security import generate_record_checksum


def evaluate_triage(vitals: TriageVitals) -> TriageResult:
    """
    Evaluates patient vital parameters deterministically based on clinical ESI triage rules.

    Rules Hierarchy:
    ----------------
    1. Category 1 (Resuscitation / Immediate):
       - SpO2 < 90%  OR
       - Heart Rate > 140 bpm  OR
       - Systolic Blood Pressure < 80 mmHg
       => Priority Score: 100 | Max Wait Time: 0 mins (Immediate)

    2. Category 2 (Emergent):
       - SpO2 between 90% and 94% (inclusive)  OR
       - Heart Rate between 110 and 140 bpm (inclusive)  OR
       - Pain Score >= 8 (Severe)
       => Priority Score: 75 | Max Wait Time: 15 mins

    3. Category 3 (Urgent):
       - Heart Rate between 100 and 109 bpm (inclusive)  OR
       - Pain Score between 5 and 7 (inclusive, Moderate)
       => Priority Score: 50 | Max Wait Time: 60 mins

    4. Category 4 (Non-Urgent / Routine):
       - Normal vital parameters (SpO2 >= 95%, HR < 100, SBP >= 80, Pain <= 4)
       => Priority Score: 20 | Max Wait Time: 120 mins

    Args:
        vitals: TriageVitals object containing measured parameters.

    Returns:
        TriageResult: Classification category, score, wait time, and clinical rationale.

    Raises:
        MedicalValidationError: If any vital sign fails physiological bounds checks.
    """
    # 1. Enforce strict input domain validation
    vitals.validate()

    rationale: List[str] = []

    # =========================================================================
    # Branch 1: Category 1 (Resuscitation / Immediate)
    # =========================================================================
    is_cat_1 = False
    if vitals.sp02 < 90.0:
        is_cat_1 = True
        rationale.append(f"Critical Hypoxemia: SpO2 ({vitals.sp02}%) is below 90%.")
    if vitals.heart_rate > 140:
        is_cat_1 = True
        rationale.append(f"Severe Tachycardia: Heart Rate ({vitals.heart_rate} bpm) exceeds 140 bpm.")
    if vitals.systolic_bp < 80:
        is_cat_1 = True
        rationale.append(f"Hemodynamic Instability / Hypotension: Systolic BP ({vitals.systolic_bp} mmHg) is below 80 mmHg.")

    if is_cat_1:
        return TriageResult(
            category=TriageCategory.CATEGORY_1,
            category_label="Resuscitation / Immediate",
            priority_score=100,
            max_wait_minutes=0,
            clinical_rationale=rationale
        )

    # =========================================================================
    # Branch 2: Category 2 (Emergent)
    # =========================================================================
    is_cat_2 = False
    if 90.0 <= vitals.sp02 <= 94.0:
        is_cat_2 = True
        rationale.append(f"Moderate Hypoxia: SpO2 ({vitals.sp02}%) is between 90% and 94%.")
    if 110 <= vitals.heart_rate <= 140:
        is_cat_2 = True
        rationale.append(f"Moderate Tachycardia: Heart Rate ({vitals.heart_rate} bpm) is between 110 and 140 bpm.")
    if vitals.pain_score >= 8:
        is_cat_2 = True
        rationale.append(f"Severe Pain Crisis: Pain Scale ({vitals.pain_score}/10) is >= 8.")

    if is_cat_2:
        return TriageResult(
            category=TriageCategory.CATEGORY_2,
            category_label="Emergent",
            priority_score=75,
            max_wait_minutes=15,
            clinical_rationale=rationale
        )

    # =========================================================================
    # Branch 3: Category 3 (Urgent)
    # =========================================================================
    is_cat_3 = False
    if 100 <= vitals.heart_rate < 110:
        is_cat_3 = True
        rationale.append(f"Mild Tachycardia: Heart Rate ({vitals.heart_rate} bpm) is between 100 and 109 bpm.")
    if 5 <= vitals.pain_score <= 7:
        is_cat_3 = True
        rationale.append(f"Moderate Pain: Pain Scale ({vitals.pain_score}/10) is between 5 and 7.")

    if is_cat_3:
        return TriageResult(
            category=TriageCategory.CATEGORY_3,
            category_label="Urgent",
            priority_score=50,
            max_wait_minutes=60,
            clinical_rationale=rationale
        )

    # =========================================================================
    # Branch 4: Category 4 (Non-Urgent / Routine)
    # =========================================================================
    rationale.append(
        f"All vital parameters within normal baseline limits "
        f"(HR: {vitals.heart_rate} bpm, SBP: {vitals.systolic_bp} mmHg, "
        f"SpO2: {vitals.sp02}%, Pain: {vitals.pain_score}/10)."
    )
    return TriageResult(
        category=TriageCategory.CATEGORY_4,
        category_label="Non-Urgent / Routine",
        priority_score=20,
        max_wait_minutes=120,
        clinical_rationale=rationale
    )


def record_patient_triage(
    db: DatabaseManager,
    vitals: TriageVitals
) -> Tuple[TriageResult, TriageRecord]:
    """
    Evaluates patient vitals and persists the triage calculation to the database
    with an HMAC integrity checksum.

    Args:
        db: The active DatabaseManager instance.
        vitals: Measured vital signs.

    Returns:
        Tuple of (TriageResult, TriageRecord).
    """
    result = evaluate_triage(vitals)

    # Build tamper-proof payload string
    payload = (
        f"patient_id={vitals.patient_id}|hr={vitals.heart_rate}|"
        f"sbp={vitals.systolic_bp}|sp02={vitals.sp02}|pain={vitals.pain_score}|"
        f"cat={result.category.value}|score={result.priority_score}"
    )
    checksum = generate_record_checksum(payload)

    record = db.create_triage_record(
        patient_id=vitals.patient_id,
        heart_rate=vitals.heart_rate,
        systolic_bp=vitals.systolic_bp,
        sp02=vitals.sp02,
        pain_score=vitals.pain_score,
        urgency_category=result.category.value,
        priority_score=result.priority_score,
        checksum=checksum
    )

    return result, record
