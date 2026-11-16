
import io
import os
import json
import shutil
import zipfile
import hashlib
import tempfile

from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


# HEDWIG encrypted vault format
MAGIC = b"HEDWIGVAULT1"
SALT_SIZE = 16
NONCE_SIZE = 12
KEY_ITERATIONS = 600_000


def _derive_key(passphrase, salt):
    """Derive a 256-bit encryption key from the spoken phrase."""

    if not isinstance(passphrase, str) or not passphrase:
        raise ValueError("Security phrase cannot be empty.")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KEY_ITERATIONS
    )

    return kdf.derive(passphrase.encode("utf-8"))


def _make_archive(folder_path):
    """Create an in-memory ZIP archive of a folder."""

    folder = Path(folder_path).resolve()

    if not folder.is_dir():
        raise ValueError("Selected folder does not exist.")

    archive_buffer = io.BytesIO()

    with zipfile.ZipFile(
        archive_buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED
    ) as archive:

        for current_root, directories, filenames in os.walk(folder):

            current = Path(current_root)

            # Do not follow symbolic links.
            for directory in list(directories):
                item = current / directory

                if item.is_symlink():
                    raise ValueError(
                        f"Symbolic links are not supported: {item}"
                    )

            for filename in filenames:
                file_path = current / filename

                if file_path.is_symlink():
                    raise ValueError(
                        f"Symbolic links are not supported: {file_path}"
                    )

                relative_path = file_path.relative_to(folder)
                archive_name = relative_path.as_posix()

                archive.write(file_path, archive_name)

    return archive_buffer.getvalue()


def _encrypt_archive(archive_data, passphrase):
    """Encrypt archive bytes using AES-256-GCM."""

    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)

    key = _derive_key(passphrase, salt)

    encrypted_data = AESGCM(key).encrypt(
        nonce,
        archive_data,
        MAGIC
    )

    return MAGIC + salt + nonce + encrypted_data


def _decrypt_vault(vault_path, passphrase):
    """Read and authenticate an encrypted vault."""

    vault_path = Path(vault_path)

    if not vault_path.is_file():
        raise FileNotFoundError("Encrypted vault was not found.")

    data = vault_path.read_bytes()

    minimum_size = len(MAGIC) + SALT_SIZE + NONCE_SIZE + 16

    if len(data) < minimum_size or not data.startswith(MAGIC):
        raise ValueError("This is not a valid HEDWIG vault.")

    offset = len(MAGIC)

    salt = data[offset:offset + SALT_SIZE]
    offset += SALT_SIZE

    nonce = data[offset:offset + NONCE_SIZE]
    offset += NONCE_SIZE

    encrypted_data = data[offset:]

    key = _derive_key(passphrase, salt)

    # A wrong phrase or modified vault raises an authentication error.
    return AESGCM(key).decrypt(
        nonce,
        encrypted_data,
        MAGIC
    )


def _validate_archive(archive_data):
    """Check archive integrity before extracting or accepting it."""

    try:
        with zipfile.ZipFile(io.BytesIO(archive_data), "r") as archive:

            if archive.testzip() is not None:
                raise ValueError("Vault archive failed its integrity check.")

            for member in archive.infolist():
                path = PurePosixPath(member.filename)

                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Unsafe path found inside the vault.")

                if ":" in member.filename:
                    raise ValueError("Unsafe file path found inside the vault.")

    except zipfile.BadZipFile as error:
        raise ValueError("Vault contents are damaged.") from error


def create_vault(source_folder, vault_path, passphrase):
    """
    Create an encrypted copy.
    The original folder is NEVER deleted.
    """

    source = Path(source_folder).resolve()
    vault = Path(vault_path).resolve()

    if not source.is_dir():
        raise ValueError("Source folder does not exist.")

    if source == vault or source in vault.parents:
        raise ValueError("The vault must be outside the source folder.")

    if vault.exists():
        raise FileExistsError(
            "A vault already exists at this location. "
            "Choose another location instead of overwriting it."
        )

    vault.parent.mkdir(parents=True, exist_ok=True)

    archive_data = _make_archive(source)
    encrypted_data = _encrypt_archive(archive_data, passphrase)

    # Verify encryption and recovery before saving the vault.
    decrypted_data = _decrypt_bytes(encrypted_data, passphrase)
    _validate_archive(decrypted_data)

    if decrypted_data != archive_data:
        raise ValueError("Vault verification failed.")

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=vault.parent,
            prefix="hedwig_",
            suffix=".tmp",
            delete=False
        ) as temporary_file:

            temporary_path = Path(temporary_file.name)
            temporary_file.write(encrypted_data)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        # Publish only after successful verification.
        if vault.exists():
            raise FileExistsError("Vault destination already exists.")

        os.replace(temporary_path, vault)

    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()

    return str(vault)


def _decrypt_bytes(encrypted_data, passphrase):
    """Decrypt vault data held in memory."""

    if not encrypted_data.startswith(MAGIC):
        raise ValueError("Invalid HEDWIG vault format.")

    offset = len(MAGIC)

    salt = encrypted_data[offset:offset + SALT_SIZE]
    offset += SALT_SIZE

    nonce = encrypted_data[offset:offset + NONCE_SIZE]
    offset += NONCE_SIZE

    key = _derive_key(passphrase, salt)

    return AESGCM(key).decrypt(
        nonce,
        encrypted_data[offset:],
        MAGIC
    )


def verify_vault(vault_path, passphrase):
    """Verify that a vault can be decrypted and its archive is intact."""

    archive_data = _decrypt_vault(vault_path, passphrase)
    _validate_archive(archive_data)

    return True


def unlock_vault(vault_path, working_folder, passphrase):
    """
    Decrypt into a new working folder.
    Refuses to overwrite an existing folder.
    """

    destination = Path(working_folder).resolve()

    if destination.exists():
        raise FileExistsError(
            "The working folder already exists. "
            "It will not be overwritten."
        )

    archive_data = _decrypt_vault(vault_path, passphrase)
    _validate_archive(archive_data)

    destination.parent.mkdir(parents=True, exist_ok=True)

    staging = Path(
        tempfile.mkdtemp(
            prefix="hedwig_unlock_",
            dir=destination.parent
        )
    )

    try:
        with zipfile.ZipFile(io.BytesIO(archive_data), "r") as archive:

            for member in archive.infolist():

                relative_path = PurePosixPath(member.filename)

                if relative_path.is_absolute() or ".." in relative_path.parts:
                    raise ValueError("Unsafe path in vault.")

                target = staging.joinpath(*relative_path.parts).resolve()

                if staging.resolve() not in target.parents and target != staging.resolve():
                    raise ValueError("Unsafe extraction path.")

                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)

                    with archive.open(member, "r") as source:
                        with open(target, "wb") as output:
                            shutil.copyfileobj(source, output)

        # Publish the recovered folder only after extraction succeeds.
        if destination.exists():
            raise FileExistsError("Working folder already exists.")

        os.replace(staging, destination)

    finally:
        if staging.exists():
            shutil.rmtree(staging)

    return str(destination)


def lock_vault(working_folder, vault_path, passphrase):
    """
    Encrypt the working folder and verify the new vault.
    Removes the working folder only after successful verification.
    """

    working = Path(working_folder).resolve()
    vault = Path(vault_path).resolve()

    if not working.is_dir():
        raise FileNotFoundError("Working folder was not found.")

    if vault.exists():
        raise FileExistsError(
            "Vault already exists. It will not be overwritten."
        )

    archive_data = _make_archive(working)
    encrypted_data = _encrypt_archive(archive_data, passphrase)

    # Verify that the new vault decrypts to exactly the current files.
    recovered_data = _decrypt_bytes(encrypted_data, passphrase)
    _validate_archive(recovered_data)

    if recovered_data != archive_data:
        raise ValueError("Lock verification failed. Files were not removed.")

    vault.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=vault.parent,
            prefix="hedwig_",
            suffix=".tmp",
            delete=False
        ) as temporary_file:

            temporary_path = Path(temporary_file.name)
            temporary_file.write(encrypted_data)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, vault)

        # Verify the actual saved vault, not just the in-memory data.
        verify_vault(vault, passphrase)

    except Exception:
        if vault.exists():
            vault.unlink()
        raise

    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()

    # This is ordinary deletion, not guaranteed secure erasure.
    shutil.rmtree(working)

    return str(vault)
