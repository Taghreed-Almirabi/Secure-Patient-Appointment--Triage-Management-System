"""
Root launcher for the Secure Patient Appointment & Triage Web Dashboard.
Execute: python app.py
"""

from src.web_app import app

if __name__ == "__main__":
    print("\n" + "="*80)
    print("  AEGISHEALTH - SECURE CLINICAL TRIAGE & APPOINTMENT MANAGEMENT SYSTEM")
    print("  Starting Flask Web Server on http://127.0.0.1:5000")
    print("="*80 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
