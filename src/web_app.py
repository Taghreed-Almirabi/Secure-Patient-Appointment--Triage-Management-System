"""
Flask Web Application for the Secure Patient Appointment & Triage Management System.
Connects the deterministic ESI triage engine, priority queue appointment manager,
PBKDF2-HMAC authentication, and SQLite persistence layer to a modern Tailwind CSS Web UI.

Author: Software Engineering Team
Version: 1.0.0 (Production Release)
"""

from __future__ import annotations
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
)

# Internal domain and engine imports
from .models import (
    UserRole,
    TriageVitals,
    TriageCategory,
    AppointmentStatus,
    AppointmentConflictError,
    AppointmentValidationError,
    MedicalValidationError,
    AuthenticationError,
    ResourceNotFoundError,
)
from .database import DatabaseManager
from .auth_security import (
    register_user,
    authenticate_user,
    verify_record_checksum,
    generate_record_checksum,
)
from .triage_engine import evaluate_triage, record_patient_triage
from .appointment_manager import AppointmentManager

# Initialize Flask Application
app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

# Global Database and Engine Instances
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hospital_web.db")
db = DatabaseManager(DB_PATH)
appointment_mgr = AppointmentManager(db, slot_duration_minutes=30)


def seed_initial_demo_data() -> None:
    """
    Populates the database with initial clinical staff, sample patients, and
    baseline triage scenarios if the database tables are empty upon startup.
    """
    # 1. Seed Staff Users (Doctors, Triage Nurses, Admins)
    if not db.list_users():
        register_user(db, "admin_sarah", "AdminPass#2026", UserRole.ADMIN)
        register_user(db, "nurse_emily", "NursePass#2026", UserRole.TRIAGE_NURSE)
        dr_smith = register_user(db, "dr_smith", "DoctorPass#2026", UserRole.DOCTOR)
        dr_wilson = register_user(db, "dr_wilson", "DoctorPass#2026", UserRole.DOCTOR)

        # 2. Seed Initial Clinical Patients
        p1 = db.create_patient("NAT-1001", "John Carter (Critical)", 64, "+1-555-0101")
        p2 = db.create_patient("NAT-1002", "Maria Rodriguez (Emergent)", 45, "+1-555-0102")
        p3 = db.create_patient("NAT-1003", "David Kim (Routine)", 29, "+1-555-0103")
        p4 = db.create_patient("NAT-1004", "Emma Watson (Urgent)", 52, "+1-555-0104")

        # 3. Seed Triage Calculations with HMAC Signatures
        # John: Critical (Cat 1: SpO2 84%, HR 152, BP 72, Pain 9) -> Score 100
        record_patient_triage(db, TriageVitals(p1.id, heart_rate=152, systolic_bp=72, sp02=84.0, pain_score=9))
        # Maria: Emergent (Cat 2: SpO2 92%, HR 128, BP 135, Pain 8) -> Score 75
        record_patient_triage(db, TriageVitals(p2.id, heart_rate=128, systolic_bp=135, sp02=92.0, pain_score=8))
        # David: Routine (Cat 4: Normal vitals) -> Score 20
        record_patient_triage(db, TriageVitals(p3.id, heart_rate=72, systolic_bp=120, sp02=99.0, pain_score=2))
        # Emma: Urgent (Cat 3: HR 106, BP 124, SpO2 97%, Pain 6) -> Score 50
        record_patient_triage(db, TriageVitals(p4.id, heart_rate=106, systolic_bp=124, sp02=97.0, pain_score=6))

        # 4. Seed Initial Schedule for Dr. Smith
        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            # Routine appointment for David Kim at 10:00 AM
            appointment_mgr.schedule_appointment(
                patient_id=p3.id,
                doctor_id=dr_smith.id,
                appointment_time=f"{today_str} 10:00",
                priority_score=20,
                urgency_category=TriageCategory.CATEGORY_4,
                notes="Routine annual physical examination."
            )
            # Emergent appointment for Maria Rodriguez at 11:00 AM
            appointment_mgr.schedule_appointment(
                patient_id=p2.id,
                doctor_id=dr_smith.id,
                appointment_time=f"{today_str} 11:00",
                priority_score=75,
                urgency_category=TriageCategory.CATEGORY_2,
                notes="Acute migraine and elevated heart rate."
            )
        except Exception:
            pass


# Ensure seed data is initialized upon import
seed_initial_demo_data()


# =============================================================================
# Helper Utility Functions
# =============================================================================

def get_system_stats() -> Dict[str, int]:
    """
    Computes real-time system Key Performance Indicators (KPIs)
    displayed across dashboard metric cards.
    """
    patients = db.list_patients()
    doctors = db.list_users(role=UserRole.DOCTOR)
    appointments = db.list_appointments()

    critical_count = 0
    for p in patients:
        rec = db.get_latest_triage_by_patient(p.id)
        if rec and rec.urgency_category in (TriageCategory.CATEGORY_1.value, TriageCategory.CATEGORY_2.value):
            critical_count += 1

    scheduled_appts = sum(1 for a in appointments if a.status == AppointmentStatus.SCHEDULED)

    return {
        "total_patients": len(patients),
        "critical_cases": critical_count,
        "scheduled_appointments": scheduled_appts,
        "total_doctors": len(doctors),
    }


# =============================================================================
# Web Routes & Controller Handlers
# =============================================================================

@app.route("/")
def index():
    """Redirects the root URL to the interactive triage intake dashboard."""
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    """
    Renders the primary Clinical Triage Dashboard.
    Provides the patient intake form, interactive vitals calculator,
    real-time KPI metrics, and recent triage intake history.
    """
    stats = get_system_stats()
    patients = db.list_patients()
    
    # Collect recent triage history with associated patient info
    recent_triages = []
    for p in reversed(patients[-8:]):
        rec = db.get_latest_triage_by_patient(p.id)
        if rec:
            recent_triages.append({"patient": p, "record": rec})

    return render_template("dashboard.html", stats=stats, recent_triages=recent_triages)


@app.route("/triage/process", methods=["POST"])
def process_triage():
    """
    Processes patient demographic intake and clinical vital parameters from the form.
    Calculates deterministic ESI triage score, generates HMAC checksum,
    and persists the record to SQLite.
    """
    full_name = request.form.get("full_name", "").strip()
    national_id = request.form.get("national_id", "").strip()
    age_str = request.form.get("age", "").strip()
    contact = request.form.get("contact", "").strip()

    try:
        age = int(age_str)
        heart_rate = int(request.form.get("heart_rate", "75"))
        systolic_bp = int(request.form.get("systolic_bp", "120"))
        sp02 = float(request.form.get("sp02", "98.0"))
        pain_score = int(request.form.get("pain_score", "0"))

        # Find or create patient record
        patient = db.get_patient_by_national_id(national_id)
        if not patient:
            patient = db.create_patient(
                national_id=national_id,
                full_name=full_name,
                age=age,
                contact=contact
            )

        # Build vitals and evaluate triage
        vitals = TriageVitals(
            patient_id=patient.id,
            heart_rate=heart_rate,
            systolic_bp=systolic_bp,
            sp02=sp02,
            pain_score=pain_score
        )
        result, record = record_patient_triage(db, vitals)

        flash(
            f"Intake completed for {patient.full_name}. Evaluated as {result.category.value} "
            f"({result.category_label}) with Priority Score {result.priority_score}/100. "
            f"HMAC checksum generated.",
            "success"
        )
    except (ValueError, MedicalValidationError) as e:
        flash(f"Clinical Validation Error: {e}", "error")
    except Exception as e:
        flash(f"Unexpected Error during intake: {e}", "error")

    return redirect(url_for("dashboard"))


@app.route("/api/evaluate_triage", methods=["POST"])
def api_evaluate_triage():
    """
    Asynchronous JSON REST endpoint for live, client-side triage calculations
    without requiring a full-page reload.
    """
    data = request.get_json() or {}
    try:
        vitals = TriageVitals(
            patient_id=0,
            heart_rate=int(data.get("heart_rate", 75)),
            systolic_bp=int(data.get("systolic_bp", 120)),
            sp02=float(data.get("sp02", 98.0)),
            pain_score=int(data.get("pain_score", 0))
        )
        res = evaluate_triage(vitals)
        return jsonify({
            "success": True,
            "result": {
                "category": res.category.value,
                "category_label": res.category_label,
                "priority_score": res.priority_score,
                "max_wait_minutes": res.max_wait_minutes,
                "clinical_rationale": res.clinical_rationale
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/appointments", methods=["GET"])
def appointments_page():
    """
    Renders the Doctor Appointment Scheduling and Priority Conflict Queue page.
    Displays doctor timetables, the booking form, and emergency preemption tools.
    """
    doctors = db.list_users(role=UserRole.DOCTOR)
    patients = db.list_patients()
    
    selected_doctor_id = request.args.get("doctor_id", type=int)
    if not selected_doctor_id and doctors:
        selected_doctor_id = doctors[0].id

    # Retrieve doctor schedule
    appts = appointment_mgr.get_doctor_schedule(selected_doctor_id) if selected_doctor_id else []
    
    # Enrich appointment objects with patient and triage details
    schedule_list = []
    for a in appts:
        pt = db.get_patient_by_id(a.patient_id)
        tr = db.get_latest_triage_by_patient(a.patient_id)
        schedule_list.append({
            "appointment": a,
            "patient": pt,
            "triage": tr
        })

    today_str = datetime.now().strftime("%Y-%m-%d")

    return render_template(
        "appointments.html",
        doctors=doctors,
        patients=patients,
        selected_doctor_id=selected_doctor_id,
        schedule_list=schedule_list,
        default_date=today_str
    )


@app.route("/appointments/book", methods=["POST"])
def book_appointment_route():
    """
    Handles appointment booking requests.
    Enforces strict double-booking rejection for routine consultations and
    triggers automated emergency preemption if Category 1/2 patients require an occupied slot.
    """
    try:
        patient_id = int(request.form.get("patient_id", "0"))
        doctor_id = int(request.form.get("doctor_id", "0"))
        date_str = request.form.get("appointment_date", "").strip()
        time_slot = request.form.get("appointment_time_slot", "").strip()
        notes = request.form.get("notes", "").strip()

        combined_time = f"{date_str} {time_slot}"

        # Retrieve patient triage score to determine priority eligibility
        triage = db.get_latest_triage_by_patient(patient_id)
        p_score = triage.priority_score if triage else 20
        u_cat = triage.urgency_category if triage else TriageCategory.CATEGORY_4

        alloc = appointment_mgr.schedule_appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_time=combined_time,
            priority_score=p_score,
            urgency_category=u_cat,
            notes=notes
        )

        if alloc.emergency_preemption:
            flash(alloc.message, "warning")
        else:
            flash(alloc.message, "success")

    except AppointmentConflictError as e:
        flash(f"Booking Conflict Detected: {e}", "error")
    except (AppointmentValidationError, ResourceNotFoundError) as e:
        flash(f"Validation Error: {e}", "error")
    except Exception as e:
        flash(f"Scheduling Error: {e}", "error")

    return redirect(url_for("appointments_page", doctor_id=doctor_id))


@app.route("/appointments/complete/<int:appt_id>", methods=["POST"])
def complete_appointment_route(appt_id: int):
    """Marks an existing appointment as Completed."""
    try:
        appointment_mgr.complete_appointment(appt_id)
        flash(f"Appointment #{appt_id} marked as Completed.", "success")
    except Exception as e:
        flash(f"Error completing appointment: {e}", "error")
    return redirect(url_for("appointments_page"))


@app.route("/appointments/cancel/<int:appt_id>", methods=["POST"])
def cancel_appointment_route(appt_id: int):
    """Cancels an existing appointment."""
    try:
        appointment_mgr.cancel_appointment(appt_id, reason="Cancelled via Web Portal")
        flash(f"Appointment #{appt_id} has been cancelled.", "info")
    except Exception as e:
        flash(f"Error cancelling appointment: {e}", "error")
    return redirect(url_for("appointments_page"))


@app.route("/appointments/simulate_conflict", methods=["POST"])
def simulate_conflict_demo():
    """
    Demonstration helper endpoint:
    1. Ensures a routine patient is booked at 10:00 AM for Dr. Smith.
    2. Introduces a Category 1 critical patient (John Carter, Score 100) requesting 10:00 AM.
    3. Executes automated priority preemption, displacing the routine patient to 10:30 AM.
    """
    doctors = db.list_users(role=UserRole.DOCTOR)
    if not doctors:
        flash("No doctors registered.", "error")
        return redirect(url_for("appointments_page"))

    dr_smith = doctors[0]
    patients = db.list_patients()
    if len(patients) < 2:
        flash("Need at least 2 patients to simulate conflict.", "error")
        return redirect(url_for("appointments_page"))

    p_critical = patients[0]  # John Carter (Score 100)
    p_routine = patients[2] if len(patients) > 2 else patients[1]  # Routine patient

    today_str = datetime.now().strftime("%Y-%m-%d")
    target_slot = f"{today_str} 10:00"

    try:
        # Clear existing scheduled slot at target time if any
        existing = db.get_scheduled_appointment_at(dr_smith.id, target_slot)
        if existing:
            db.update_appointment_status(existing.id, AppointmentStatus.CANCELLED)

        # 1. Book routine patient into 10:00 AM
        appointment_mgr.schedule_appointment(
            patient_id=p_routine.id,
            doctor_id=dr_smith.id,
            appointment_time=target_slot,
            priority_score=20,
            urgency_category=TriageCategory.CATEGORY_4,
            notes="Routine consultation checkup."
        )

        # 2. Critical emergency patient arrives requesting the exact same 10:00 AM slot
        alloc = appointment_mgr.schedule_appointment(
            patient_id=p_critical.id,
            doctor_id=dr_smith.id,
            appointment_time=target_slot,
            priority_score=100,
            urgency_category=TriageCategory.CATEGORY_1,
            notes="CRITICAL EMERGENCY: Severe Hypoxia & Hypotension override."
        )

        flash(
            f"⚡ CONFLICT RESOLVED: Critical Emergency Patient #{p_critical.id} ({p_critical.full_name}) "
            f"successfully preempted slot {target_slot}. Routine Patient #{p_routine.id} ({p_routine.full_name}) "
            f"was automatically rescheduled to {alloc.rescheduled_to}.",
            "warning"
        )
    except Exception as e:
        flash(f"Simulation Error: {e}", "error")

    return redirect(url_for("appointments_page", doctor_id=dr_smith.id))


@app.route("/patients")
def patients_page():
    """
    Renders the Patient Records Data Table.
    Displays all registered patients with their latest vital signs,
    calculated ESI category, priority score, and HMAC cryptographic signature status.
    """
    patients = db.list_patients()
    patients_list = []

    for p in patients:
        rec = db.get_latest_triage_by_patient(p.id)
        is_verified = False
        if rec and rec.checksum:
            payload = (
                f"patient_id={rec.patient_id}|hr={rec.heart_rate}|"
                f"sbp={rec.systolic_bp}|sp02={rec.sp02}|pain={rec.pain_score}|"
                f"cat={rec.urgency_category}|score={rec.priority_score}"
            )
            is_verified = verify_record_checksum(payload, rec.checksum)

        patients_list.append({
            "patient": p,
            "triage": rec,
            "is_verified": is_verified
        })

    return render_template("patients.html", patients_list=patients_list)


@app.route("/login", methods=["GET"])
def login_page():
    """Renders the medical staff authentication page."""
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_post():
    """
    Authenticates staff credentials using PBKDF2-HMAC-SHA256 password hashing.
    Establishes secure user session upon success.
    """
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    try:
        user = authenticate_user(db, username, password)
        session["user_id"] = user.id
        session["username"] = user.username
        session["role"] = user.role.value
        flash(f"Welcome back, {user.username}! (Role: {user.role.value})", "success")
        return redirect(url_for("dashboard"))
    except AuthenticationError as e:
        flash(f"Authentication Failed: {e}", "error")
    except Exception as e:
        flash(f"Login Error: {e}", "error")

    return redirect(url_for("login_page"))


@app.route("/logout")
def logout():
    """Clears staff session and redirects to login portal."""
    session.clear()
    flash("You have been securely logged out.", "info")
    return redirect(url_for("login_page"))


# =============================================================================
# Application Entry Point
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("  AEGISHEALTH - SECURE CLINICAL TRIAGE & APPOINTMENT MANAGEMENT SYSTEM")
    print("  Starting Flask Web Server on http://127.0.0.1:5000")
    print("="*80 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
