"""
Unit and Integration Test Suite for Flask Web Application Endpoints.
Validates HTTP routing, JSON API responses, template rendering, and session security.
"""

import pytest
from src.web_app import app


@pytest.fixture
def client():
    """Provides a Flask test client with testing mode enabled."""
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test_secret_key"
    with app.test_client() as client:
        yield client


class TestWebRoutes:
    """Tests web UI pages and JSON API endpoints."""

    def test_root_redirects_to_dashboard(self, client):
        res = client.get("/")
        assert res.status_code == 302
        assert "/dashboard" in res.headers["Location"]

    def test_dashboard_page_renders_successfully(self, client):
        res = client.get("/dashboard")
        assert res.status_code == 200
        assert b"Patient Intake &amp; Triage Assessment" in res.data or b"Patient Intake & Triage Assessment" in res.data
        assert b"Total Patients" in res.data

    def test_api_evaluate_triage_critical(self, client):
        payload = {
            "heart_rate": 155,
            "systolic_bp": 70,
            "sp02": 82.0,
            "pain_score": 9
        }
        res = client.post("/api/evaluate_triage", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["result"]["category"] == "Category 1"
        assert data["result"]["priority_score"] == 100
        assert data["result"]["max_wait_minutes"] == 0

    def test_api_evaluate_triage_routine(self, client):
        payload = {
            "heart_rate": 72,
            "systolic_bp": 120,
            "sp02": 99.0,
            "pain_score": 1
        }
        res = client.post("/api/evaluate_triage", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["result"]["category"] == "Category 4"
        assert data["result"]["priority_score"] == 20

    def test_appointments_page_renders(self, client):
        res = client.get("/appointments")
        assert res.status_code == 200
        assert b"Doctor Scheduling &amp; Priority Queue Engine" in res.data or b"Doctor Scheduling" in res.data

    def test_patients_page_renders(self, client):
        res = client.get("/patients")
        assert res.status_code == 200
        assert b"Registered Patients &amp; Clinical Audit Records" in res.data or b"Registered Patients" in res.data

    def test_login_page_renders(self, client):
        res = client.get("/login")
        assert res.status_code == 200
        assert b"Hospital Staff Portal" in res.data

    def test_login_successful_authentication(self, client):
        res = client.post("/login", data={
            "username": "dr_smith",
            "password": "DoctorPass#2026"
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"Welcome back, dr_smith!" in res.data

    def test_login_invalid_password_fails(self, client):
        res = client.post("/login", data={
            "username": "dr_smith",
            "password": "WrongPassword#999"
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"Authentication Failed" in res.data
