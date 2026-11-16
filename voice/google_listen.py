import sounddevice as sd
import speech_recognition as sr
import webbrowser
import pyttsx3
import os
import re
import queue
import threading

from datetime import datetime, timedelta
from urllib.parse import quote_plus

from security.voicelock import (
    verify_phrase, is_configured
)

from security.vault_manager import (
    setup_private_vault,
    unlock_private_vault,
    lock_private_vault,
    get_vault_status
)

from automation.app_launcher import (
    find_application, open_application, find_folder, open_folder
)
from database.reminders import (
    create_reminder, delete_reminder, list_pending_reminders,
    remove_reminder_record
)
from automation.reminder_scheduler import (
    schedule_reminder, cancel_scheduled_reminder
)
from automation import hardware_controls as hardware

MICROPHONE_ID = 1
SAMPLE_RATE = 16000
DURATION = 7


def voice_worker(speech_queue):
    pythoncom_module = None
    try:
        import pythoncom as pythoncom_module
        pythoncom_module.CoInitialize()
    except ImportError:
        pythoncom_module = None

    try:
        while True:
            message = speech_queue.get()
            engine = None
            try:
                if message is None:
                    break
                engine = pyttsx3.init("sapi5")
                engine.setProperty("rate", 145)
                engine.setProperty("volume", 1.0)
                engine.say(message)
                engine.runAndWait()
            except Exception as error:
                print("Speech error:", error)
            finally:
                if engine:
                    engine.stop()
                    del engine
                speech_queue.task_done()
    finally:
        if pythoncom_module:
            pythoncom_module.CoUninitialize()


def normalize_command(command):
    command = command.lower().strip()
    command = command.replace("-", " ")
    command = re.sub(r"[.!?,]+$", "", command)
    return re.sub(r"\s+", " ", command)


def parse_reminder_time(text):
    now = datetime.now()
    text = text.strip().lower()

    relative = re.fullmatch(
        r"in\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?)", text
    )
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        if amount < 1:
            raise ValueError("Please choose a reminder time of at least one minute.")
        if unit.startswith(("minute", "min")):
            due = now + timedelta(minutes=amount)
        elif unit.startswith(("hour", "hr")):
            due = now + timedelta(hours=amount)
        else:
            due = now + timedelta(days=amount)
        return due.replace(second=0, microsecond=0)

    tomorrow = text.startswith("tomorrow at ")
    today = text.startswith("today at ")
    if tomorrow or today:
        clock_text = text.split(" at ", 1)[1]
        base_date = (now + timedelta(days=1)).date() if tomorrow else now.date()
    elif text.startswith("at "):
        clock_text = text[3:]
        base_date = now.date()
    else:
        raise ValueError(
            "Try 'in 10 minutes', 'in 2 hours', or 'tomorrow at 9 AM'."
        )

    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", clock_text)
    if not match:
        raise ValueError("I couldn't read that time. Try 9 AM or 14:30.")

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = match.group(3)

    if minute > 59 or hour > 23 or (suffix and not 1 <= hour <= 12):
        raise ValueError("That time is not valid.")

    if suffix == "pm" and hour != 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0

    due = datetime.combine(base_date, datetime.min.time()).replace(
        hour=hour, minute=minute
    )
    if due <= now:
        if text.startswith("at "):
            due += timedelta(days=1)
        else:
            raise ValueError("That time has already passed.")
    return due


def handle_reminder_command(command):
    create_match = re.fullmatch(
        r"remind me (?:to )?(.+?) (in\s+\d+\s*(?:minutes?|mins?|hours?|hrs?|days?)|"
        r"tomorrow at .+|today at .+|at .+)",
        command
    )
    if create_match:
        message = create_match.group(1).strip()
        time_text = create_match.group(2).strip()
        if not message:
            return "What should I remind you about?"
        due = parse_reminder_time(time_text)
        reminder_id = create_reminder(message, due)
        try:
            schedule_reminder(reminder_id, due)
        except Exception:
            remove_reminder_record(reminder_id)
            raise
        return (
            f"Reminder {reminder_id} set for {due.strftime('%d %B at %I:%M %p')}. "
            "It will alert you while Windows is running and you are signed in."
        )

    if command in ["show reminders", "list reminders", "my reminders"]:
        reminders = list_pending_reminders()
        if not reminders:
            return "You have no pending reminders."
        lines = [
            f"Reminder {row[0]}: {row[1]} at "
            f"{datetime.fromisoformat(row[2]).strftime('%d %b, %I:%M %p')}"
            for row in reminders
        ]
        return "Your pending reminders are: " + ". ".join(lines)

    if command == "cancel all reminders":
        reminders = list_pending_reminders()
        cancelled = 0
        for row in reminders:
            cancel_scheduled_reminder(row[0])
            if delete_reminder(row[0]):
                cancelled += 1
        return f"Cancelled {cancelled} pending reminders."

    cancel_match = re.fullmatch(r"cancel reminder\s+(\d+)", command)
    if cancel_match:
        reminder_id = int(cancel_match.group(1))
        if delete_reminder(reminder_id):
            cancel_scheduled_reminder(reminder_id)
            return f"Reminder {reminder_id} cancelled."
        return f"I couldn't find pending reminder {reminder_id}."

    return None


def handle_hardware_command(command):
    match = re.fullmatch(r"(?:set )?brightness(?: to)?\s+(\d{1,3})\s*%?", command)
    if match:
        return hardware.set_brightness(int(match.group(1)))

    match = re.fullmatch(r"(?:set )?volume(?: to)?\s+(\d{1,3})\s*%?", command)
    if match:
        return hardware.set_volume(int(match.group(1)))

    if command in ["brightness up", "increase brightness", "increase the brightness"]:
        return hardware.change_brightness(10)
    if command in ["brightness down", "decrease brightness", "decrease the brightness"]:
        return hardware.change_brightness(-10)
    if command in ["volume up", "increase volume", "increase the volume"]:
        return hardware.change_volume(10)
    if command in ["volume down", "decrease volume", "decrease the volume"]:
        return hardware.change_volume(-10)
    if command in ["mute", "mute volume", "mute the volume"]:
        return hardware.mute_audio(True)
    if command in ["unmute", "unmute volume", "unmute the volume"]:
        return hardware.mute_audio(False)
    if command in ["turn wifi on", "turn wi fi on", "enable wifi", "enable wi fi"]:
        return hardware.set_wifi(True)
    if command in ["turn wifi off", "turn wi fi off", "disable wifi", "disable wi fi"]:
        return hardware.set_wifi(False)
    if command in [
        "sleep", "sleep laptop", "laptop sleep", "laptop to sleep",
        "put laptop to sleep", "put the laptop to sleep",
        "put my laptop to sleep", "sleep my laptop",
        "put computer to sleep", "put the computer to sleep",
        "the laptop to sleep"
    ]:
        return hardware.sleep_computer()
    return None


def handle_command(command):
    command = normalize_command(command)

    try:
        reminder_response = handle_reminder_command(command)
        if reminder_response is not None:
            return reminder_response
    except Exception as error:
        return f"I couldn't set that reminder. {error}"

    try:
        hardware_response = handle_hardware_command(command)
        if hardware_response is not None:
            return hardware_response
    except Exception as error:
        return f"I couldn't complete that hardware command. {error}"

    if "thank" in command or command == "thanks":
        response = "You're most welcome! I'm always happy to help."
    elif ("how are" in command or "how r u" in command or "how you doing" in command):
        response = "I'm doing wonderful! Thank you for asking. How are you?"
    elif any(x in command for x in [
        "i am fine", "im fine", "i'm fine", "i am good", "im good",
        "i'm good", "doing good", "doing well"
    ]):
        response = "That's lovely to hear! What can I do for you?"
    elif any(x in command for x in [
        "good morning", "good afternoon", "good evening", "good night"
    ]):
        response = "Hello! I hope you're having a wonderful day."
    elif "hello" in command or command == "hi" or "hi hedwig" in command:
        response = "Hello! It's lovely to talk to you. How can I help?"
    elif any(x in command for x in ["bye", "goodbye", "see you"]):
        response = "Goodbye! Take care and have a lovely day."
    elif "sorry" in command:
        response = "That's alright! No worries at all."
    elif (
        "what can" in command or "what do you do" in command
        or "your features" in command or "help me" in command
    ):
        response = (
            "I can open applications and personal folders, search Google and YouTube, "
            "tell you the date, day and time, manage reminders, control brightness, "
            "volume and Wi-Fi, put your laptop to sleep, and protect your confidential "
            "folder with VoiceLock."
        )
    elif "who are you" in command:
        response = "I'm Hedwig, your personal desktop voice assistant."
    elif "date" in command or "what is today" in command:
        response = "Today's date is " + datetime.now().strftime("%d %B %Y") + "."
    elif "what day" in command or "which day" in command or command == "day":
        response = "Today is " + datetime.now().strftime("%A") + "."
    elif "time" in command:
        response = "The time is " + datetime.now().strftime("%I:%M %p") + "."
    elif command in ["open downloads", "downloads"]:
        path = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.isdir(path):
            os.startfile(path)
            response = "Opening your Downloads folder."
        else:
            response = "I couldn't find your Downloads folder."
    elif "play" in command and "youtube" in command:
        search_text = command.replace("play", "", 1)
        search_text = search_text.replace("on youtube", "").replace("in youtube", "")
        search_text = search_text.replace("youtube", "").strip()
        if search_text:
            webbrowser.open(
                "https://www.youtube.com/results?search_query=" + quote_plus(search_text)
            )
            response = f"Searching YouTube for {search_text}."
        else:
            webbrowser.open("https://www.youtube.com")
            response = "Opening YouTube."
    elif command.startswith("search") or command.startswith("google"):
        search_text = re.sub(r"^(search for|search|google)\s*", "", command)
        search_text = re.sub(r"\s+(on|in)\s+google$", "", search_text).strip()
        if search_text:
            webbrowser.open(
                "https://www.google.com/search?q=" + quote_plus(search_text)
            )
            response = f"Searching Google for {search_text}."
        else:
            webbrowser.open("https://www.google.com")
            response = "Opening Google."
    elif command in ["open google", "google"]:
        webbrowser.open("https://www.google.com")
        response = "Opening Google."
    elif command in ["open youtube", "youtube"]:
        webbrowser.open("https://www.youtube.com")
        response = "Opening YouTube."
    else:
        response = open_requested_item(command)
    return response


def open_requested_item(command):
    match = re.match(r"^(?:please\s+)?open\s+(.+)$", command)
    if not match:
        return (
            "Sorry, I didn't understand that. You can ask me what I can do, "
            "or ask me to open an application or folder."
        )

    requested = match.group(1).strip()
    if requested in [
        "my private folder", "private folder", "my confidential folder",
        "confidential folder", "protected folder",
        "my secret folder", "secret folder"
    ]:
        return "Please use the VoiceLock command to access your private folder."

    if requested in ["my folder", "my personal folder", "home folder"]:
        try:
            os.startfile(os.path.expanduser("~"))
            return "Opening your personal folder."
        except Exception:
            return "I couldn't open your personal folder."

    folder_request = requested[:-7].strip() if requested.endswith(" folder") else requested
    if folder_request in ["desktop", "documents", "downloads", "pictures", "music", "videos"]:
        path = os.path.join(os.path.expanduser("~"), folder_request.capitalize())
        if os.path.isdir(path):
            os.startfile(path)
            return f"Opening your {folder_request} folder."

    if requested.endswith(" folder"):
        if open_folder(folder_request):
            return f"Opening your {folder_request} folder."
        return f"I couldn't find a folder named {folder_request}."

    application = find_application(requested)
    if application:
        try:
            open_application(requested)
            return f"Opening {requested}."
        except Exception as error:
            print("Application launch error:", error)
            return f"I couldn't open {requested}."

    if open_folder(requested):
        return f"Opening your {requested} folder."
    return f"I couldn't find an application or folder named {requested}."



def is_protected_folder_command(command):
    return command in [
        "open my private folder",
        "open private folder",
        "open my confidential folder",
        "open confidential folder",
        "open protected folder",
        "open my secret folder",
        "open secret folder"
    ]


def is_lock_private_folder_command(command):
    return command in [
        "lock my private folder",
        "lock private folder",
        "lock my confidential folder",
        "lock confidential folder",
        "lock protected folder",
        "lock my secret folder",
        "lock secret folder"
    ]


def is_private_folder_status_command(command):
    return command in [
        "check my secret folder status",
        "check secret folder status",
        "secret folder status",
        "is my secret folder locked",
        "is my secret folder unlocked"  
    ]
    
def is_create_private_vault_command(command):
    commands = (
        "create encrypted vault",
        "encrypt my private folder",
        "protect my private folder",
        "set up my private vault"
    )
    return command.strip().lower() in commands


def create_private_vault_by_voice(recognizer, speech_queue, ui_queue, stop_event):
    if get_vault_status() != "not_configured":
        return "A private vault is already configured or needs recovery."

    phrase, error = authenticate_voice_phrase(
        recognizer, speech_queue, ui_queue, stop_event
    )

    if error:
        return error

    try:
        return setup_private_vault(phrase)
    except Exception as exc:
        return f"I couldn't create the encrypted vault: {exc}"


def authenticate_voice_phrase(
    recognizer, speech_queue, ui_queue, stop_event
):
    if not is_configured():
        return None, "VoiceLock is not configured."

    ui_queue.put(("status", "VOICELOCK: AUTHENTICATION REQUIRED"))
    speech_queue.put("Please say your security phrase now.")
    speech_queue.join()

    if stop_event.is_set():
        return None, "VoiceLock authentication cancelled."

    try:
        ui_queue.put(("status", "VOICELOCK: LISTENING FOR PHRASE"))

        audio = sd.rec(
            int(DURATION * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=MICROPHONE_ID
        )
        sd.wait()

        if stop_event.is_set():
            return None, "VoiceLock authentication cancelled."

        audio_data = sr.AudioData(
            audio.tobytes(), SAMPLE_RATE, 2
        )

        ui_queue.put(("status", "VOICELOCK: VERIFYING PHRASE"))

        entered_phrase = recognizer.recognize_google(
            audio_data,
            language="en-IN"
        )

        if not verify_phrase(entered_phrase):
            ui_queue.put(("status", "VOICELOCK: ACCESS DENIED"))
            return None, "Incorrect security phrase. Access denied."

        ui_queue.put(("status", "VOICELOCK: ACCESS GRANTED"))
        return entered_phrase, None

    except sr.UnknownValueError:
        ui_queue.put(("status", "VOICELOCK: PHRASE NOT UNDERSTOOD"))
        return None, "I couldn't understand your security phrase. Access denied."

    except sr.RequestError:
        ui_queue.put(("status", "VOICELOCK: INTERNET ERROR"))
        return None, "I couldn't verify your phrase because of an internet error."

    except Exception as error:
        print("VoiceLock error:", error)
        ui_queue.put(("status", "VOICELOCK: ERROR"))
        return None, "An error occurred during authentication. Access denied."


def authenticate_and_open_folder(
    recognizer, speech_queue, ui_queue, stop_event
):
    try:
        status = get_vault_status()

        if status == "not_configured":
            return (
                "Your encrypted vault has not been set up yet. "
                "Your original folder remains unchanged."
            )

        if status == "recovery_required":
            return (
                "Your vault needs recovery. "
                "I will not open or modify it."
            )

        if status == "unlocked":
            return "Your private folder is already unlocked."

        phrase, error = authenticate_voice_phrase(
            recognizer, speech_queue, ui_queue, stop_event
        )

        if error:
            return error

        working_folder = unlock_private_vault(phrase)
        os.startfile(working_folder)

        ui_queue.put(("status", "PRIVATE FOLDER UNLOCKED"))
        return "Authentication successful. Your private folder is now unlocked."

    except Exception as error:
        print("Vault unlock error:", error)
        ui_queue.put(("status", "VAULT UNLOCK ERROR"))
        return f"I couldn't unlock your private folder. {error}"


def authenticate_and_lock_folder(
    recognizer, speech_queue, ui_queue, stop_event
):
    try:
        status = get_vault_status()

        if status == "not_configured":
            return "Your encrypted vault has not been set up yet."

        if status == "recovery_required":
            return "Your vault needs recovery. I cannot safely lock it."

        if status == "locked":
            return "Your private folder is already locked."

        phrase, error = authenticate_voice_phrase(
            recognizer, speech_queue, ui_queue, stop_event
        )

        if error:
            return error

        result = lock_private_vault(phrase)

        ui_queue.put(("status", "PRIVATE FOLDER LOCKED"))
        return result

    except Exception as error:
        print("Vault lock error:", error)
        ui_queue.put(("status", "VAULT LOCK ERROR"))
        return f"I couldn't lock your private folder. {error}"


def report_private_folder_status():
    try:
        status = get_vault_status()

        if status == "not_configured":
            return "Your encrypted private vault has not been set up."

        if status == "locked":
            return "Your private folder is locked."

        if status == "unlocked":
            return "Your private folder is currently unlocked."

        return "Your private folder needs recovery. Please check it manually."

    except Exception as error:
        print("Vault status error:", error)
        return "I couldn't check your private folder status."



def listen_loop(stop_event, ui_queue):
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.8
    recognizer.non_speaking_duration = 0.5
    recognizer.dynamic_energy_threshold = True

    speech_queue = queue.Queue()
    speaker_thread = threading.Thread(
        target=voice_worker,
        args=(speech_queue,),
        daemon=True
    )
    speaker_thread.start()
    ui_queue.put(("status", "HEDWIG IS READY"))

    try:
        while not stop_event.is_set():
            try:
                ui_queue.put(("status", "LISTENING..."))

                audio = sd.rec(
                    int(DURATION * SAMPLE_RATE),
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    device=MICROPHONE_ID
                )
                sd.wait()

                if stop_event.is_set():
                    break

                audio_data = sr.AudioData(
                    audio.tobytes(),
                    SAMPLE_RATE,
                    2
                )

                ui_queue.put(("status", "PROCESSING..."))

                command = normalize_command(
                    recognizer.recognize_google(
                        audio_data,
                        language="en-IN"
                    )
                )

                ui_queue.put(("command", command))

                if is_create_private_vault_command(command):
                    response = create_private_vault_by_voice(
                        recognizer,
                        speech_queue,
                        ui_queue,
                        stop_event
                    )

                elif is_protected_folder_command(command):
                    response = authenticate_and_open_folder(
                        recognizer,
                        speech_queue,
                        ui_queue,
                        stop_event
                    )

                elif is_lock_private_folder_command(command):
                    response = authenticate_and_lock_folder(
                        recognizer,
                        speech_queue,
                        ui_queue,
                        stop_event
                    )

                elif is_private_folder_status_command(command):
                    response = report_private_folder_status()

                else:
                    response = handle_command(command)

                ui_queue.put(("response", response))
                speech_queue.put(response)
                speech_queue.join()

            except sr.UnknownValueError:
                ui_queue.put(("status", "COULDN'T UNDERSTAND"))

            except sr.RequestError:
                ui_queue.put(("status", "INTERNET / RECOGNITION ERROR"))

            except Exception as error:
                print("Listening error:", error)
                ui_queue.put(("status", f"ERROR: {error}"))

    finally:
        speech_queue.put(None)
        speaker_thread.join(timeout=10)
        ui_queue.put(("status", "HEDWIG IS IDLE"))
