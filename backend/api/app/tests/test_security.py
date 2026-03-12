from app.core.security import get_pin_hash, verify_pin


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
