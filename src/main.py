"""
Main Execution and Demonstration Script (Part A: Algorithmic Logic & Output Validation).
Runs a complete clinical workflow: database setup, authentication, patient intake,
deterministic triage scoring, priority scheduling, conflict detection, and emergency preemption.
"""

from __future__ import annotations
import os
import sys
from datetime import datetime

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

from .models import (
    UserRole,
    TriageVitals,
    TriageCategory,
    AppointmentConflictError,
    AppointmentValidationError,
)
from .database import DatabaseManager
from .auth_security import (
    register_user,
    authenticate_user,
    verify_record_checksum,
)
from .triage_engine import evaluate_triage, record_patient_triage
from .appointment_manager import AppointmentManager


# Ensure stdout handles UTF-8 safely on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def render_table(rows: list, headers: list, title: str = "") -> None:
    """Helper to render formatted console tables using ASCII-safe box format."""
    if title:
        print(f"\n{'='*80}")
        print(f"  {title.upper()}")
        print(f"{'='*80}")

    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="grid"))
    else:
        # Fallback pretty printer
        col_widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))

        sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
        header_row = "| " + " | ".join(str(h).ljust(w) for h, w in zip(headers, col_widths)) + " |"

        print(sep)
        print(header_row)
        print(sep)
        for row in rows:
            print("| " + " | ".join(str(c).ljust(w) for c, w in zip(row, col_widths)) + " |")
        print(sep)


def run_demonstration(db_path: str = "hospital_demo.db") -> None:
    """Executes the full clinical demonstration scenario."""
    # Clean old demo db if exists
    if db_path != ":memory:" and os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass

    print("\n" + "#" * 80)
    print("#  SECURE PATIENT APPOINTMENT & TRIAGE MANAGEMENT SYSTEM")
    print("#  Production Demonstration & Output Validation (Part A)")
    print("#" * 80)

    # 1. Initialize Database
    db = DatabaseManager(db_path)
    # Use fixed reference time for deterministic demonstration
    ref_time = datetime(2026, 10, 15, 8, 0, 0)
    appointment_mgr = AppointmentManager(db, slot_duration_minutes=30, reference_time=ref_time)

    # 2. Staff Registration & Authentication
    print("\n>>> STEP 1: Staff Registration & Role-Based Access Control (RBAC)")
    staff_data = [
        ("admin_sarah", "AdminPass#2026", UserRole.ADMIN),
        ("nurse_emily", "NursePass#2026", UserRole.TRIAGE_NURSE),
        ("dr_wilson", "DoctorPass#2026", UserRole.DOCTOR),
        ("dr_smith", "DoctorPass#2026", UserRole.DOCTOR),
    ]

    registered_users = []
    for username, pwd, role in staff_data:
        u = register_user(db, username, pwd, role)
        registered_users.append([u.id, u.username, u.role.value, u.password_hash[:16] + "...", u.salt[:8] + "..."])

    render_table(
        registered_users,
        headers=["User ID", "Username", "Role", "Password Hash (PBKDF2-SHA256)", "Salt"],
        title="Hospital Staff Registry"
    )

    # Authenticate staff
    nurse_user = authenticate_user(db, "nurse_emily", "NursePass#2026")
    dr_smith = authenticate_user(db, "dr_smith", "DoctorPass#2026")
    print(f"\n[AUTH SUCCESS] Logged in: Nurse '{nurse_user.username}' (Role: {nurse_user.role.value})")
    print(f"[AUTH SUCCESS] Logged in: Doctor '{dr_smith.username}' (Role: {dr_smith.role.value})")

    # 3. Patient Enrollment
    print("\n>>> STEP 2: Patient Registration & Clinical Intake")
    patient_data = [
        ("NAT-1001", "John Carter (Critical)", 64, "+1-555-0101"),
        ("NAT-1002", "Maria Rodriguez (Emergent)", 45, "+1-555-0102"),
        ("NAT-1003", "David Kim (Routine)", 29, "+1-555-0103"),
        ("NAT-1004", "Emma Watson (Urgent)", 52, "+1-555-0104"),
    ]

    patients = []
    patient_table_rows = []
    for nid, name, age, contact in patient_data:
        p = db.create_patient(nid, name, age, contact)
        patients.append(p)
        patient_table_rows.append([p.id, p.national_id, p.full_name, p.age, p.contact])

    render_table(
        patient_table_rows,
        headers=["Patient ID", "National ID", "Full Name", "Age", "Contact"],
        title="Registered Patients"
    )

    # 4. Triage Calculations (Part A Algorithm Validation)
    print("\n>>> STEP 3: Triage Engine Execution & ESI Classification")

    vitals_cases = [
        # Patient 1: Critical (SpO2=84% < 90%, HR=152 > 140 bpm, BP=72 < 80 mmHg, Pain=9) -> Cat 1
        TriageVitals(patient_id=patients[0].id, heart_rate=152, systolic_bp=72, sp02=84.0, pain_score=9),
        # Patient 2: Emergent (SpO2=92% in 90-94%, HR=128 in 110-140, BP=135, Pain=8) -> Cat 2
        TriageVitals(patient_id=patients[1].id, heart_rate=128, systolic_bp=135, sp02=92.0, pain_score=8),
        # Patient 3: Routine (Normal vitals, HR=72, BP=120, SpO2=99%, Pain=2) -> Cat 4
        TriageVitals(patient_id=patients[2].id, heart_rate=72, systolic_bp=120, sp02=99.0, pain_score=2),
        # Patient 4: Urgent (HR=106 in 100-109, BP=124, SpO2=97%, Pain=6 in 5-7) -> Cat 3
        TriageVitals(patient_id=patients[3].id, heart_rate=106, systolic_bp=124, sp02=97.0, pain_score=6),
    ]

    triage_results = []
    triage_table_rows = []

    for v in vitals_cases:
        res, rec = record_patient_triage(db, v)
        triage_results.append(res)
        p = db.get_patient_by_id(v.patient_id)
        # Verify HMAC checksum
        payload = (
            f"patient_id={v.patient_id}|hr={v.heart_rate}|"
            f"sbp={v.systolic_bp}|sp02={v.sp02}|pain={v.pain_score}|"
            f"cat={res.category.value}|score={res.priority_score}"
        )
        is_valid = verify_record_checksum(payload, rec.checksum)
        integrity_status = "VERIFIED (HMAC-OK)" if is_valid else "TAMPER DETECTED"

        triage_table_rows.append([
            f"#{p.id} {p.full_name.split()[0]}",
            f"{v.heart_rate} bpm",
            f"{v.systolic_bp} mmHg",
            f"{v.sp02}%",
            f"{v.pain_score}/10",
            res.category.value,
            res.category_label,
            res.priority_score,
            f"{res.max_wait_minutes} min",
            integrity_status
        ])

    render_table(
        triage_table_rows,
        headers=[
            "Patient", "Heart Rate", "Systolic BP", "SpO2", "Pain",
            "Category", "Clinical Label", "Priority Score", "Max Wait", "HMAC Integrity"
        ],
        title="Deterministic Triage Assessment Results (ESI Algorithm)"
    )

    # 5. Appointment Booking & Conflict Preemption Demonstration
    print("\n>>> STEP 4: Appointment Allocation & Conflict Management")

    booking_date = "2026-10-15"
    target_slot = f"{booking_date} 10:00"

    print(f"\n--- Scenario A: Routine Patient #{patients[2].id} ({patients[2].full_name}) books {target_slot} ---")
    alloc_1 = appointment_mgr.schedule_appointment(
        patient_id=patients[2].id,
        doctor_id=dr_smith.id,
        appointment_time=target_slot,
        priority_score=triage_results[2].priority_score,
        urgency_category=triage_results[2].category,
        notes="Routine health follow-up."
    )
    print(f"Result: {alloc_1.message}")

    print(f"\n--- Scenario B: Another Routine Patient #{patients[3].id} attempts double-booking at {target_slot} ---")
    try:
        appointment_mgr.schedule_appointment(
            patient_id=patients[3].id,
            doctor_id=dr_smith.id,
            appointment_time=target_slot,
            priority_score=triage_results[3].priority_score,
            urgency_category=triage_results[3].category,
            notes="Routine check."
        )
    except AppointmentConflictError as e:
        print(f"[CONFLICT DETECTED & PREVENTED] -> {e}")

    # Display schedule before emergency
    schedule_rows_before = []
    for appt in appointment_mgr.get_doctor_schedule(dr_smith.id):
        pt = db.get_patient_by_id(appt.patient_id)
        schedule_rows_before.append([
            appt.id, f"Dr. {dr_smith.username}", f"#{pt.id} {pt.full_name}",
            appt.appointment_time, appt.status.value, appt.notes or "-"
        ])

    render_table(
        schedule_rows_before,
        headers=["Appt ID", "Doctor", "Patient", "Scheduled Time", "Status", "Clinical Notes"],
        title=f"Schedule for Dr. {dr_smith.username} (Before Emergency Arrival)"
    )

    print(f"\n--- Scenario C: Critical Emergency Patient #{patients[0].id} ({patients[0].full_name}) arrives ---")
    print(f"Patient has Priority Score: 100 (Resuscitation / Immediate). Needs {target_slot}.")

    alloc_emergency = appointment_mgr.schedule_appointment(
        patient_id=patients[0].id,
        doctor_id=dr_smith.id,
        appointment_time=target_slot,
        priority_score=triage_results[0].priority_score,
        urgency_category=triage_results[0].category,
        notes="CRITICAL: Severe Hypoxia & Hypotension."
    )
    print(f"[EMERGENCY PREEMPTION EXECUTED] -> {alloc_emergency.message}")

    # Also book Emergent Patient 2 at 11:00
    appointment_mgr.schedule_appointment(
        patient_id=patients[1].id,
        doctor_id=dr_smith.id,
        appointment_time=f"{booking_date} 11:00",
        priority_score=triage_results[1].priority_score,
        urgency_category=triage_results[1].category,
        notes="Emergent: Moderate hypoxia with acute pain."
    )

    # Display schedule after emergency resolution
    schedule_rows_after = []
    for appt in appointment_mgr.get_doctor_schedule(dr_smith.id):
        pt = db.get_patient_by_id(appt.patient_id)
        schedule_rows_after.append([
            appt.id, f"Dr. {dr_smith.username}", f"#{pt.id} {pt.full_name}",
            appt.appointment_time, appt.status.value, appt.notes or "-"
        ])

    render_table(
        schedule_rows_after,
        headers=["Appt ID", "Doctor", "Patient", "Final Scheduled Time", "Status", "Clinical Notes / Audit Trail"],
        title=f"Schedule for Dr. {dr_smith.username} (After Priority Reallocation & Preemption)"
    )

def interactive_menu(db_path: str = "hospital_live.db") -> None:
    """Provides an interactive CLI menu for live testing and demonstration."""
    db = DatabaseManager(db_path)
    appointment_mgr = AppointmentManager(db, slot_duration_minutes=30)

    # Seed initial staff if not already present
    if not db.list_users():
        register_user(db, "admin", "Admin123!", UserRole.ADMIN)
        register_user(db, "nurse_joy", "Nurse123!", UserRole.TRIAGE_NURSE)
        register_user(db, "dr_smith", "DocSmith123!", UserRole.DOCTOR)
        register_user(db, "dr_wilson", "DocWilson123!", UserRole.DOCTOR)

    while True:
        print("\n" + "="*60)
        print("  HOSPITAL TRIAGE & APPOINTMENT MANAGEMENT SYSTEM")
        print("="*60)
        print("1. Run Automated Full System Demo (Part A Scenarios)")
        print("2. Register New Patient & Calculate Triage Score")
        print("3. Book / Schedule Appointment (with Conflict Check)")
        print("4. View Doctor Schedule")
        print("5. View All Patients & Triage History")
        print("6. Run PyTest Unit Tests (Part B)")
        print("7. Exit")
        choice = input("\nEnter your choice (1-7): ").strip()

        if choice == "1":
            run_demonstration("demo_temp.db")
        elif choice == "2":
            nid = input("Enter National ID (e.g. NAT-9001): ").strip()
            name = input("Enter Full Name: ").strip()
            try:
                age = int(input("Enter Age: ").strip())
                contact = input("Enter Contact Number: ").strip()
                p = db.create_patient(nid, name, age, contact)

                print("\n--- Enter Patient Vital Signs for Triage ---")
                hr = int(input("Heart Rate (bpm, e.g. 75): ").strip())
                sbp = int(input("Systolic Blood Pressure (mmHg, e.g. 120): ").strip())
                sp02 = float(input("Blood Oxygen SpO2 (%, e.g. 98.0): ").strip())
                pain = int(input("Pain Score (0-10, e.g. 3): ").strip())

                vitals = TriageVitals(patient_id=p.id, heart_rate=hr, systolic_bp=sbp, sp02=sp02, pain_score=pain)
                res, rec = record_patient_triage(db, vitals)

                print("\n" + "*"*50)
                print(f"TRIAGE EVALUATION FOR {p.full_name.upper()}:")
                print(f"- Urgency Category: {res.category.value} ({res.category_label})")
                print(f"- Priority Score:   {res.priority_score}/100")
                print(f"- Max Wait Limit:   {res.max_wait_minutes} minutes")
                print(f"- Rationale:        {', '.join(res.clinical_rationale)}")
                print(f"- HMAC Checksum:    {rec.checksum[:20]}... (Integrity Signed)")
                print("*"*50)
            except Exception as e:
                print(f"\n[ERROR] {e}")
        elif choice == "3":
            try:
                patients = db.list_patients()
                if not patients:
                    print("\n[INFO] No patients registered yet. Please register a patient first (Option 2).")
                    continue

                doctors = db.list_users(role=UserRole.DOCTOR)
                print("\nAvailable Doctors:")
                for d in doctors:
                    print(f"  ID #{d.id}: Dr. {d.username}")

                print("\nRegistered Patients:")
                for p in patients:
                    print(f"  ID #{p.id}: {p.full_name} (National ID: {p.national_id})")

                pid = int(input("\nEnter Patient ID: ").strip())
                did = int(input("Enter Doctor ID: ").strip())
                time_str = input("Enter Appointment Time (YYYY-MM-DD HH:MM, e.g. 2026-10-15 10:00): ").strip()
                notes = input("Enter Notes (optional): ").strip()

                latest_triage = db.get_latest_triage_by_patient(pid)
                p_score = latest_triage.priority_score if latest_triage else 20
                u_cat = latest_triage.urgency_category if latest_triage else TriageCategory.CATEGORY_4

                alloc = appointment_mgr.schedule_appointment(
                    patient_id=pid,
                    doctor_id=did,
                    appointment_time=time_str,
                    priority_score=p_score,
                    urgency_category=u_cat,
                    notes=notes
                )
                print(f"\n[SUCCESS] {alloc.message}")
            except Exception as e:
                print(f"\n[BOOKING FAILED / CONFLICT] {e}")
        elif choice == "4":
            doctors = db.list_users(role=UserRole.DOCTOR)
            for d in doctors:
                print(f"ID #{d.id}: Dr. {d.username}")
            try:
                did = int(input("\nEnter Doctor ID to view schedule: ").strip())
                appts = appointment_mgr.get_doctor_schedule(did)
                if not appts:
                    print(f"\nNo appointments scheduled for Doctor #{did}.")
                else:
                    rows = []
                    for a in appts:
                        pt = db.get_patient_by_id(a.patient_id)
                        rows.append([a.id, f"#{pt.id} {pt.full_name}", a.appointment_time, a.status.value, a.notes or "-"])
                    render_table(rows, headers=["Appt ID", "Patient", "Time", "Status", "Notes"], title=f"Schedule for Doctor #{did}")
            except Exception as e:
                print(f"\n[ERROR] {e}")
        elif choice == "5":
            patients = db.list_patients()
            if not patients:
                print("\nNo patients registered.")
            else:
                rows = []
                for p in patients:
                    rec = db.get_latest_triage_by_patient(p.id)
                    score = rec.priority_score if rec else "-"
                    cat = rec.urgency_category if rec else "Unassessed"
                    rows.append([p.id, p.national_id, p.full_name, p.age, p.contact, cat, score])
                render_table(rows, headers=["ID", "National ID", "Name", "Age", "Contact", "Latest Triage", "Score"], title="Patient Registry & Triage Status")
        elif choice == "6":
            import pytest
            print("\nRunning PyTest Unit Tests...\n")
            pytest.main(["-v", "tests/"])
        elif choice == "7":
            print("\nExiting. Thank you!")
            break
        else:
            print("\nInvalid choice. Please select 1-7.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-i", "--interactive"):
        interactive_menu()
    else:
        run_demonstration()

