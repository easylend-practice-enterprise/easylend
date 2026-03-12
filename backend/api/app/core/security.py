import bcrypt


def get_pin_hash(pin: str) -> str:
    """
    Zet een plain-text PIN om naar een veilige bcrypt hash.
    """
    # bcrypt verwacht bytes, dus we encoden de string
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pin.encode("utf-8"), salt)

    # We returnen een string omdat de database (PostgreSQL) dit als VARCHAR opslaat
    return hashed_bytes.decode("utf-8")


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """
    Verifieert of een plain-text PIN overeenkomt met de hash uit de database.
    """
    # Zowel de input als de hash uit de DB moeten omgezet worden naar bytes voor de check
    return bcrypt.checkpw(plain_pin.encode("utf-8"), hashed_pin.encode("utf-8"))
