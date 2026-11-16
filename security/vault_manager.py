
import os
import json
import uuid
import shutil
from pathlib import Path

from security.voicelock import (
    verify_phrase,
    normalize_phrase,
    get_protected_folder
)

from security.encrypted_vault import (
    create_vault,
    verify_vault,
    unlock_vault as decrypt_vault
)


SECURITY_DIR = Path(__file__).resolve().parent
VAULT_CONFIG = SECURITY_DIR / "vault_config.json"


def _load_config():
    if not VAULT_CONFIG.exists():
        return {}

    try:
        with open(VAULT_CONFIG, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise RuntimeError("Invalid vault configuration.")

        return data

    except (OSError, ValueError):
        raise RuntimeError(
            "HEDWIG vault configuration is damaged."
        )


def _save_config(data):
    temporary = VAULT_CONFIG.with_name(
        VAULT_CONFIG.name + ".tmp"
    )

    try:
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary, VAULT_CONFIG)

    finally:
        if temporary.exists():
            temporary.unlink()


def _authenticate(phrase):
    phrase = normalize_phrase(phrase)

    if not verify_phrase(phrase):
        raise PermissionError(
            "VoiceLock authentication failed."
        )

    return phrase


def _get_working_folder(source_folder):
    local_app_data = os.environ.get("LOCALAPPDATA")

    if not local_app_data:
        raise RuntimeError(
            "Windows local application folder was not found."
        )

    return (
        Path(local_app_data)
        / "HEDWIG"
        / "Unlocked"
        / Path(source_folder).name
    )


def _get_paths(config):
    vault_value = config.get("vault_path")
    working_value = config.get("working_folder")

    if not vault_value or not working_value:
        raise RuntimeError(
            "Vault paths are missing from the configuration."
        )

    return Path(vault_value), Path(working_value)


def setup_private_vault(phrase):
    """Create, verify and migrate the original folder into encryption."""

    phrase = _authenticate(phrase)

    source_folder = get_protected_folder()

    if not source_folder:
        raise FileNotFoundError(
            "Please select an existing private folder first."
        )

    source = Path(source_folder).resolve()

    if not source.is_dir():
        raise FileNotFoundError(
            "The selected private folder does not exist."
        )

    config = _load_config()

    if config.get("vault_path"):
        raise FileExistsError(
            "A HEDWIG vault is already configured."
        )

    vault_path = source.parent / (source.name + ".hwvault")

    if vault_path.exists():
        raise FileExistsError(
            "A vault file already exists. It will not be overwritten."
        )

    working_folder = _get_working_folder(source)

    if working_folder.exists():
        raise FileExistsError(
            "A previous working folder exists. Check it first."
        )

    # Keep the original folder until encryption is verified.
    create_vault(source, vault_path, phrase)
    verify_vault(vault_path, phrase)

    # Rename the original folder to a temporary recovery location.
    recovery_folder = source.with_name(
        source.name + ".HEDWIG_RECOVERY_" + uuid.uuid4().hex
    )

    try:
        os.replace(source, recovery_folder)

        # Verify the encrypted vault again after migration.
        verify_vault(vault_path, phrase)

        _save_config({
            "source_folder": str(source),
            "vault_path": str(vault_path),
            "working_folder": str(working_folder),
            "unlocked": False,
            "state": "locked"
        })

    except Exception:
        # Restore the original folder if migration fails.
        if recovery_folder.exists() and not source.exists():
            os.replace(recovery_folder, source)

        if vault_path.exists():
            vault_path.unlink()

        raise

    # Delete the readable recovery copy only after verification.
    try:
        shutil.rmtree(recovery_folder)

    except OSError:
        return (
            "Encrypted vault created and verified, but the original "
            "recovery folder could not be deleted. It remains at: "
            + str(recovery_folder)
        )

    return (
        "Your private folder has been encrypted and the original "
        "readable folder has been removed."
    )

def unlock_private_vault(phrase):
    """Authenticate and decrypt the vault."""

    phrase = _authenticate(phrase)
    config = _load_config()

    vault_path, working_folder = _get_paths(config)

    if not vault_path.is_file():
        raise FileNotFoundError(
            "Encrypted vault was not found."
        )

    if working_folder.exists():
        raise FileExistsError(
            "A working folder already exists. "
            "HEDWIG will not overwrite it."
        )

    if config.get("unlocked"):
        raise RuntimeError(
            "The vault configuration says it is already unlocked. "
            "Check the vault status before continuing."
        )

    if config.get("state") not in ("locked", None):
        raise RuntimeError(
            "The vault needs recovery before it can be unlocked."
        )

    verify_vault(vault_path, phrase)

    decrypt_vault(
        vault_path,
        working_folder,
        phrase
    )

    config["unlocked"] = True
    config["state"] = "unlocked"
    _save_config(config)

    return str(working_folder)


def lock_private_vault(phrase):
    """
    Encrypt changes, verify the new vault, and then
    remove the unlocked working folder.

    The previous encrypted vault is retained as a
    backup until the new vault is safely installed.
    """

    phrase = _authenticate(phrase)
    config = _load_config()

    vault_path, working_folder = _get_paths(config)

    if not config.get("unlocked"):
        raise RuntimeError(
            "The private folder is already locked."
        )

    if not working_folder.is_dir():
        raise FileNotFoundError(
            "The unlocked working folder is missing. "
            "The existing vault has not been changed."
        )

    if not vault_path.is_file():
        raise FileNotFoundError(
            "The original encrypted vault is missing."
        )

    backup_vault = vault_path.with_name(
        vault_path.name
        + ".backup_"
        + uuid.uuid4().hex
    )

    temporary_vault = vault_path.with_name(
        vault_path.name
        + ".new_"
        + uuid.uuid4().hex
    )

    quarantine_folder = working_folder.with_name(
        working_folder.name
        + ".locking_"
        + uuid.uuid4().hex
    )

    backup_created = False
    new_vault_installed = False
    folder_quarantined = False

    try:
        # 1. Create a new encrypted copy without deleting
        #    the currently unlocked working folder.
        create_vault(
            working_folder,
            temporary_vault,
            phrase
        )

        # 2. Verify the new encrypted vault.
        verify_vault(temporary_vault, phrase)

        # 3. Preserve the old encrypted vault.
        os.replace(vault_path, backup_vault)
        backup_created = True

        # 4. Install the verified new vault.
        os.replace(temporary_vault, vault_path)
        new_vault_installed = True

        verify_vault(vault_path, phrase)

        # 5. Record that the new vault is ready.
        config["state"] = "ready_to_lock"
        _save_config(config)

        # 6. Rename the working folder first.
        #    This allows recovery if configuration saving fails.
        os.replace(working_folder, quarantine_folder)
        folder_quarantined = True

        config["unlocked"] = False
        config["state"] = "locked"
        _save_config(config)

    except Exception:
        # Restore the working folder if it was renamed.
        if folder_quarantined and quarantine_folder.exists():
            if not working_folder.exists():
                os.replace(
                    quarantine_folder,
                    working_folder
                )

        # Restore the previous encrypted vault if needed.
        if backup_created and backup_vault.exists():
            if new_vault_installed and vault_path.exists():
                failed_vault = vault_path.with_name(
                    vault_path.name
                    + ".failed_"
                    + uuid.uuid4().hex
                )

                os.replace(vault_path, failed_vault)

            os.replace(backup_vault, vault_path)

        raise

    finally:
        if temporary_vault.exists():
            temporary_vault.unlink()

    # 7. The new vault is installed and configuration
    #    says locked. Remove the quarantined plaintext copy.
    try:
        if quarantine_folder.exists():
            shutil.rmtree(quarantine_folder)

    except OSError:
        return (
            "The encrypted vault is ready, but a temporary "
            "plaintext folder could not be removed. "
            "Manual cleanup is required before considering "
            "the folder fully locked."
        )

    # 8. Remove the previous encrypted backup only after
    #    the new vault and locked state are confirmed.
    try:
        if backup_vault.exists():
            backup_vault.unlink()

    except OSError:
        return (
            "The private folder is locked successfully. "
            "An older encrypted backup remains on disk."
        )

    return "Private folder encrypted and locked successfully."


def get_vault_status():
    """Return the current vault status."""

    config = _load_config()

    if not config.get("vault_path"):
        return "not_configured"

    try:
        vault_path, working_folder = _get_paths(config)
    except RuntimeError:
        return "recovery_required"

    if not vault_path.is_file():
        return "recovery_required"

    if config.get("unlocked") and working_folder.is_dir():
        return "unlocked"

    if config.get("unlocked") and not working_folder.exists():
        return "recovery_required"

    if config.get("state") == "ready_to_lock":
        return "recovery_required"

    if config.get("state") == "locked":
        return "locked"

    if not config.get("unlocked") and not working_folder.exists():
        return "locked"

    return "recovery_required"
