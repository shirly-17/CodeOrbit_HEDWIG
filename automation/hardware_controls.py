import subprocess
import ctypes


def set_brightness(level):
    import screen_brightness_control as sbc
    level = max(0, min(100, int(level)))
    sbc.set_brightness(level)
    return f"Brightness set to {level}%."


def change_brightness(amount):
    import screen_brightness_control as sbc
    current = sbc.get_brightness()
    if isinstance(current, list):
        current = current[0]
    return set_brightness(int(current) + int(amount))


def get_volume_interface():
    from pycaw.pycaw import AudioUtilities
    speakers = AudioUtilities.GetSpeakers()
    return speakers.EndpointVolume


def set_volume(level):
    level = max(0, min(100, int(level)))
    endpoint = get_volume_interface()
    endpoint.SetMasterVolumeLevelScalar(level / 100.0, None)
    return f"Volume set to {level}%."


def change_volume(amount):
    endpoint = get_volume_interface()
    current = int(round(endpoint.GetMasterVolumeLevelScalar() * 100))
    return set_volume(current + int(amount))


def mute_audio(muted=True):
    endpoint = get_volume_interface()
    endpoint.SetMute(1 if muted else 0, None)
    return "Volume muted." if muted else "Volume unmuted."


def set_wifi(enabled):
    result = subprocess.run(
        ["netsh", "interface", "show", "interface"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )
    candidates = []
    for line in result.stdout.splitlines():
        lower = line.lower()
        if ("wi-fi" in lower or "wifi" in lower or "wireless" in lower):
            parts = line.split()
            if len(parts) >= 4:
                name = " ".join(parts[3:])
                candidates.append(name)

    if not candidates:
        raise RuntimeError("I couldn't identify your Wi-Fi network adapter.")

    adapter = candidates[0]
    state = "enabled" if enabled else "disabled"
    change = subprocess.run(
        ["netsh", "interface", "set", "interface",
         f"name={adapter}", f"admin={state}"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )
    if change.returncode != 0:
        detail = (change.stderr or change.stdout or "").strip()
        raise RuntimeError(
            "Windows could not change the Wi-Fi adapter. "
            "You may need to run HEDWIG as administrator. " + detail
        )
    return "Wi-Fi turned on." if enabled else "Wi-Fi turned off."


def sleep_computer():
    # Requests Windows suspend/sleep. Save your work before using this command.
    result = ctypes.windll.powrprof.SetSuspendState(False, True, False)
    if result == 0:
        raise RuntimeError("Windows could not put the computer to sleep.")
    return "Putting your computer to sleep."
