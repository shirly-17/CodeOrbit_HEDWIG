
import os
import json
import secrets
import hashlib
import hmac
import base64

SECURITY_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.join(SECURITY_DIR, "voicelock.json")
FOLDER_CONFIG = os.path.join(SECURITY_DIR, "protected_folder.json")

ITERATIONS = 310000


def normalize_phrase(phrase):
    return " ".join(phrase.lower().strip().split())


def is_configured():
    if not os.path.exists(CONFIG_FILE):
        return False

    try:
        with open(CONFIG_FILE, "r") as file:
            data = json.load(file)

        return "salt" in data and "password_hash" in data

    except (OSError, ValueError):
        return False


def setup_phrase(phrase):
    phrase = normalize_phrase(phrase)

    if len(phrase) < 6:
        return False

    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        phrase.encode("utf-8"),
        salt,
        ITERATIONS
    )

    data = {
        "salt": base64.b64encode(salt).decode("utf-8"),
        "password_hash": base64.b64encode(
            password_hash
        ).decode("utf-8")
    }

    os.makedirs(SECURITY_DIR, exist_ok=True)

    with open(CONFIG_FILE, "w") as file:
        json.dump(data, file, indent=4)

    return True


def verify_phrase(phrase):
    if not is_configured():
        return False

    try:
        with open(CONFIG_FILE, "r") as file:
            data = json.load(file)

        salt = base64.b64decode(data["salt"])
        stored_hash = base64.b64decode(data["password_hash"])

        entered_hash = hashlib.pbkdf2_hmac(
            "sha256",
            normalize_phrase(phrase).encode("utf-8"),
            salt,
            ITERATIONS
        )

        return hmac.compare_digest(
            stored_hash,
            entered_hash
        )

    except (OSError, KeyError, ValueError):
        return False


def save_protected_folder(folder):
    if not os.path.isdir(folder):
        return False

    os.makedirs(SECURITY_DIR, exist_ok=True)

    with open(FOLDER_CONFIG, "w") as file:
        json.dump({"folder": folder}, file, indent=4)

    return True


def get_protected_folder():
    if not os.path.exists(FOLDER_CONFIG):
        return None

    try:
        with open(FOLDER_CONFIG, "r") as file:
            data = json.load(file)

        folder = data.get("folder")

        if folder and os.path.isdir(folder):
            return folder

    except (OSError, ValueError):
        pass

    return None
