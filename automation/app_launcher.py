import os
import re
import csv
import io
import subprocess
import difflib
from pathlib import Path

SKIP_FOLDERS = {
    "appdata", "windows", "program files", "program files (x86)",
    "programdata", "node_modules", "venv", "__pycache__",
    ".git", ".vscode"
}


def normalize_name(name):
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9 ]", "", name)
    return re.sub(r"\s+", " ", name)


def get_start_menu_folders():
    folders = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
    ]
    return [folder for folder in folders if folder.exists()]


def discover_applications():
    applications = {}
    for folder in get_start_menu_folders():
        for root, directories, files in os.walk(folder):
            for filename in files:
                if filename.lower().endswith((".lnk", ".url")):
                    applications[Path(filename).stem.lower()] = os.path.join(root, filename)

    try:
        import winreg
        registry_locations = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths")
        ]
        for hive, location in registry_locations:
            try:
                root_key = winreg.OpenKey(hive, location)
            except OSError:
                continue
            try:
                index = 0
                while True:
                    try:
                        name = winreg.EnumKey(root_key, index)
                        index += 1
                        with winreg.OpenKey(root_key, name) as app_key:
                            executable, _ = winreg.QueryValueEx(app_key, None)
                        if executable and os.path.exists(executable):
                            applications[Path(name).stem.lower()] = executable
                    except OSError:
                        break
            finally:
                winreg.CloseKey(root_key)
    except ImportError:
        pass

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-StartApps | Select-Object Name,AppID | ConvertTo-Csv -NoTypeInformation"],
            capture_output=True, text=True, timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if result.returncode == 0 and result.stdout.strip():
            for row in csv.DictReader(io.StringIO(result.stdout)):
                name = (row.get("Name") or "").strip()
                app_id = (row.get("AppID") or "").strip()
                if name and app_id:
                    applications[name.lower()] = "APPID:" + app_id
    except Exception as error:
        print("Packaged app discovery:", error)

    return applications


def find_application(requested_name):
    requested_name = normalize_name(requested_name)
    if not requested_name:
        return None

    applications = discover_applications()
    normalized_apps = {normalize_name(name): path for name, path in applications.items()}

    if requested_name in normalized_apps:
        return normalized_apps[requested_name]

    aliases = {
        "whatsapp": ["whatsapp", "whatsapp desktop"],
        "vs code": ["visual studio code", "vs code"],
        "edge": ["microsoft edge", "edge"],
        "word": ["microsoft word", "word"],
        "excel": ["microsoft excel", "excel"],
        "powerpoint": ["microsoft powerpoint", "powerpoint"]
    }
    for alias in aliases.get(requested_name, []):
        if normalize_name(alias) in normalized_apps:
            return normalized_apps[normalize_name(alias)]

    matches = difflib.get_close_matches(
        requested_name, normalized_apps.keys(), n=1, cutoff=0.68
    )
    if matches:
        return normalized_apps[matches[0]]

    for name, path in normalized_apps.items():
        if len(requested_name) >= 4 and (requested_name in name or name in requested_name):
            return path
    return None


def open_application(requested_name):
    path = find_application(requested_name)
    if not path:
        return False
    if path.startswith("APPID:"):
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + path[6:]])
    else:
        os.startfile(path)
    return True


def get_folder_search_roots():
    home = Path.home()
    roots = [
        home, home / "Desktop", home / "Documents", home / "Downloads",
        home / "Pictures", home / "Videos", home / "Music", home / "OneDrive"
    ]
    return list(dict.fromkeys(path for path in roots if path.exists()))


def find_folder(requested_name):
    requested_name = normalize_name(requested_name)
    if not requested_name:
        return None
    if requested_name in ["home", "my folder", "personal folder"]:
        return str(Path.home())

    found = []
    for root in get_folder_search_roots():
        for current, directories, _files in os.walk(root):
            relative = Path(current).relative_to(root)
            depth = len(relative.parts)
            directories[:] = [
                d for d in directories
                if d.lower() not in SKIP_FOLDERS and not d.startswith(".")
            ]
            if depth >= 5:
                directories[:] = []

            for directory in directories:
                folder_path = Path(current) / directory
                normalized = normalize_name(directory)
                if normalized == requested_name:
                    return str(folder_path)
                found.append((normalized, str(folder_path)))

    names = [item[0] for item in found]
    matches = difflib.get_close_matches(requested_name, names, n=1, cutoff=0.78)
    if matches:
        for name, path in found:
            if name == matches[0]:
                return path
    return None


def open_folder(requested_name):
    path = find_folder(requested_name)
    if not path:
        return False
    os.startfile(path)
    return True
