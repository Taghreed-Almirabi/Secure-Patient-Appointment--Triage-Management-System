"""
Appointment Management and Conflict Resolution Engine.
Handles doctor scheduling, double-booking prevention, working hours validation,
and priority-queue emergency override / preemption logic.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from .models import (
    Appointment,
    AppointmentStatus,
    UserRole,
    TriageCategory,
    AppointmentConflictError,
    AppointmentValidationError,
    ResourceNotFoundError,
)
from .database import DatabaseManager

# Standard clinic operating configuration
CLINIC_START_HOUR = 8   # 08:00 AM
CLINIC_END_HOUR = 18    # 06:00 PM (18:00)
DEFAULT_SLOT_MINUTES = 30
DATETIME_FORMAT = "%Y-%m-%d %H:%M"


@dataclass
class AllocationResult:
    """Detailed outcome of an appointment booking or emergency reallocation request."""
    success: bool
    appointment: Appointment
    emergency_preemption: bool = False
    preempted_appointment: Optional[Appointment] = None
    rescheduled_to: Optional[str] = None
    message: str = ""


class AppointmentManager:
    """Manages consultation scheduling, conflict detection, and emergency overrides."""

    def __init__(
        self,
        db: DatabaseManager,
        slot_duration_minutes: int = DEFAULT_SLOT_MINUTES,
        reference_time: Optional[datetime] = None
    ) -> None:
        self.db = db
        self.slot_duration = slot_duration_minutes
        self.reference_time = reference_time

    def _get_current_time(self) -> datetime:
        """Returns the active reference time or actual system clock."""
        return self.reference_time if self.reference_time is not None else datetime.now()

    def parse_time(self, time_str: str) -> datetime:
        """Parses an ISO or standard datetime string."""
        for fmt in (DATETIME_FORMAT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(time_str.strip(), fmt)
            except ValueError:
                continue
        raise AppointmentValidationError(
            f"Invalid datetime format: '{time_str}'. Expected format: 'YYYY-MM-DD HH:MM'."
        )

    def format_time(self, dt: datetime) -> str:
        """Formats a datetime object to standard string representation."""
        return dt.strftime(DATETIME_FORMAT)

    def validate_operating_hours(self, dt: datetime) -> None:
        """
        Ensures appointment falls within clinic operating hours (08:00 - 18:00).
        """
        hour = dt.hour
        minute = dt.minute

        # Check working hours bounds
        if hour < CLINIC_START_HOUR or (hour == CLINIC_END_HOUR and minute > 0) or hour > CLINIC_END_HOUR:
            raise AppointmentValidationError(
                f"Requested time {dt.strftime('%H:%M')} is outside operating hours "
                f"({CLINIC_START_HOUR:02d}:00 to {CLINIC_END_HOUR:02d}:00)."
            )

        # Slot alignment (e.g. 00, 30)
        if minute % self.slot_duration != 0:
            raise AppointmentValidationError(
                f"Appointment minute ({minute:02d}) must align with {self.slot_duration}-minute slot intervals."
            )

    def validate_future_timestamp(self, dt: datetime) -> None:
        """Ensures the appointment is scheduled in the future."""
        current_now = self._get_current_time()
        if dt < current_now:
            raise AppointmentValidationError(
                f"Cannot schedule appointment in the past: {self.format_time(dt)} "
                f"(Current reference time: {self.format_time(current_now)})."
            )

    def find_next_available_slot(
        self,
        doctor_id: int,
        start_dt: datetime,
        max_days_ahead: int = 7
    ) -> str:
        """
        Finds the nearest vacant 30-minute slot for a doctor starting from start_dt.
        """
        current_slot = start_dt
        # Normalize to next slot if start_dt is within working hours
        if current_slot.hour < CLINIC_START_HOUR:
            current_slot = current_slot.replace(hour=CLINIC_START_HOUR, minute=0, second=0, microsecond=0)
        elif current_slot.hour >= CLINIC_END_HOUR:
            # Advance to next day at clinic start
            current_slot = (current_slot + timedelta(days=1)).replace(
                hour=CLINIC_START_HOUR, minute=0, second=0, microsecond=0
            )

        end_search_limit = start_dt + timedelta(days=max_days_ahead)

        while current_slot < end_search_limit:
            # Check operating hours
            if CLINIC_START_HOUR <= current_slot.hour < CLINIC_END_HOUR or (
                current_slot.hour == CLINIC_END_HOUR and current_slot.minute == 0
            ):
                slot_str = self.format_time(current_slot)
                existing = self.db.get_scheduled_appointment_at(doctor_id, slot_str)
                if not existing:
                    return slot_str
                # Advance by slot duration
                current_slot += timedelta(minutes=self.slot_duration)
            else:
                # Roll over to next morning
                current_slot = (current_slot + timedelta(days=1)).replace(
                    hour=CLINIC_START_HOUR, minute=0, second=0, microsecond=0
                )

        raise AppointmentConflictError(f"No available slots found for Doctor #{doctor_id} in the next {max_days_ahead} days.")

    def schedule_appointment(
        self,
        patient_id: int,
        doctor_id: int,
        appointment_time: str,
        priority_score: int = 20,
        urgency_category: Optional[TriageCategory | str] = None,
        notes: Optional[str] = None
    ) -> AllocationResult:
        """
        Schedules an appointment with conflict detection and priority-based emergency preemption.

        Priority Rules:
        - Category 1 (Score 100) / Category 2 (Score 75) are Emergency/Emergent.
        - If an emergency patient requests an occupied slot held by a lower-priority patient,
          the system preempts the existing appointment, books the emergency patient into the requested slot,
          and automatically reschedules the routine patient to the next available slot.
        - Non-emergency patients conflicting with an occupied slot raise `AppointmentConflictError`.

        Args:
            patient_id: ID of the patient.
            doctor_id: ID of the doctor (must have UserRole.DOCTOR).
            appointment_time: String representation of requested time.
            priority_score: Numeric triage score (100, 75, 50, 20).
            urgency_category: Category label or enum.
            notes: Optional consultation notes.

        Returns:
            AllocationResult: Detailed outcome with preemption metadata.
        """
        # 1. Validate Entities
        patient = self.db.get_patient_by_id(patient_id)
        if not patient:
            raise ResourceNotFoundError(f"Patient with ID {patient_id} does not exist.")

        doctor = self.db.get_user_by_id(doctor_id)
        if not doctor:
            raise ResourceNotFoundError(f"Doctor with ID {doctor_id} does not exist.")
        if doctor.role != UserRole.DOCTOR:
            raise AppointmentValidationError(
                f"User '{doctor.username}' has role '{doctor.role.value}', not 'Doctor'. "
                f"Appointments can only be scheduled with registered doctors."
            )

        # 2. Parse & Validate Datetime
        appt_dt = self.parse_time(appointment_time)
        self.validate_operating_hours(appt_dt)
        self.validate_future_timestamp(appt_dt)
        formatted_slot = self.format_time(appt_dt)

        # 3. Conflict Detection
        existing_appt = self.db.get_scheduled_appointment_at(doctor_id, formatted_slot)

        # Determine if this is an Emergency / Priority request
        is_emergency = priority_score >= 75 or (
            urgency_category in (TriageCategory.CATEGORY_1, TriageCategory.CATEGORY_2, "Category 1", "Category 2")
        )

        if existing_appt is not None:
            # Slot is already occupied!
            if existing_appt.patient_id == patient_id:
                raise AppointmentConflictError(
                    f"Patient #{patient_id} ({patient.full_name}) is already booked for Doctor #{doctor_id} at {formatted_slot}."
                )

            # Check if emergency override is warranted
            if is_emergency:
                # Query existing patient's triage record to evaluate priority competition
                existing_triage = self.db.get_latest_triage_by_patient(existing_appt.patient_id)
                existing_priority = existing_triage.priority_score if existing_triage else 20

                if priority_score > existing_priority:
                    # Execute Emergency Preemption & Dynamic Slot Reallocation
                    preempted_patient = self.db.get_patient_by_id(existing_appt.patient_id)
                    preempted_name = preempted_patient.full_name if preempted_patient else f"ID #{existing_appt.patient_id}"

                    # Find next available opening for the displaced routine patient
                    next_slot = self.find_next_available_slot(
                        doctor_id,
                        start_dt=appt_dt + timedelta(minutes=self.slot_duration)
                    )

                    # Update the existing appointment: mark preempted and reschedule
                    realloc_note = (
                        f"Preempted by Emergency Patient #{patient_id} (Priority {priority_score}). "
                        f"Automatically rescheduled from {formatted_slot} to {next_slot}."
                    )
                    self.db.reschedule_appointment(existing_appt.id, next_slot, notes=realloc_note)
                    existing_appt.appointment_time = next_slot
                    existing_appt.notes = realloc_note

                    # Now book the emergency patient into the newly cleared prime slot
                    emergency_note = (
                        f"Emergency Priority Allocation (Score: {priority_score}). "
                        f"{notes or ''}".strip()
                    )
                    new_appt = self.db.create_appointment(
                        patient_id=patient_id,
                        doctor_id=doctor_id,
                        appointment_time=formatted_slot,
                        status=AppointmentStatus.SCHEDULED,
                        notes=emergency_note
                    )

                    return AllocationResult(
                        success=True,
                        appointment=new_appt,
                        emergency_preemption=True,
                        preempted_appointment=existing_appt,
                        rescheduled_to=next_slot,
                        message=(
                            f"EMERGENCY OVERRIDE: Slot {formatted_slot} allocated to Emergency Patient "
                            f"#{patient_id} ({patient.full_name}). Displaced Patient #{existing_appt.patient_id} "
                            f"({preempted_name}) automatically rescheduled to {next_slot}."
                        )
                    )
                else:
                    # Existing patient has equal or higher priority
                    raise AppointmentConflictError(
                        f"Cannot preempt slot {formatted_slot}: Existing patient #{existing_appt.patient_id} "
                        f"holds equal or higher triage priority (Score {existing_priority} vs {priority_score})."
                    )
            else:
                # Routine patient collision -> reject double booking
                raise AppointmentConflictError(
                    f"Booking Conflict: Doctor #{doctor_id} ({doctor.username}) already has an active "
                    f"appointment at {formatted_slot} (Appointment #{existing_appt.id})."
                )

        # 4. Standard Vacant Slot Allocation
        new_appt = self.db.create_appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_time=formatted_slot,
            status=AppointmentStatus.SCHEDULED,
            notes=notes
        )

        return AllocationResult(
            success=True,
            appointment=new_appt,
            emergency_preemption=False,
            message=f"Appointment successfully confirmed for {formatted_slot} with Doctor #{doctor_id}."
        )

    def cancel_appointment(self, appointment_id: int, reason: str = "Patient request") -> Appointment:
        """Cancels an existing appointment."""
        appt = self.db.get_appointment_by_id(appointment_id)
        if not appt:
            raise ResourceNotFoundError(f"Appointment #{appointment_id} does not exist.")

        if appt.status == AppointmentStatus.CANCELLED:
            raise AppointmentValidationError(f"Appointment #{appointment_id} is already cancelled.")

        self.db.update_appointment_status(
            appointment_id,
            AppointmentStatus.CANCELLED,
            notes=f"Cancelled: {reason}"
        )
        appt.status = AppointmentStatus.CANCELLED
        appt.notes = f"Cancelled: {reason}"
        return appt

    def complete_appointment(self, appointment_id: int) -> Appointment:
        """Marks a consultation as completed."""
        appt = self.db.get_appointment_by_id(appointment_id)
        if not appt:
            raise ResourceNotFoundError(f"Appointment #{appointment_id} does not exist.")

        self.db.update_appointment_status(appointment_id, AppointmentStatus.COMPLETED)
        appt.status = AppointmentStatus.COMPLETED
        return appt

    def get_doctor_schedule(self, doctor_id: int, date_str: Optional[str] = None) -> List[Appointment]:
        """Retrieves schedule of appointments for a doctor."""
        doctor = self.db.get_user_by_id(doctor_id)
        if not doctor:
            raise ResourceNotFoundError(f"Doctor with ID {doctor_id} does not exist.")
        return self.db.get_appointments_by_doctor(doctor_id, date_str)
