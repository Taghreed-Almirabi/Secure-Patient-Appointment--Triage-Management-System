"""
Shared pytest fixtures and database setup for unit testing.
Provides clean, isolated in-memory SQLite database instances for each test.
"""

import pytest
from datetime import datetime
from src.database import DatabaseManager
from src.models import UserRole
from src.auth_security import register_user
from src.appointment_manager import AppointmentManager


@pytest.fixture
def in_memory_db():
    """Provides a fresh, isolated in-memory SQLite database for each test."""
    db = DatabaseManager(":memory:")
    yield db
    db.close()


@pytest.fixture
def sample_doctor(in_memory_db):
    """Registers a sample Doctor in the database."""
    return register_user(
        in_memory_db,
        username="dr_alice",
        password="SecureDocPassword123!",
        role=UserRole.DOCTOR
    )


@pytest.fixture
def sample_nurse(in_memory_db):
    """Registers a sample Triage Nurse in the database."""
    return register_user(
        in_memory_db,
        username="nurse_bob",
        password="SecureNursePassword123!",
        role=UserRole.TRIAGE_NURSE
    )


@pytest.fixture
def sample_admin(in_memory_db):
    """Registers a sample Admin in the database."""
    return register_user(
        in_memory_db,
        username="admin_carol",
        password="SecureAdminPassword123!",
        role=UserRole.ADMIN
    )


@pytest.fixture
def sample_patient_1(in_memory_db):
    """Registers a primary test patient."""
    return in_memory_db.create_patient(
        national_id="PAT-TEST-001",
        full_name="Alice Smith",
        age=32,
        contact="+1-555-0191"
    )


@pytest.fixture
def sample_patient_2(in_memory_db):
    """Registers a secondary test patient."""
    return in_memory_db.create_patient(
        national_id="PAT-TEST-002",
        full_name="Bob Jones",
        age=58,
        contact="+1-555-0192"
    )


@pytest.fixture
def sample_patient_emergency(in_memory_db):
    """Registers an emergency test patient."""
    return in_memory_db.create_patient(
        national_id="PAT-TEST-003",
        full_name="Charlie Danger",
        age=67,
        contact="+1-555-0193"
    )


@pytest.fixture
def appointment_mgr(in_memory_db):
    """Provides an AppointmentManager pinned to a fixed reference time for deterministic testing."""
    fixed_now = datetime(2026, 10, 15, 8, 0, 0)
    return AppointmentManager(in_memory_db, slot_duration_minutes=30, reference_time=fixed_now)
