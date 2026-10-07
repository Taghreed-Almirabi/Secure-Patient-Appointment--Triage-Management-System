"""
Database access and persistence layer for the
Secure Patient Appointment & Triage Management System.
Uses SQLite3 with foreign key enforcement and parameterized queries.
"""

from __future__ import annotations
import sqlite3
from typing import List, Optional, Any, Tuple
from contextlib import contextmanager
from datetime import datetime

from .models import (
    User,
    UserRole,
    Patient,
    TriageRecord,
    Appointment,
    AppointmentStatus,
    ResourceNotFoundError,
)


class DatabaseManager:
    """Encapsulates SQLite connection management, schema migrations, and CRUD operations."""

    def __init__(self, db_path: str = "hospital_system.db") -> None:
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            # For in-memory DBs, keep a persistent connection open
            self._connection = self._create_connection()
        self.initialize_tables()

    def _create_connection(self) -> sqlite3.Connection:
        """Establishes and configures an SQLite database connection."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable foreign key constraint checks in SQLite
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def get_connection(self):
        """Context manager providing a managed database connection and auto-commit."""
        if self._connection is not None:
            # Reusing persistent connection (e.g., :memory:)
            try:
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        else:
            conn = self._create_connection()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def initialize_tables(self) -> None:
        """Initializes the relational database schema and required indexes."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Users Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            # 2. Patients Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    national_id TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    age INTEGER NOT NULL,
                    contact TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            # 3. Triage Records Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS triage_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                    heart_rate INTEGER NOT NULL,
                    systolic_bp INTEGER NOT NULL,
                    sp02 REAL NOT NULL,
                    pain_score INTEGER NOT NULL,
                    urgency_category TEXT NOT NULL,
                    priority_score INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    checksum TEXT
                );
            """)

            # 4. Appointments Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                    doctor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    appointment_time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    notes TEXT
                );
            """)

            # Performance & Lookup Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_patients_national_id ON patients(national_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_appointments_doc_time ON appointments(doctor_id, appointment_time);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_triage_patient ON triage_records(patient_id);")

    # =========================================================================
    # User CRUD Operations
    # =========================================================================

    def create_user(self, username: str, password_hash: str, salt: str, role: UserRole) -> User:
        """Inserts a new system user into the database."""
        created_at = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, salt, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, password_hash, salt, role.value, created_at)
            )
            user_id = cursor.lastrowid
            return User(
                id=user_id,
                username=username,
                password_hash=password_hash,
                salt=salt,
                role=role,
                created_at=created_at
            )

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Retrieves a user by unique username."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if not row:
                return None
            return User(
                id=row["id"],
                username=row["username"],
                password_hash=row["password_hash"],
                salt=row["salt"],
                role=UserRole(row["role"]),
                created_at=row["created_at"]
            )

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Retrieves a user by numeric primary key."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return User(
                id=row["id"],
                username=row["username"],
                password_hash=row["password_hash"],
                salt=row["salt"],
                role=UserRole(row["role"]),
                created_at=row["created_at"]
            )

    def list_users(self, role: Optional[UserRole] = None) -> List[User]:
        """Lists all registered users, optionally filtered by role."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if role:
                cursor.execute("SELECT * FROM users WHERE role = ? ORDER BY id ASC", (role.value,))
            else:
                cursor.execute("SELECT * FROM users ORDER BY id ASC")
            rows = cursor.fetchall()
            return [
                User(
                    id=r["id"],
                    username=r["username"],
                    password_hash=r["password_hash"],
                    salt=r["salt"],
                    role=UserRole(r["role"]),
                    created_at=r["created_at"]
                )
                for r in rows
            ]

    # =========================================================================
    # Patient CRUD Operations
    # =========================================================================

    def create_patient(self, national_id: str, full_name: str, age: int, contact: str) -> Patient:
        """Registers a new patient."""
        created_at = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO patients (national_id, full_name, age, contact, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (national_id.strip(), full_name.strip(), age, contact.strip(), created_at)
            )
            patient_id = cursor.lastrowid
            return Patient(
                id=patient_id,
                national_id=national_id.strip(),
                full_name=full_name.strip(),
                age=age,
                contact=contact.strip(),
                created_at=created_at
            )

    def get_patient_by_id(self, patient_id: int) -> Optional[Patient]:
        """Fetches a patient by database ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return Patient(
                id=row["id"],
                national_id=row["national_id"],
                full_name=row["full_name"],
                age=row["age"],
                contact=row["contact"],
                created_at=row["created_at"]
            )

    def get_patient_by_national_id(self, national_id: str) -> Optional[Patient]:
        """Fetches a patient by unique National ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM patients WHERE national_id = ?", (national_id.strip(),))
            row = cursor.fetchone()
            if not row:
                return None
            return Patient(
                id=row["id"],
                national_id=row["national_id"],
                full_name=row["full_name"],
                age=row["age"],
                contact=row["contact"],
                created_at=row["created_at"]
            )

    def list_patients(self) -> List[Patient]:
        """Lists all registered patients."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM patients ORDER BY id ASC")
            rows = cursor.fetchall()
            return [
                Patient(
                    id=r["id"],
                    national_id=r["national_id"],
                    full_name=r["full_name"],
                    age=r["age"],
                    contact=r["contact"],
                    created_at=r["created_at"]
                )
                for r in rows
            ]

    # =========================================================================
    # Triage Records CRUD Operations
    # =========================================================================

    def create_triage_record(
        self,
        patient_id: int,
        heart_rate: int,
        systolic_bp: int,
        sp02: float,
        pain_score: int,
        urgency_category: str,
        priority_score: int,
        checksum: Optional[str] = None
    ) -> TriageRecord:
        """Stores a calculated triage record for a patient."""
        # Ensure patient exists
        if not self.get_patient_by_id(patient_id):
            raise ResourceNotFoundError(f"Patient with ID {patient_id} does not exist.")

        timestamp = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO triage_records (
                    patient_id, heart_rate, systolic_bp, sp02, pain_score,
                    urgency_category, priority_score, timestamp, checksum
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_id, heart_rate, systolic_bp, sp02, pain_score,
                    urgency_category, priority_score, timestamp, checksum
                )
            )
            record_id = cursor.lastrowid
            return TriageRecord(
                id=record_id,
                patient_id=patient_id,
                heart_rate=heart_rate,
                systolic_bp=systolic_bp,
                sp02=sp02,
                pain_score=pain_score,
                urgency_category=urgency_category,
                priority_score=priority_score,
                timestamp=timestamp,
                checksum=checksum
            )

    def get_triage_records_by_patient(self, patient_id: int) -> List[TriageRecord]:
        """Returns all triage history records for a given patient."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM triage_records WHERE patient_id = ? ORDER BY timestamp DESC",
                (patient_id,)
            )
            rows = cursor.fetchall()
            return [
                TriageRecord(
                    id=r["id"],
                    patient_id=r["patient_id"],
                    heart_rate=r["heart_rate"],
                    systolic_bp=r["systolic_bp"],
                    sp02=r["sp02"],
                    pain_score=r["pain_score"],
                    urgency_category=r["urgency_category"],
                    priority_score=r["priority_score"],
                    timestamp=r["timestamp"],
                    checksum=r["checksum"]
                )
                for r in rows
            ]

    def get_latest_triage_by_patient(self, patient_id: int) -> Optional[TriageRecord]:
        """Returns the most recent triage record for a given patient."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM triage_records WHERE patient_id = ? ORDER BY id DESC LIMIT 1",
                (patient_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return TriageRecord(
                id=row["id"],
                patient_id=row["patient_id"],
                heart_rate=row["heart_rate"],
                systolic_bp=row["systolic_bp"],
                sp02=row["sp02"],
                pain_score=row["pain_score"],
                urgency_category=row["urgency_category"],
                priority_score=row["priority_score"],
                timestamp=row["timestamp"],
                checksum=row["checksum"]
            )

    # =========================================================================
    # Appointment CRUD Operations
    # =========================================================================

    def create_appointment(
        self,
        patient_id: int,
        doctor_id: int,
        appointment_time: str,
        status: AppointmentStatus = AppointmentStatus.SCHEDULED,
        notes: Optional[str] = None
    ) -> Appointment:
        """Creates an appointment booking in the database."""
        # Validate patient and doctor exist
        if not self.get_patient_by_id(patient_id):
            raise ResourceNotFoundError(f"Patient ID {patient_id} does not exist.")
        doctor = self.get_user_by_id(doctor_id)
        if not doctor:
            raise ResourceNotFoundError(f"Doctor ID {doctor_id} does not exist.")

        created_at = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO appointments (patient_id, doctor_id, appointment_time, status, created_at, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (patient_id, doctor_id, appointment_time, status.value, created_at, notes)
            )
            appt_id = cursor.lastrowid
            return Appointment(
                id=appt_id,
                patient_id=patient_id,
                doctor_id=doctor_id,
                appointment_time=appointment_time,
                status=status,
                created_at=created_at,
                notes=notes
            )

    def get_appointment_by_id(self, appointment_id: int) -> Optional[Appointment]:
        """Retrieves a single appointment by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return Appointment(
                id=row["id"],
                patient_id=row["patient_id"],
                doctor_id=row["doctor_id"],
                appointment_time=row["appointment_time"],
                status=AppointmentStatus(row["status"]),
                created_at=row["created_at"],
                notes=row["notes"]
            )

    def get_scheduled_appointment_at(self, doctor_id: int, appointment_time: str) -> Optional[Appointment]:
        """Checks if a doctor already has an active 'Scheduled' appointment at a specific time."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM appointments
                WHERE doctor_id = ? AND appointment_time = ? AND status = ?
                """,
                (doctor_id, appointment_time, AppointmentStatus.SCHEDULED.value)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return Appointment(
                id=row["id"],
                patient_id=row["patient_id"],
                doctor_id=row["doctor_id"],
                appointment_time=row["appointment_time"],
                status=AppointmentStatus(row["status"]),
                created_at=row["created_at"],
                notes=row["notes"]
            )

    def get_appointments_by_doctor(
        self,
        doctor_id: int,
        date_prefix: Optional[str] = None
    ) -> List[Appointment]:
        """Retrieves all appointments for a doctor, optionally filtered by date prefix (YYYY-MM-DD)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if date_prefix:
                cursor.execute(
                    """
                    SELECT * FROM appointments
                    WHERE doctor_id = ? AND appointment_time LIKE ?
                    ORDER BY appointment_time ASC
                    """,
                    (doctor_id, f"{date_prefix}%")
                )
            else:
                cursor.execute(
                    "SELECT * FROM appointments WHERE doctor_id = ? ORDER BY appointment_time ASC",
                    (doctor_id,)
                )
            rows = cursor.fetchall()
            return [
                Appointment(
                    id=r["id"],
                    patient_id=r["patient_id"],
                    doctor_id=r["doctor_id"],
                    appointment_time=r["appointment_time"],
                    status=AppointmentStatus(r["status"]),
                    created_at=r["created_at"],
                    notes=r["notes"]
                )
                for r in rows
            ]

    def get_appointments_by_patient(self, patient_id: int) -> List[Appointment]:
        """Retrieves all appointments for a patient."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM appointments WHERE patient_id = ? ORDER BY appointment_time ASC",
                (patient_id,)
            )
            rows = cursor.fetchall()
            return [
                Appointment(
                    id=r["id"],
                    patient_id=r["patient_id"],
                    doctor_id=r["doctor_id"],
                    appointment_time=r["appointment_time"],
                    status=AppointmentStatus(r["status"]),
                    created_at=r["created_at"],
                    notes=r["notes"]
                )
                for r in rows
            ]

    def update_appointment_status(
        self,
        appointment_id: int,
        status: AppointmentStatus,
        notes: Optional[str] = None
    ) -> bool:
        """Updates the status and optional notes of an appointment."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if notes is not None:
                cursor.execute(
                    "UPDATE appointments SET status = ?, notes = ? WHERE id = ?",
                    (status.value, notes, appointment_id)
                )
            else:
                cursor.execute(
                    "UPDATE appointments SET status = ? WHERE id = ?",
                    (status.value, appointment_id)
                )
            return cursor.rowcount > 0

    def reschedule_appointment(
        self,
        appointment_id: int,
        new_appointment_time: str,
        notes: Optional[str] = None
    ) -> bool:
        """Reschedules an appointment to a new time."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if notes is not None:
                cursor.execute(
                    """
                    UPDATE appointments
                    SET appointment_time = ?, status = ?, notes = ?
                    WHERE id = ?
                    """,
                    (new_appointment_time, AppointmentStatus.SCHEDULED.value, notes, appointment_id)
                )
            else:
                cursor.execute(
                    """
                    UPDATE appointments
                    SET appointment_time = ?, status = ?
                    WHERE id = ?
                    """,
                    (new_appointment_time, AppointmentStatus.SCHEDULED.value, appointment_id)
                )
            return cursor.rowcount > 0

    def list_appointments(self) -> List[Appointment]:
        """Lists all appointments across all doctors."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appointments ORDER BY appointment_time ASC")
            rows = cursor.fetchall()
            return [
                Appointment(
                    id=r["id"],
                    patient_id=r["patient_id"],
                    doctor_id=r["doctor_id"],
                    appointment_time=r["appointment_time"],
                    status=AppointmentStatus(r["status"]),
                    created_at=r["created_at"],
                    notes=r["notes"]
                )
                for r in rows
            ]

    def close(self) -> None:
        """Closes the underlying connection if one is maintained."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
