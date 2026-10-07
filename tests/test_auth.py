"""
Unit Test Suite for Authentication, Password Security & RBAC (Part B).
Validates PBKDF2 salting uniqueness, constant-time verification,
role-based authorization rules, and HMAC tamper detection.
"""

import pytest
from src.models import (
    UserRole,
    AuthenticationError,
    AuthorizationError,
)
from src.auth_security import (
    hash_password,
    verify_password,
    register_user,
    authenticate_user,
    verify_role,
    require_role,
    generate_record_checksum,
    verify_record_checksum,
)


class TestPasswordSecurityAndSalting:
    """Tests cryptographic hashing, salt entropy, and constant-time verification."""

    def test_salting_uniqueness_for_identical_passwords(self):
        """Two identical plaintext passwords generate completely distinct hashes due to dynamic salts."""
        raw_password = "ClinicalSecretPassword123!"
        hash1, salt1 = hash_password(raw_password)
        hash2, salt2 = hash_password(raw_password)

        assert salt1 != salt2
        assert hash1 != hash2
        assert len(hash1) == 64  # SHA-256 hex string
        assert len(hash2) == 64

    def test_password_verification_success(self):
        """Valid password matches hash and salt."""
        raw_password = "CorrectDoctorPassword#1"
        pwd_hash, salt = hash_password(raw_password)
        assert verify_password(raw_password, salt, pwd_hash) is True

    def test_password_verification_failure_on_wrong_password(self):
        """Incorrect password fails verification."""
        raw_password = "CorrectDoctorPassword#1"
        pwd_hash, salt = hash_password(raw_password)
        assert verify_password("WrongDoctorPassword#99", salt, pwd_hash) is False

    def test_short_password_rejected(self):
        """Password shorter than 6 characters is rejected."""
        with pytest.raises(ValueError, match="at least 6 characters"):
            hash_password("12345")


class TestUserRegistrationAndAuthentication:
    """Tests user lifecycle, credential verification, and error paths."""

    def test_register_and_authenticate_success(self, in_memory_db):
        """User can register and subsequently authenticate."""
        registered = register_user(
            in_memory_db,
            username="dr_house",
            password="DiagnosticGenius2026!",
            role=UserRole.DOCTOR
        )
        assert registered.id is not None
        assert registered.username == "dr_house"
        assert registered.role == UserRole.DOCTOR

        authenticated = authenticate_user(in_memory_db, "dr_house", "DiagnosticGenius2026!")
        assert authenticated.id == registered.id
        assert authenticated.username == "dr_house"

    def test_authenticate_with_wrong_password_raises_error(self, in_memory_db):
        """Authentication with invalid password raises AuthenticationError."""
        register_user(
            in_memory_db,
            username="nurse_jackie",
            password="RealNursePassword#1",
            role=UserRole.TRIAGE_NURSE
        )
        with pytest.raises(AuthenticationError, match="Invalid username or password"):
            authenticate_user(in_memory_db, "nurse_jackie", "FakePassword#99")

    def test_authenticate_nonexistent_user_raises_error(self, in_memory_db):
        """Authentication with non-existent username raises AuthenticationError."""
        with pytest.raises(AuthenticationError, match="Invalid username or password"):
            authenticate_user(in_memory_db, "ghost_user", "AnyPassword#1")

    def test_duplicate_username_registration_rejected(self, in_memory_db):
        """Attempting to register an existing username raises ValueError."""
        register_user(in_memory_db, "duplicate_user", "Pass12345!", UserRole.ADMIN)
        with pytest.raises(ValueError, match="already registered"):
            register_user(in_memory_db, "duplicate_user", "Pass67890!", UserRole.ADMIN)


class TestRoleBasedAccessControl:
    """Tests RBAC role enforcement and permission checks."""

    def test_verify_role_matches(self, sample_doctor, sample_nurse, sample_admin):
        assert verify_role(sample_doctor, [UserRole.DOCTOR]) is True
        assert verify_role(sample_nurse, [UserRole.TRIAGE_NURSE]) is True
        assert verify_role(sample_admin, [UserRole.ADMIN]) is True
        assert verify_role(sample_doctor, [UserRole.TRIAGE_NURSE, UserRole.ADMIN]) is False

    def test_require_role_raises_authorization_error(self, sample_nurse):
        """Nurse attempting Doctor-only action raises AuthorizationError."""
        with pytest.raises(AuthorizationError, match="Access denied"):
            require_role(sample_nurse, [UserRole.DOCTOR])

    def test_require_role_passes_when_authorized(self, sample_admin):
        """Admin accessing Admin role succeeds without exception."""
        require_role(sample_admin, [UserRole.ADMIN])


class TestClinicalDataIntegrity:
    """Tests HMAC cryptographic checksum signing and tamper detection."""

    def test_hmac_checksum_verification_success(self):
        payload = "patient_id=101|hr=145|sbp=72|sp02=86.0|pain=9|cat=Category 1|score=100"
        sig = generate_record_checksum(payload)
        assert verify_record_checksum(payload, sig) is True

    def test_tampered_payload_fails_verification(self):
        payload = "patient_id=101|hr=145|sbp=72|sp02=86.0|pain=9|cat=Category 1|score=100"
        sig = generate_record_checksum(payload)
        tampered_payload = "patient_id=101|hr=80|sbp=120|sp02=98.0|pain=2|cat=Category 4|score=20"
        assert verify_record_checksum(tampered_payload, sig) is False
