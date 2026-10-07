"""
Unit Test Suite for Appointment Scheduling & Conflict Resolution (Part B: Black-Box Testing).
Demonstrates equivalence partitioning, boundary condition checks, double-booking rejection,
priority-queue emergency overrides, and exception handling for invalid inputs.
"""

import pytest
from datetime import datetime, timedelta
from src.models import (
    AppointmentStatus,
    TriageCategory,
    AppointmentConflictError,
    AppointmentValidationError,
    ResourceNotFoundError,
)


# =============================================================================
# 1. Equivalence Partitioning & Time Slot Validation
# =============================================================================

class TestAppointmentTimeEquivalencePartitioning:
    """Tests valid vs. invalid equivalence classes for appointment times."""

    def test_valid_operating_hours_slot_confirmed(self, appointment_mgr, sample_doctor, sample_patient_1):
        """Valid class: Slot within 08:00 - 18:00 and aligned to 30-min boundary."""
        res = appointment_mgr.schedule_appointment(
            patient_id=sample_patient_1.id,
            doctor_id=sample_doctor.id,
            appointment_time="2026-10-15 09:30"
        )
        assert res.success is True
        assert res.appointment.status == AppointmentStatus.SCHEDULED
        assert res.appointment.appointment_time == "2026-10-15 09:30"

    def test_invalid_before_opening_hours_rejected(self, appointment_mgr, sample_doctor, sample_patient_1):
        """Invalid class: Slot before 08:00 AM (e.g. 06:30 AM)."""
        with pytest.raises(AppointmentValidationError, match="outside operating hours"):
            appointment_mgr.schedule_appointment(
                patient_id=sample_patient_1.id,
                doctor_id=sample_doctor.id,
                appointment_time="2026-10-15 06:30"
            )

    def test_invalid_after_closing_hours_rejected(self, appointment_mgr, sample_doctor, sample_patient_1):
        """Invalid class: Slot after 18:00 (e.g. 19:00 / 07:00 PM)."""
        with pytest.raises(AppointmentValidationError, match="outside operating hours"):
            appointment_mgr.schedule_appointment(
                patient_id=sample_patient_1.id,
                doctor_id=sample_doctor.id,
                appointment_time="2026-10-15 19:00"
            )

    def test_invalid_unaligned_slot_minutes_rejected(self, appointment_mgr, sample_doctor, sample_patient_1):
        """Invalid class: Slot not on 30-minute interval (e.g. 10:15 AM)."""
        with pytest.raises(AppointmentValidationError, match="must align with 30-minute slot intervals"):
            appointment_mgr.schedule_appointment(
                patient_id=sample_patient_1.id,
                doctor_id=sample_doctor.id,
                appointment_time="2026-10-15 10:15"
            )

    def test_invalid_past_timestamp_rejected(self, appointment_mgr, sample_doctor, sample_patient_1):
        """Invalid class: Slot scheduled in the past relative to reference time (2026-10-15 08:00)."""
        with pytest.raises(AppointmentValidationError, match="Cannot schedule appointment in the past"):
            appointment_mgr.schedule_appointment(
                patient_id=sample_patient_1.id,
                doctor_id=sample_doctor.id,
                appointment_time="2026-10-14 10:00"
            )


# =============================================================================
# 2. Conflict Detection & Double-Booking Prevention
# =============================================================================

class TestAppointmentConflictDetection:
    """Tests double booking rejection and schedule collision handling."""

    def test_double_booking_same_doctor_same_slot_rejected(
        self,
        appointment_mgr,
        sample_doctor,
        sample_patient_1,
        sample_patient_2
    ):
        """Second routine patient attempting to book the same doctor at the same time is rejected."""
        slot = "2026-10-15 11:00"

        # Patient 1 books 11:00
        res1 = appointment_mgr.schedule_appointment(
            patient_id=sample_patient_1.id,
            doctor_id=sample_doctor.id,
            appointment_time=slot,
            priority_score=20
        )
        assert res1.success is True

        # Patient 2 tries to book 11:00 for same doctor
        with pytest.raises(AppointmentConflictError, match="Booking Conflict"):
            appointment_mgr.schedule_appointment(
                patient_id=sample_patient_2.id,
                doctor_id=sample_doctor.id,
                appointment_time=slot,
                priority_score=20
            )

    def test_same_patient_double_booking_rejected(
        self,
        appointment_mgr,
        sample_doctor,
        sample_patient_1
    ):
        """Same patient cannot book two appointments with same doctor at the exact same slot."""
        slot = "2026-10-15 14:00"
        appointment_mgr.schedule_appointment(
            patient_id=sample_patient_1.id,
            doctor_id=sample_doctor.id,
            appointment_time=slot
        )

        with pytest.raises(AppointmentConflictError, match="already booked"):
            appointment_mgr.schedule_appointment(
                patient_id=sample_patient_1.id,
                doctor_id=sample_doctor.id,
                appointment_time=slot
            )


# =============================================================================
# 3. Priority-Queue Override & Emergency Preemption
# =============================================================================

class TestAppointmentPriorityPreemption:
    """Tests emergency queue reallocation when a Category 1/2 patient arrives."""

    def test_emergency_patient_preempts_routine_patient(
        self,
        in_memory_db,
        appointment_mgr,
        sample_doctor,
        sample_patient_1,
        sample_patient_emergency
    ):
        """Critical Category 1 patient overrides Category 4 routine patient and reschedules routine patient."""
        slot = "2026-10-15 10:00"

        # 1. Record routine triage for Patient 1 (Score: 20)
        in_memory_db.create_triage_record(
            patient_id=sample_patient_1.id,
            heart_rate=72,
            systolic_bp=120,
            sp02=99.0,
            pain_score=1,
            urgency_category=TriageCategory.CATEGORY_4.value,
            priority_score=20
        )

        # 2. Routine patient books 10:00
        alloc_routine = appointment_mgr.schedule_appointment(
            patient_id=sample_patient_1.id,
            doctor_id=sample_doctor.id,
            appointment_time=slot,
            priority_score=20,
            urgency_category=TriageCategory.CATEGORY_4
        )
        assert alloc_routine.success is True

        # 3. Emergency patient arrives with Priority 100 (Cat 1) requesting 10:00
        alloc_emergency = appointment_mgr.schedule_appointment(
            patient_id=sample_patient_emergency.id,
            doctor_id=sample_doctor.id,
            appointment_time=slot,
            priority_score=100,
            urgency_category=TriageCategory.CATEGORY_1,
            notes="Critical resuscitation required"
        )

        assert alloc_emergency.success is True
        assert alloc_emergency.emergency_preemption is True
        assert alloc_emergency.appointment.appointment_time == slot
        assert alloc_emergency.appointment.patient_id == sample_patient_emergency.id

        # Displaced routine patient is automatically rescheduled to 10:30
        displaced_appt = in_memory_db.get_appointment_by_id(alloc_routine.appointment.id)
        assert displaced_appt.appointment_time == "2026-10-15 10:30"
        assert "Preempted by Emergency Patient" in displaced_appt.notes

    def test_equal_or_lower_priority_cannot_preempt(
        self,
        in_memory_db,
        appointment_mgr,
        sample_doctor,
        sample_patient_1,
        sample_patient_2
    ):
        """Emergency patient cannot preempt another emergency patient with equal or higher priority."""
        slot = "2026-10-15 10:00"

        # First emergency patient (Score: 100)
        in_memory_db.create_triage_record(
            patient_id=sample_patient_1.id,
            heart_rate=150,
            systolic_bp=70,
            sp02=85.0,
            pain_score=9,
            urgency_category=TriageCategory.CATEGORY_1.value,
            priority_score=100
        )
        appointment_mgr.schedule_appointment(
            patient_id=sample_patient_1.id,
            doctor_id=sample_doctor.id,
            appointment_time=slot,
            priority_score=100,
            urgency_category=TriageCategory.CATEGORY_1
        )

        # Second emergent patient (Score: 75) attempts to override
        with pytest.raises(AppointmentConflictError, match="Cannot preempt slot"):
            appointment_mgr.schedule_appointment(
                patient_id=sample_patient_2.id,
                doctor_id=sample_doctor.id,
                appointment_time=slot,
                priority_score=75,
                urgency_category=TriageCategory.CATEGORY_2
            )


# =============================================================================
# 4. Input Validation & Entity Integrity
# =============================================================================

class TestAppointmentInputValidation:
    """Verifies exception raising on non-existent IDs or invalid user roles."""

    def test_nonexistent_doctor_raises_error(self, appointment_mgr, sample_patient_1):
        with pytest.raises(ResourceNotFoundError, match="Doctor with ID 9999 does not exist"):
            appointment_mgr.schedule_appointment(
                patient_id=sample_patient_1.id,
                doctor_id=9999,
                appointment_time="2026-10-15 10:00"
            )

    def test_non_doctor_user_role_rejected(self, appointment_mgr, sample_nurse, sample_patient_1):
        """Attempting to book an appointment with a Nurse raises AppointmentValidationError."""
        with pytest.raises(AppointmentValidationError, match="not 'Doctor'"):
            appointment_mgr.schedule_appointment(
                patient_id=sample_patient_1.id,
                doctor_id=sample_nurse.id,
                appointment_time="2026-10-15 10:00"
            )

    def test_nonexistent_patient_raises_error(self, appointment_mgr, sample_doctor):
        with pytest.raises(ResourceNotFoundError, match="Patient with ID 8888 does not exist"):
            appointment_mgr.schedule_appointment(
                patient_id=8888,
                doctor_id=sample_doctor.id,
                appointment_time="2026-10-15 10:00"
            )


# =============================================================================
# 5. Lifecycle Management (Cancellation & Completion)
# =============================================================================

class TestAppointmentLifecycle:
    """Tests appointment status state transitions."""

    def test_cancel_appointment_workflow(self, appointment_mgr, sample_doctor, sample_patient_1):
        res = appointment_mgr.schedule_appointment(
            patient_id=sample_patient_1.id,
            doctor_id=sample_doctor.id,
            appointment_time="2026-10-15 15:00"
        )
        cancelled_appt = appointment_mgr.cancel_appointment(res.appointment.id, reason="Patient feeling better")
        assert cancelled_appt.status == AppointmentStatus.CANCELLED
        assert "Patient feeling better" in cancelled_appt.notes

    def test_recancelling_already_cancelled_appointment_raises_error(
        self,
        appointment_mgr,
        sample_doctor,
        sample_patient_1
    ):
        res = appointment_mgr.schedule_appointment(
            patient_id=sample_patient_1.id,
            doctor_id=sample_doctor.id,
            appointment_time="2026-10-15 15:30"
        )
        appointment_mgr.cancel_appointment(res.appointment.id)
        with pytest.raises(AppointmentValidationError, match="already cancelled"):
            appointment_mgr.cancel_appointment(res.appointment.id)

    def test_complete_appointment_workflow(self, appointment_mgr, sample_doctor, sample_patient_1):
        res = appointment_mgr.schedule_appointment(
            patient_id=sample_patient_1.id,
            doctor_id=sample_doctor.id,
            appointment_time="2026-10-15 16:00"
        )
        completed_appt = appointment_mgr.complete_appointment(res.appointment.id)
        assert completed_appt.status == AppointmentStatus.COMPLETED
