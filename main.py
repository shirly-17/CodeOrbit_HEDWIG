import customtkinter as ctk
import pyttsx3
import threading
import queue

from tkinter import filedialog, messagebox

from voice.google_listen import listen_loop
from database.history import (
    initialize_database, save_history, get_history, clear_history
)
from security.voicelock import (
    setup_phrase, is_configured, save_protected_folder
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG = "#151515"
CARD = "#222222"
GOLD = "#D6B46A"
CREAM = "#F2E6C9"
MUTED = "#A99B80"

initialize_database()
ui_queue = queue.Queue()
stop_event = threading.Event()
listen_thread = None
startup_complete = False

app = ctk.CTk()
app.title("HEDWIG - Personal Voice Assistant")
app.geometry("1000x800")
app.minsize(650, 600)
app.configure(fg_color=BG)

content = ctk.CTkScrollableFrame(
    app, fg_color=BG,
    scrollbar_button_color="#725C35",
    scrollbar_button_hover_color="#947747"
)
content.pack(fill="both", expand=True, padx=5, pady=5)


def ask_value(title, prompt):
    result = {"value": None}
    dialog = ctk.CTkToplevel(app)
    dialog.title(title)
    dialog.geometry("440x230")
    dialog.configure(fg_color=BG)
    dialog.transient(app)
    dialog.grab_set()
    dialog.resizable(False, False)

    ctk.CTkLabel(
        dialog, text=title.upper(),
        font=("Georgia", 19, "bold"), text_color=GOLD
    ).pack(pady=(20, 10))
    ctk.CTkLabel(
        dialog, text=prompt, font=("Arial", 13),
        text_color=CREAM, wraplength=390
    ).pack(pady=5)

    entry = ctk.CTkEntry(dialog, width=350, height=38)
    entry.pack(pady=10)
    entry.focus()

    def submit():
        result["value"] = entry.get()
        dialog.destroy()

    def cancel():
        dialog.destroy()

    buttons = ctk.CTkFrame(dialog, fg_color="transparent")
    buttons.pack(pady=10)
    ctk.CTkButton(
        buttons, text="SUBMIT", command=submit,
        fg_color="#725C35", hover_color="#947747", width=120
    ).grid(row=0, column=0, padx=8)
    ctk.CTkButton(
        buttons, text="CANCEL", command=cancel,
        fg_color="#444444", hover_color="#606060", width=120
    ).grid(row=0, column=1, padx=8)

    dialog.bind("<Return>", lambda event: submit())
    dialog.bind("<Escape>", lambda event: cancel())
    app.wait_window(dialog)
    return result["value"]


ctk.CTkLabel(
    content, text="H E D W I G",
    font=("Georgia", 32, "bold"), text_color=GOLD
).pack(pady=(20, 5))
ctk.CTkLabel(
    content, text="YOUR PERSONAL VOICE ASSISTANT",
    font=("Arial", 11), text_color=MUTED
).pack(pady=(0, 20))

status_card = ctk.CTkFrame(content, fg_color=CARD, corner_radius=15)
status_card.pack(fill="x", padx=30, pady=10)
status_label = ctk.CTkLabel(
    status_card, text="HEDWIG IS STARTING...",
    font=("Arial", 16, "bold"), text_color=GOLD
)
status_label.pack(pady=18)

ctk.CTkLabel(
    content, text="YOU SAID:", font=("Arial", 13, "bold"),
    text_color=GOLD
).pack(anchor="w", padx=40, pady=(15, 5))
command_display = ctk.CTkLabel(
    content, text="Waiting for your command...",
    font=("Arial", 15), text_color=CREAM
)
command_display.pack(anchor="w", padx=40)

ctk.CTkLabel(
    content, text="HEDWIG:", font=("Arial", 13, "bold"),
    text_color=GOLD
).pack(anchor="w", padx=40, pady=(20, 5))
response_display = ctk.CTkLabel(
    content, text="Hello! I am Hedwig.",
    font=("Arial", 15), text_color=CREAM,
    wraplength=850, justify="left"
)
response_display.pack(anchor="w", padx=40)

ctk.CTkLabel(
    content, text="HEDWIG SESSION HISTORY",
    font=("Arial", 14, "bold"), text_color=GOLD
).pack(anchor="w", padx=40, pady=(25, 8))
history_box = ctk.CTkTextbox(
    content, height=150, fg_color=CARD, text_color=CREAM,
    font=("Consolas", 12), corner_radius=10
)
history_box.pack(fill="x", padx=30, pady=5)


def add_history(role, message):
    history_box.configure(state="normal")
    history_box.insert("end", f"{role}: {message}\n")
    history_box.see("end")
    history_box.configure(state="disabled")


def load_previous_history():
    history_box.configure(state="normal")
    for role, message, created_at in get_history():
        history_box.insert("end", f"{role}: {message}\n")
    history_box.see("end")
    history_box.configure(state="disabled")


def clear_command_history():
    clear_history()
    history_box.configure(state="normal")
    history_box.delete("1.0", "end")
    history_box.configure(state="disabled")


def set_security_phrase():
    phrase = ask_value(
        "CREATE SECURITY PHRASE",
        "Create a phrase with at least 6 characters:"
    )
    if phrase is None:
        return

    normalized = " ".join(phrase.lower().strip().split())
    if len(normalized) < 6:
        messagebox.showerror(
            "VOICELOCK", "Your phrase must contain at least 6 characters."
        )
        return

    confirmation = ask_value(
        "CONFIRM SECURITY PHRASE", "Enter your phrase again:"
    )
    if confirmation is None:
        return

    if normalized != " ".join(confirmation.lower().strip().split()):
        messagebox.showerror("VOICELOCK", "The security phrases do not match.")
        return

    if setup_phrase(phrase):
        messagebox.showinfo(
            "VOICELOCK", "Your security phrase has been saved successfully."
        )
    else:
        messagebox.showerror("VOICELOCK", "Unable to save your security phrase.")



def choose_protected_folder():
    if not is_configured():
        messagebox.showwarning(
            "VOICELOCK",
            "Please create your security phrase first."
        )
        return

    folder = filedialog.askdirectory(
        title="Select Your Confidential Folder"
    )

    if not folder:
        return

    confirm = messagebox.askyesno(
        "PROTECT PRIVATE FOLDER",
        "HEDWIG will encrypt this folder and remove its "
        "readable original after verification.\n\n"
        "Please ensure you have a separate backup first.\n\n"
        "Do you want to continue?"
    )

    if not confirm:
        return

    try:
        if not save_protected_folder(folder):
            raise RuntimeError("Unable to save the selected folder.")

        from security.vault_manager import setup_private_vault

        phrase = ask_value(
            "VOICELOCK AUTHENTICATION",
            "Enter your existing VoiceLock phrase to protect this folder:"
        )

        if phrase is None:
            return

        result = setup_private_vault(phrase)

        messagebox.showinfo("HEDWIG SECURITY", result)

    except Exception as error:
        messagebox.showerror(
            "HEDWIG SECURITY",
            f"Unable to protect this folder:\n\n{error}"
        )


def start_listening():
    global listen_thread
    if listen_thread and listen_thread.is_alive():
        return

    stop_event.clear()
    listen_thread = threading.Thread(
        target=listen_loop, args=(stop_event, ui_queue), daemon=True
    )
    listen_thread.start()
    start_button.configure(state="disabled")
    stop_button.configure(state="normal")


def stop_listening():
    stop_event.set()
    status_label.configure(text="STOPPING HEDWIG...", text_color=GOLD)
    start_button.configure(state="disabled")
    stop_button.configure(state="disabled")


def startup_greeting():
    engine = None
    try:
        engine = pyttsx3.init("sapi5")
        engine.setProperty("rate", 165)
        engine.setProperty("volume", 1.0)
        engine.say("Hello! Hedwig here. How's your day going?")
        engine.runAndWait()
    except Exception as error:
        print("Greeting error:", error)
    finally:
        if engine:
            engine.stop()
        ui_queue.put(("startup_done", ""))


def update_gui():
    global startup_complete
    while not ui_queue.empty():
        event, message = ui_queue.get()

        if event == "status":
            status_label.configure(text=message)
        elif event == "command":
            command_display.configure(text=message)
            save_history("You", message)
            add_history("You", message)
        elif event == "response":
            response_display.configure(text=message)
            save_history("Hedwig", message)
            add_history("Hedwig", message)
        elif event == "startup_done":
            startup_complete = True
            status_label.configure(text="HEDWIG IS READY", text_color=GOLD)
            start_button.configure(state="normal")

    if startup_complete and listen_thread is not None and not listen_thread.is_alive():
        start_button.configure(state="normal")
        stop_button.configure(state="disabled")

    app.after(100, update_gui)


button_frame = ctk.CTkFrame(content, fg_color="transparent")
button_frame.pack(pady=15)

start_button = ctk.CTkButton(
    button_frame, text="START LISTENING", command=start_listening,
    fg_color="#725C35", hover_color="#947747",
    width=160, height=40, state="disabled"
)
start_button.grid(row=0, column=0, padx=8, pady=7)

stop_button = ctk.CTkButton(
    button_frame, text="STOP LISTENING", command=stop_listening,
    fg_color="#713B3B", hover_color="#914D4D",
    width=160, height=40, state="disabled"
)
stop_button.grid(row=0, column=1, padx=8, pady=7)

clear_button = ctk.CTkButton(
    button_frame, text="CLEAR HISTORY", command=clear_command_history,
    fg_color="#444444", hover_color="#606060", width=160, height=40
)
clear_button.grid(row=0, column=2, padx=8, pady=7)

security_button = ctk.CTkButton(
    button_frame, text="SET SECURITY PHRASE", command=set_security_phrase,
    fg_color="#725C35", hover_color="#947747", width=190, height=40
)
security_button.grid(row=1, column=0, padx=8, pady=7)

folder_button = ctk.CTkButton(
    button_frame, text="SELECT PRIVATE FOLDER", command=choose_protected_folder,
    fg_color="#444444", hover_color="#606060", width=190, height=40
)
folder_button.grid(row=1, column=1, padx=8, pady=7)


def close_app():
    stop_event.set()
    app.destroy()


load_previous_history()
threading.Thread(target=startup_greeting, daemon=True).start()
app.after(100, update_gui)
app.protocol("WM_DELETE_WINDOW", close_app)
app.mainloop()
