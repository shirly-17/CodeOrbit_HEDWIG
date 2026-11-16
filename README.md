\# HEDWIG – Windows Voice Assistant



\*\*HEDWIG\*\* is a Python-based Windows desktop voice assistant designed to simplify everyday computer tasks through voice commands and a graphical interface.



Developed as part of the \*\*CodeOrbit Tech Software Development Internship – 2026\*\*.



\## Features



\- \*\*Voice Interaction:\*\* Recognizes voice commands using Google Speech Recognition and responds using text-to-speech.

\- \*\*Application Launcher:\*\* Opens applications, websites, and folders through voice commands.

\- \*\*Web Search:\*\* Opens Google and YouTube searches.

\- \*\*Date and Time:\*\* Provides current date, time, and day information.

\- \*\*Reminder Manager:\*\* Creates and manages reminders with notifications.

\- \*\*Hardware Controls:\*\* Controls system volume, brightness, mute, Wi-Fi, and sleep.

\- \*\*Command History:\*\* Stores command history using SQLite.

\- \*\*VoiceLock Security:\*\* Uses phrase-based authentication to protect private folder access.

\- \*\*Encrypted Vault:\*\* Protects selected folder data using AES-256-GCM encryption.



\## Technologies Used



\- Python 3

\- CustomTkinter

\- SpeechRecognition

\- Google Speech Recognition

\- pyttsx3

\- SQLite

\- Cryptography

\- SoundDevice

\- Pycaw

\- Screen Brightness Control

\- Windows Task Scheduler



\## Project Structure



```text

HEDWIG/

│

├── main.py

├── requirements.txt

├── README.md

│

├── automation/

│   ├── app\_launcher.py

│   ├── hardware\_controls.py

│   ├── reminder\_notify.py

│   └── reminder\_scheduler.py

│

├── cli/

│   └── reminder\_manager.py

│

├── database/

│   ├── history.py

│   └── reminders.py

│

├── security/

│   ├── encrypted\_vault.py

│   ├── vault\_manager.py

│   └── voicelock.py

│

└── voice/

&#x20;   └── google\_listen.py

```



\## Installation



1\. Clone the repository:



```bash

git clone YOUR\_GITHUB\_REPOSITORY\_URL

```



2\. Open the project directory:



```bash

cd HEDWIG

```



3\. Create a virtual environment:



```bash

python -m venv venv

```



4\. Activate the virtual environment:



```bash

venv\\Scripts\\activate

```



5\. Install dependencies:



```bash

pip install -r requirements.txt

```



\## Running the Application



Start HEDWIG using:



```bash

python main.py

```



For the standalone CLI Reminder Manager:



```bash

python cli/reminder\_manager.py

```



\## Security



\- VoiceLock uses PBKDF2-based password derivation for phrase authentication.

\- The encrypted vault uses AES-256-GCM.

\- Private vault configuration, encrypted vault files, and personal database files are excluded from version control.



\## Requirements and Limitations



\- Windows operating system.

\- Python 3 installed.

\- Internet connection required for Google Speech Recognition.

\- A working microphone and speaker are recommended.

\- Some hardware operations, such as Wi-Fi control, may require administrator permissions.

\- VoiceLock is phrase-based authentication, not biometric voice recognition.



\## Developer



\*\*Shirly Rajadurai\*\*



Developed for the CodeOrbit Tech Software Development Internship, 2026.

