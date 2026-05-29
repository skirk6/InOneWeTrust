import hashlib


def generate_pbkdf2_hash(email: str, iterations: int = 10) -> str:
    """
    Generate a deterministic PBKDF2-HMAC-SHA256 hash from an email address.

    Salt is the SHA-256 digest of the lowercased email. Iteration count
    matches the existing Teradata database scheme and must not be changed
    without a full rehash of stored values.

    Args:
        email: Raw email address (case-insensitive).
        iterations: PBKDF2 iteration count; defaults to 10 to match DB scheme.

    Returns:
        Uppercase hex string of the 32-byte PBKDF2 digest.
    """
    email_lower = email.lower()
    salt = hashlib.sha256(email_lower.encode('utf-8')).digest()
    password = email_lower.encode('utf-8')
    hash_value = hashlib.pbkdf2_hmac('sha256', password, salt, iterations)
    return hash_value.hex().upper()


if __name__ == "__main__":
    import pandas as pd
    emails = ["test1@example.com", "test2@example.com", "test3@example.com"]
    rows = [
        {"EMAIL": email, "EMAIL_ENCRT_TXT": generate_pbkdf2_hash(email)}
        for email in emails
    ]
    df_pbkdf2 = pd.DataFrame(rows, columns=["EMAIL", "EMAIL_ENCRT_TXT"])
    print(df_pbkdf2)
