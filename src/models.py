"""
Data models, enumerations, and custom exception definitions for the
Secure Patient Appointment & Triage Management System.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


# =====================================================================
# Enumerations
# =====================================================================

class UserRole(str, Enum):
    """Allowed system access roles."""
    DOCTOR = "Doctor"
    TRIAGE_NURSE = "Triage_Nurse"
    ADMIN = "Admin"

    @classmethod
    def from_str(cls, value: str) -> UserRole:
        for member in cls:
            if member.value.lower() == value.strip().lower():
                return member
        raise ValueError(f"Invalid UserRole: '{value}'. Allowed: {[e.value for e in cls]}")


class TriageCategory(str, Enum):
    """Emergency Severity Index (ESI) inspired triage classification."""
    CATEGORY_1 = "Category 1"  # Resuscitation / Immediate
    CATEGORY_2 = "Category 2"  # Emergent
    CATEGORY_3 = "Category 3"  # Urgent
    CATEGORY_4 = "Category 4"  # Non-Urgent / Routine


class AppointmentStatus(str, Enum):
    """Lifecycle states for patient appointments."""
    SCHEDULED = "Scheduled"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    EMERGENCY_PREEMPTED = "Emergency_Preempted"

    @classmethod
    def from_str(cls, value: str) -> AppointmentStatus:
        for member in cls:
            if member.value.lower() == value.strip().lower():
                return member
        raise ValueError(f"Invalid AppointmentStatus: '{value}'. Allowed: {[e.value for e in cls]}")


# =====================================================================
# Domain Models & Dataclasses
# =====================================================================

@dataclass
class User:
    """System user with role-based access control."""
    id: Optional[int]
    username: str
    password_hash: str
    salt: str
    role: UserRole
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Patient:
    """Demographic and identification record of a patient."""
    id: Optional[int]
    national_id: str
    full_name: str
    age: int
    contact: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.national_id or not self.national_id.strip():
            raise MedicalValidationError("National ID cannot be empty.")
        if not self.full_name or not self.full_name.strip():
            raise MedicalValidationError("Full name cannot be empty.")
        if self.age < 0 or self.age > 130:
            raise MedicalValidationError(f"Invalid age: {self.age}. Must be between 0 and 130.")


@dataclass
class TriageVitals:
    """Clinical vital signs measured at intake triage."""
    patient_id: int
    heart_rate: int       # Heart rate in beats per minute (bpm)
    systolic_bp: int      # Systolic blood pressure in mmHg
    sp02: float           # Blood oxygen saturation percentage (0 - 100%)
    pain_score: int       # Pain scale (1 - 10 or 0 for none)

    def validate(self) -> None:
        """Validates that all vital signs fall within physiologically possible limits."""
        if not (20 <= self.heart_rate <= 300):
            raise MedicalValidationError(
                f"Heart rate {self.heart_rate} bpm is outside physiological range (20 - 300 bpm)."
            )
        if not (0.0 <= self.sp02 <= 100.0):
            raise MedicalValidationError(
                f"SpO2 saturation {self.sp02}% is invalid. Must be between 0.0% and 100.0%."
            )
        if not (30 <= self.systolic_bp <= 300):
            raise MedicalValidationError(
                f"Systolic BP {self.systolic_bp} mmHg is outside physiological range (30 - 300 mmHg)."
            )
        if not (0 <= self.pain_score <= 10):
            raise MedicalValidationError(
                f"Pain score {self.pain_score} is invalid. Must be between 0 and 10 on the visual analog scale."
            )


@dataclass
class TriageResult:
    """Evaluated clinical priority output from the triage algorithm."""
    category: TriageCategory
    category_label: str
    priority_score: int
    max_wait_minutes: int
    clinical_rationale: List[str]


@dataclass
class TriageRecord:
    """Persistent database record of a triage calculation."""
    id: Optional[int]
    patient_id: int
    heart_rate: int
    systolic_bp: int
    sp02: float
    pain_score: int
    urgency_category: str
    priority_score: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    checksum: Optional[str] = None


@dataclass
class Appointment:
    """Doctor consultation booking record."""
    id: Optional[int]
    patient_id: int
    doctor_id: int
    appointment_time: str
    status: AppointmentStatus = AppointmentStatus.SCHEDULED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: Optional[str] = None


# =====================================================================
# Custom Exceptions
# =====================================================================

class MedicalValidationError(ValueError):
    """Raised when physiological inputs violate clinical constraints."""
    pass


class AuthenticationError(Exception):
    """Raised on invalid user authentication attempts."""
    pass


class AuthorizationError(Exception):
    """Raised when a user attempts an unauthorized role-restricted action."""
    pass


class AppointmentConflictError(Exception):
    """Raised when an appointment schedule slot collides with an existing booking."""
    pass


class AppointmentValidationError(ValueError):
    """Raised when appointment parameters violate business scheduling rules."""
    pass


class ResourceNotFoundError(KeyError):
    """Raised when a queried entity (Patient, User, Appointment) does not exist."""
    pass
