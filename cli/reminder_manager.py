
import json
import os
from datetime import datetime

# File used to store reminders
DATA_FILE = os.path.join(os.path.dirname(__file__), "reminders.json")


def load_reminders():
    """Load saved reminders from the JSON file."""
    if not os.path.exists(DATA_FILE):
        return []

    try:
        with open(DATA_FILE, "r") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return []


def save_reminders(reminders):
    """Save reminders to the JSON file."""
    with open(DATA_FILE, "w") as file:
        json.dump(reminders, file, indent=4)


def add_reminder(reminders):
    """Add a reminder with a valid future date and time."""
    description = input("Enter reminder: ").strip()

    if not description:
        print("Reminder cannot be empty.")
        return

    date_text = input("Enter date (DD-MM-YYYY): ").strip()
    time_text = input("Enter time (HH:MM, 24-hour format): ").strip()

    try:
        reminder_time = datetime.strptime(
            date_text + " " + time_text,
            "%d-%m-%Y %H:%M"
        )

        if reminder_time <= datetime.now():
            print("Please enter a future date and time.")
            return

    except ValueError:
        print("Invalid date or time. Please try again.")
        return

    reminder = {
        "id": max((item["id"] for item in reminders), default=0) + 1,
        "description": description,
        "date": date_text,
        "time": time_text,
        "completed": False
    }

    reminders.append(reminder)
    save_reminders(reminders)

    print("Reminder added successfully!")


def view_reminders(reminders):
    """Display all saved reminders."""
    if not reminders:
        print("\nNo reminders found.")
        return

    print("\n===== YOUR REMINDERS =====")

    for item in reminders:
        print(
            f"\nID: {item['id']}"
            f"\nReminder: {item['description']}"
            f"\nDate: {item['date']}"
            f"\nTime: {item['time']}"
        )


def delete_reminder(reminders):
    """Delete a reminder using its ID."""
    view_reminders(reminders)

    if not reminders:
        return

    try:
        reminder_id = int(input("\nEnter reminder ID to delete: "))

        for item in reminders:
            if item["id"] == reminder_id:
                reminders.remove(item)
                save_reminders(reminders)
                print("Reminder deleted successfully!")
                return

        print("Reminder ID not found.")

    except ValueError:
        print("Please enter a valid numeric ID.")


def main():
    """Run the menu-driven HEDWIG CLI application."""
    reminders = load_reminders()

    while True:
        print("\n========== HEDWIG CLI ==========")
        print("1. Add Reminder")
        print("2. View Reminders")
        print("3. Delete Reminder")
        print("4. Exit")

        choice = input("\nEnter your choice: ").strip()

        if choice == "1":
            add_reminder(reminders)

        elif choice == "2":
            view_reminders(reminders)

        elif choice == "3":
            delete_reminder(reminders)

        elif choice == "4":
            print("Thank you for using HEDWIG CLI!")
            break

        else:
            print("Invalid choice. Please select 1 to 4.")


if __name__ == "__main__":
    main()
