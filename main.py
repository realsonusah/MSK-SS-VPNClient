import sys
import json
import subprocess
import os
import base64
import psutil
import requests
import shutil
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QWidget, QLabel,
    QVBoxLayout, QLineEdit, QHBoxLayout, QSystemTrayIcon, QMenu, QAction
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QTimer

# ------------------ CONFIG ------------------
CURRENT_VERSION = "1.0"
GITHUB_OWNER = "realsonusah"
GITHUB_REPO = "MSK-SS-VPNClient"
UPDATE_CHECK_INTERVAL = 3600 * 1000  # 1 hour in milliseconds
AUTO_RESTART_AFTER_UPDATE = True

CONFIG_FILE = "config.json"
SSLOCAL_PATH = "sslocal.exe"
TEMP_CONFIG = "temp_ss_config.json"
ICON_FILE = "icon.ico"

# ------------------ MAIN CLASS ------------------
class MSKClient(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("MSK SS Client")
        self.setFixedSize(350, 380)
        self.setWindowIcon(QIcon(ICON_FILE))

        self.ss_process = None
        self.last_bytes_sent = 0
        self.last_bytes_recv = 0

        self.load_config()
        self.init_ui()
        self.init_tray()

        # Timer for network speed
        self.speed_timer = QTimer()
        self.speed_timer.timeout.connect(self.update_speed)
        self.speed_timer.start(1000)  # 1 second

        # Timer for auto-update check
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.check_for_update)
        self.update_timer.start(UPDATE_CHECK_INTERVAL)
        # Check once at startup
        self.check_for_update()

    # ------------------ CONFIG ------------------
    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            default = {
                "server": "",
                "port": "",
                "password": "",
                "method": "chacha20-ietf-poly1305"
            }
            with open(CONFIG_FILE, "w") as f:
                json.dump(default, f, indent=4)
            self.config = default
        else:
            with open(CONFIG_FILE, "r") as f:
                self.config = json.load(f)

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=4)

    # ------------------ UI ------------------
    def init_ui(self):
        self.central = QWidget()
        self.main_layout = QVBoxLayout()

        # Big Connect Button
        self.btn_toggle = QPushButton("CONNECT")
        self.btn_toggle.setStyleSheet("font-size: 22px; padding: 20px;")
        self.btn_toggle.clicked.connect(self.toggle_vpn)
        self.main_layout.addWidget(self.btn_toggle)

        # Network Speed Label
        self.lbl_speed = QLabel("")
        self.lbl_speed.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.lbl_speed)

        # Show/Hide Settings Button
        self.btn_show_settings = QPushButton("Show Settings")
        self.btn_show_settings.setCheckable(True)
        self.btn_show_settings.clicked.connect(self.toggle_settings_panel)
        self.main_layout.addWidget(self.btn_show_settings)

        # Settings Panel
        self.settings_panel = QWidget()
        settings_layout = QVBoxLayout()

        # -------- Server IP + Port in one row --------
        row = QHBoxLayout()
        self.in_server = QLineEdit(self.config.get("server", ""))
        self.in_server.setPlaceholderText("Server IP")
        self.in_port = QLineEdit(self.config.get("port", ""))
        self.in_port.setPlaceholderText("Port")
        self.in_port.setMaximumWidth(80)
        row.addWidget(self.in_server)
        row.addWidget(self.in_port)
        settings_layout.addLayout(row)

        # -------- Password --------
        self.in_pass = QLineEdit(self.config.get("password", ""))
        self.in_pass.setPlaceholderText("Password")
        settings_layout.addWidget(self.in_pass)

        # -------- Method (Unclickable) --------
        self.in_method = QLineEdit(self.config.get("method", ""))
        self.in_method.setReadOnly(True)
        self.in_method.setStyleSheet("background:#eee;")
        settings_layout.addWidget(self.in_method)

        # -------- Outline Key --------
        self.in_outline = QLineEdit()
        self.in_outline.setPlaceholderText("Paste Outline Key here")
        settings_layout.addWidget(self.in_outline)

        self.btn_outline = QPushButton("Add Outline Key")
        self.btn_outline.clicked.connect(self.parse_outline_key)
        settings_layout.addWidget(self.btn_outline)

        self.settings_panel.setLayout(settings_layout)
        self.settings_panel.setVisible(False)
        self.main_layout.addWidget(self.settings_panel)

        self.central.setLayout(self.main_layout)
        self.setCentralWidget(self.central)

    def toggle_settings_panel(self):
        show = self.btn_show_settings.isChecked()
        self.settings_panel.setVisible(show)
        self.btn_show_settings.setText("Hide Settings" if show else "Show Settings")

    # ------------------ Outline Key ------------------
    def parse_outline_key(self):
        key = self.in_outline.text().strip()
        if not key.startswith("ss://"):
            print("Not a valid Outline key")
            return
        try:
            raw = key.replace("ss://", "")
            if "@" in raw:
                left, right = raw.split("@", 1)
                missing_padding = 4 - (len(left) % 4)
                if missing_padding != 4:
                    left += "=" * missing_padding
                decoded = base64.urlsafe_b64decode(left).decode(errors="ignore")
                method, password = decoded.split(":", 1)
                server = right.split(":")[0]
                port = right.split(":")[1].split("/")[0]
                self.in_method.setText(method)
                self.in_pass.setText(password)
                self.in_server.setText(server)
                self.in_port.setText(port)
                print("Outline key parsed successfully.")
            else:
                print("Invalid Outline key format")
        except Exception as e:
            print("Outline parse error:", e)

    # ------------------ VPN ------------------
    def toggle_vpn(self):
        if self.ss_process is None:
            self.start_vpn()
        else:
            self.stop_vpn()

    def start_vpn(self):
        self.config["server"] = self.in_server.text().strip()
        self.config["port"] = self.in_port.text().strip()
        self.config["password"] = self.in_pass.text().strip()
        self.config["method"] = self.in_method.text().strip()
        self.save_config()

        try:
            port_int = int(self.config["port"])
        except ValueError:
            print("Invalid port number")
            return

        cfg = {
            "server": self.config["server"],
            "server_port": port_int,
            "password": self.config["password"],
            "method": self.config["method"],
            "local_address": "127.0.0.1",
            "local_port": 1080,
            "timeout": 300
        }

        with open(TEMP_CONFIG, "w") as f:
            json.dump(cfg, f, indent=4)

        sslocal_full = os.path.join(os.getcwd(), SSLOCAL_PATH)
        if not os.path.exists(sslocal_full):
            print("sslocal.exe not found")
            return

        cmd = [sslocal_full, "-c", TEMP_CONFIG]
        print("Running:", cmd)

        try:
            self.ss_process = subprocess.Popen(cmd)
        except Exception as e:
            print("Error launching sslocal:", e)
            return

        # Enable Windows proxy
        os.system('reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f')
        os.system('reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyServer /t REG_SZ /d "socks=127.0.0.1:1080" /f')

        self.btn_toggle.setText("DISCONNECT")
        self.btn_toggle.setStyleSheet("background:#e74c3c; color:white; font-size:22px; padding:20px;")

    def stop_vpn(self):
        if self.ss_process:
            self.ss_process.terminate()
            self.ss_process = None

        os.system('reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f')

        self.btn_toggle.setText("CONNECT")
        self.btn_toggle.setStyleSheet("font-size:22px; padding:20px;")

    # ------------------ Network Speed ------------------
    def update_speed(self):
        if self.ss_process is None:
            self.lbl_speed.setText("")
            return

        counters = psutil.net_io_counters()
        sent = counters.bytes_sent
        recv = counters.bytes_recv

        up_speed = (sent - self.last_bytes_sent) / 1024
        down_speed = (recv - self.last_bytes_recv) / 1024

        self.last_bytes_sent = sent
        self.last_bytes_recv = recv

        self.lbl_speed.setText(f"↑ {up_speed:.1f} KB/s | ↓ {down_speed:.1f} KB/s")

    # ------------------ Auto Update ------------------
    def check_for_update(self):
        try:
            url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                latest = response.json()
                latest_version = latest["tag_name"].strip("v")
                asset_name = f"MSK-SS-VPN-v{latest_version}.exe"
                download_url = None
                for asset in latest["assets"]:
                    if asset["name"] == asset_name:
                        download_url = asset["browser_download_url"]
                        break
                if download_url and latest_version != CURRENT_VERSION:
                    print(f"New version {latest_version} available. Downloading...")
                    self.download_update(download_url, asset_name)
            else:
                print("Failed to check update:", response.status_code)
        except Exception as e:
            print("Update check error:", e)

    def download_update(self, url, filename):
        try:
            local_path = os.path.join(os.getcwd(), filename)
            r = requests.get(url, stream=True)
            with open(local_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)
            print(f"Downloaded new version to {local_path}")
            if AUTO_RESTART_AFTER_UPDATE:
                print("Restarting app to apply update...")
                self.restart_app(local_path)
        except Exception as e:
            print("Download error:", e)

    def restart_app(self, new_exe_path):
        self.stop_vpn()
        python = sys.executable
        os.execv(new_exe_path, [new_exe_path])

    # ------------------ SysTray ------------------
    def init_tray(self):
        icon = QIcon(ICON_FILE)

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("MSK SS Client")

        menu = QMenu()
        act_show = QAction("Show", self)
        act_show.triggered.connect(self.show)
        menu.addAction(act_show)

        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self.exit_app)
        menu.addAction(act_exit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def exit_app(self):
        self.stop_vpn()
        sys.exit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MSKClient()
    win.show()
    sys.exit(app.exec_())
