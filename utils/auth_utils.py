from pydantic import BaseModel, EmailStr
import re

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    username: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str    

def validate_password(password: str) -> tuple[bool, str]:
    """
    Validates a password based on security rules:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Returns:
        (True, "Valid password") if all checks pass
        (False, "Reason for failure") if a rule fails
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one digit."

    if not re.search(r"[@$!%*?&]", password):
        return False, "Password must contain at least one special character (@, $, !, %, *, ?, &)."

    return True, "Valid password"

def validate_uid(uid: str) -> bool:
    """
    Validates the UID to ensure it is a non-empty string.

    Args:
        uid (str): The UID to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not uid or not isinstance(uid, str):
        return False
    return True