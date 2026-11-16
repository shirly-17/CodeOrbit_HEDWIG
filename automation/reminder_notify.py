import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.reminders import get_reminder, mark_reminder_done


def notify(message):
    spoken = False
    try:
        import pyttsx3
        engine = pyttsx3.init("sapi5")
        engine.setProperty("rate", 150)
        engine.say("Reminder. " + message)
        engine.runAndWait()
        engine.stop()
        spoken = True
    except Exception as error:
        print("Reminder speech error:", error)

    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo("HEDWIG REMINDER", message, parent=root)
        root.destroy()
    except Exception as error:
        print("Reminder popup error:", error)
        if not spoken:
            print("HEDWIG REMINDER:", message)


def main():
    if len(sys.argv) < 2:
        return
    try:
        reminder_id = int(sys.argv[1])
    except ValueError:
        return

    reminder = get_reminder(reminder_id)
    if not reminder or reminder[3] != "pending":
        return

    mark_reminder_done(reminder_id)
    notify(reminder[1])


if __name__ == "__main__":
    main()
