"""
Authentication, Password Security, and Data Integrity Module.
Provides PBKDF2-HMAC password hashing, salt management, RBAC enforcement,
and HMAC data integrity verification.
"""

from __future__ import annotations
import hashlib
import hmac
import secrets
from typing import Tuple, List, Union

from .models import User, UserRole, AuthenticationError, AuthorizationError
from .database import DatabaseManager

# Security parameters
PBKDF2_ITERATIONS = 100_000
HASH_ALGORITHM = "sha256"
INTEGRITY_SECRET = "HOSPITAL_TRIAGE_SECURE_KEY_2026_V1"


def generate_salt(length_bytes: int = 16) -> str:
    """Generates a cryptographically secure random hexadecimal salt string."""
    return secrets.token_hex(length_bytes)


def hash_password(password: str, salt: str | None = None) -> Tuple[str, str]:
    """
    Hashes a plaintext password using PBKDF2-HMAC-SHA256 with dynamic salt.

    Args:
        password: The plaintext password string.
        salt: Optional hexadecimal salt. If None, a new random salt is generated.

    Returns:
        Tuple of (hex_password_hash, hex_salt).
    """
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters long.")

    if salt is None:
        salt = generate_salt(16)

    # Derive 32-byte key (256 bits)
    derived_key = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS
    )
    return derived_key.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """
    Verifies a plaintext password against a stored PBKDF2-HMAC-SHA256 hash using
    constant-time string comparison to prevent side-channel timing attacks.
    """
    try:
        calculated_hash, _ = hash_password(password, salt=salt)
        return hmac.compare_digest(calculated_hash, expected_hash)
    except Exception:
        return False


def register_user(
    db: DatabaseManager,
    username: str,
    password: str,
    role: Union[UserRole, str]
) -> User:
    """
    Registers a new system user with salted PBKDF2 password hashing.

    Args:
        db: The active DatabaseManager instance.
        username: Desired unique username.
        password: Raw password.
        role: User role (Doctor, Triage_Nurse, Admin).

    Returns:
        The newly created User model.
    """
    cleaned_username = username.strip()
    if not cleaned_username:
        raise ValueError("Username cannot be empty.")

    if isinstance(role, str):
        role_enum = UserRole.from_str(role)
    else:
        role_enum = role

    # Check if username is already taken
    existing_user = db.get_user_by_username(cleaned_username)
    if existing_user:
        raise ValueError(f"Username '{cleaned_username}' is already registered.")

    # Hash password with a fresh random salt
    pwd_hash, salt = hash_password(password)

    return db.create_user(
        username=cleaned_username,
        password_hash=pwd_hash,
        salt=salt,
        role=role_enum
    )


def authenticate_user(
    db: DatabaseManager,
    username: str,
    password: str
) -> User:
    """
    Authenticates a user against stored credentials.

    Args:
        db: The active DatabaseManager instance.
        username: Username to authenticate.
        password: Raw password.

    Returns:
        User model if authentication succeeds.

    Raises:
        AuthenticationError: If credentials are invalid or user not found.
    """
    cleaned_username = username.strip()
    user = db.get_user_by_username(cleaned_username)
    if not user:
        raise AuthenticationError("Invalid username or password.")

    if not verify_password(password, user.salt, user.password_hash):
        raise AuthenticationError("Invalid username or password.")

    return user


def verify_role(user: User, allowed_roles: List[Union[UserRole, str]]) -> bool:
    """
    Verifies if the given user has one of the required authorization roles.
    """
    normalized_roles = [
        r.value if isinstance(r, UserRole) else UserRole.from_str(r).value
        for r in allowed_roles
    ]
    return user.role.value in normalized_roles


def require_role(user: User, allowed_roles: List[Union[UserRole, str]]) -> None:
    """
    Enforces role-based access control (RBAC).

    Raises:
        AuthorizationError: If user role is not permitted.
    """
    if not verify_role(user, allowed_roles):
        allowed_names = [r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles]
        raise AuthorizationError(
            f"Access denied: User '{user.username}' has role '{user.role.value}', "
            f"which is not authorized. Required: {allowed_names}"
        )


# =========================================================================
# Patient & Clinical Record Integrity (HMAC Tamper-Proofing)
# =========================================================================

def generate_record_checksum(payload: str, secret_key: str = INTEGRITY_SECRET) -> str:
    """
    Generates an HMAC-SHA256 cryptographic signature for a clinical payload
    to guarantee tamper-evident data integrity.
    """
    return hmac.new(
        secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def verify_record_checksum(payload: str, checksum: str, secret_key: str = INTEGRITY_SECRET) -> bool:
    """
    Validates an HMAC-SHA256 signature against the clinical payload.
    """
    expected = generate_record_checksum(payload, secret_key)
    return hmac.compare_digest(expected, checksum)
