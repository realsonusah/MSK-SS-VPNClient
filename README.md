MSK Shadowsocks VPN Client (MSK-SS-VPN Client)

A lightweight custom VPN client built with Python and PyQt6 to connect to Shadowsocks servers easily on Windows.
Supports start/stop connection, system tray, and auto-reload of configs.

Features:
Simple GUI (PyQt6)
Start / Stop Shadowsocks connection
Auto-generate temp_ss_config.json
Runs sslocal.exe in background
System tray support (optional)

Requirements
Python 3.10+

Install dependencies:
pip install -r requirements.txt

Run
python main.py

Build EXE (Optional)
pyinstaller --noconsole --onefile --icon=icon.ico main.py

Files
main.py → Main application

requirements.txt → Dependencies

.gitignore → Ignores build and temp files
