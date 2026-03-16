import uuid

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_pin_hash,
    verify_access_token,
    verify_pin,
    verify_refresh_token,
)


def test_pin_hashing_and_verification():
    """
    Test of een PIN correct gehasht wordt en succesvol (en onsuccesvol)
    geverifieerd kan worden.
    """
    plain_pin = "123456"  # Een geldige 6-cijferige PIN

    # 1. Hash de PIN
    hashed_pin = get_pin_hash(plain_pin)

    # Zorg dat de hash niet gelijk is aan de plain-text
    assert hashed_pin != plain_pin
    assert "123456" not in hashed_pin

    # 2. Verifieer met de JUISTE PIN
    assert verify_pin(plain_pin, hashed_pin) is True

    # 3. Verifieer met een FOUTE PIN
    assert verify_pin("654321", hashed_pin) is False
    assert verify_pin("12345", hashed_pin) is False


def test_access_token_not_accepted_as_refresh():
    user_id = uuid.uuid4()
    access_token = create_access_token(user_id=user_id, role="Admin")

    with pytest.raises(ValueError, match=r"Invalid token\."):
        verify_refresh_token(access_token)


def test_refresh_token_not_accepted_as_access():
    user_id = uuid.uuid4()
    refresh_token = create_refresh_token(user_id=user_id)

    with pytest.raises(ValueError, match=r"Invalid token\."):
        verify_access_token(refresh_token)


def test_token_type_validation_success():
    user_id = uuid.uuid4()
    role = "Admin"

    access_token = create_access_token(user_id=user_id, role=role)
    refresh_token = create_refresh_token(user_id=user_id)

    access_payload = verify_access_token(access_token)
    refresh_payload = verify_refresh_token(refresh_token)

    assert access_payload.sub == user_id
    assert access_payload.role == role
    assert refresh_payload.sub == user_id
