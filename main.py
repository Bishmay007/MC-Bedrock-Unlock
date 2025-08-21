import sys
import os
import subprocess
import shutil
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QMessageBox, QDesktopWidget, QTextEdit, QLabel
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt
import platform


class BedrockUnlocker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MC Bedrock Unlocker")
        self.setFixedSize(700, 400)  # Increased window size
        self.center_window()
        self.set_icon()
        self.init_ui()

    def set_icon(self):
        icon_path = "./assets/icon/icon.png"
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            print("Warning: icon.png not found.")

    def center_window(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def detect_architecture(self):
        arch = platform.architecture()[0]
        if os.environ.get("PROCESSOR_ARCHITECTURE", "").endswith("64"):
            return "System Architecture: 64-bit"
        elif os.environ.get("PROCESSOR_ARCHITECTURE", "").endswith("86"):
            return "System Architecture: 32-bit"
        else:
            return f"Architecture: {arch}"

    def init_ui(self):
        window_width = self.width()
        # Button sizes
        unlock_btn_width = 300
        unlock_btn_height = 60
        restore_btn_width = 300
        restore_btn_height = 40
        spacing = 20

        # Center X for buttons
        center_x = (window_width - unlock_btn_width) // 2

        # Unlock button: centered near top
        self.unlock_button = QPushButton("Unlock", self)
        self.unlock_button.setFont(QFont("", 26))
        self.unlock_button.setGeometry(center_x, 40, unlock_btn_width, unlock_btn_height)
        self.unlock_button.clicked.connect(self.unlock_action)

        # Restore button: centered below Unlock
        self.restore_button = QPushButton("Restore", self)
        self.restore_button.setFont(QFont("", 18))
        self.restore_button.setGeometry(center_x, 40 + unlock_btn_height + spacing, restore_btn_width, restore_btn_height)
        self.restore_button.clicked.connect(self.restore_action)

        # Log display: large, lower part of window
        log_y = 40 + unlock_btn_height + spacing + restore_btn_height + spacing
        log_height = self.height() - log_y - 40
        self.log_display = QTextEdit(self)
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("", 13))
        self.log_display.setGeometry(50, log_y + 30, window_width - 100, log_height - 30)

        # Architecture label: small text, just above log box, left aligned
        self.arch_label = QLabel(self)
        self.arch_label.setText(self.detect_architecture())
        self.arch_label.setFont(QFont("", 10))
        self.arch_label.setStyleSheet("color: gray;")
        self.arch_label.setGeometry(50, log_y, 200, 18)
        self.arch_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Created by label: small text, just above log box, right aligned
        self.credit_label = QLabel(self)
        self.credit_label.setText("Created by: dheemansa")
        self.credit_label.setFont(QFont("", 10))
        self.credit_label.setStyleSheet("color: gray;")
        self.credit_label.setGeometry(window_width - 200 - 50, log_y, 200, 18)
        self.credit_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def append_log(self, message):
        self.log_display.append(message)

    def is_64bit_windows(self):
        return platform.machine().endswith('64')

    def unlock_action(self):
        self.append_log("Unlock button pressed. Attempting to delete DLL files...")
        files = [
            os.path.join(os.environ["SystemRoot"], "System32", "Windows.ApplicationModel.Store.dll")
        ]
        if self.is_64bit_windows():
            files.append(os.path.join(os.environ["SystemRoot"], "SysWOW64", "Windows.ApplicationModel.Store.dll"))
        for targetFile in files:
            folderName = "System32" if "System32" in targetFile else "SysWOW64"
            self.append_log(f"Checking {folderName}...")
            if os.path.exists(targetFile):
                try:
                    self.append_log(f"Taking ownership of {targetFile}...")
                    subprocess.run(
                        ["takeown", "/f", targetFile, "/a", "/r", "/d", "y"],
                        shell=True, capture_output=True, text=True
                    )
                    self.append_log("Granting full control to Administrators...")
                    subprocess.run(
                        ["icacls", targetFile, "/grant", "Administrators:F", "/t", "/c"],
                        shell=True, capture_output=True, text=True
                    )
                    self.append_log(f"Deleting {targetFile}...")
                    subprocess.run(
                        ["del", "/f", "/q", targetFile],
                        shell=True, capture_output=True, text=True
                    )
                    if not os.path.exists(targetFile):
                        self.append_log(f"Successfully deleted {folderName} file.")
                    else:
                        self.append_log(f"Failed to delete {folderName} file.")
                except Exception as e:
                    self.append_log(f"Error: {str(e)}")
            else:
                self.append_log(f"File not found in {folderName}.")

        # Copy custom DLLs after deletion
        try:
            if self.is_64bit_windows():
                # 64-bit: copy both System32 and SysWOW64
                src_sys32 = os.path.join("dll", "64-bit", "System32", "Windows.ApplicationModel.Store.dll")
                dst_sys32 = os.path.join(os.environ["SystemRoot"], "System32", "Windows.ApplicationModel.Store.dll")
                src_wow64 = os.path.join("dll", "64-bit", "SysWOW64", "Windows.ApplicationModel.Store.dll")
                dst_wow64 = os.path.join(os.environ["SystemRoot"], "SysWOW64", "Windows.ApplicationModel.Store.dll")
                if os.path.exists(src_sys32):
                    shutil.copy2(src_sys32, dst_sys32)
                    self.append_log("Copied custom DLL to System32.")
                else:
                    self.append_log("Custom DLL for System32 not found.")
                if os.path.exists(src_wow64):
                    shutil.copy2(src_wow64, dst_wow64)
                    self.append_log("Copied custom DLL to SysWOW64.")
                else:
                    self.append_log("Custom DLL for SysWOW64 not found.")
            else:
                # 32-bit: only System32
                src_sys32 = os.path.join("dll", "32-bit", "System32", "Windows.ApplicationModel.Store.dll")
                dst_sys32 = os.path.join(os.environ["SystemRoot"], "System32", "Windows.ApplicationModel.Store.dll")
                if os.path.exists(src_sys32):
                    shutil.copy2(src_sys32, dst_sys32)
                    self.append_log("Copied custom DLL to System32.")
                else:
                    self.append_log("Custom DLL for System32 not found.")
        except Exception as e:
            self.append_log(f"Error copying custom DLLs: {str(e)}")
        QMessageBox.information(self, "Unlock", "Unlock operation finished.")

    def restore(self):
        reply = QMessageBox.question(
            self,
            "Restore DLL",
            "This will attempt to restore the DLL file using 'sfc /scannow'.\n"
            "This process might take a long time.\n\nDo you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.append_log("Starting 'sfc /scannow'... This may take a while.")
            try:
                # Run sfc /scannow as administrator and capture output
                process = subprocess.Popen(
                    ["cmd.exe", "/c", "sfc /scannow"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    shell=True,
                    text=True
                )
                for line in process.stdout:
                    self.append_log(line.rstrip())
                process.wait()
                self.append_log("'sfc /scannow' finished.")
            except Exception as e:
                self.append_log(f"Error running sfc /scannow: {str(e)}")
        else:
            self.append_log("Restore operation cancelled by user.")

    def restore_action(self):
        self.restore()

    def restore_ownership(self):
        files = [
            os.path.join(os.environ["SystemRoot"], "System32", "Windows.ApplicationModel.Store.dll")
        ]
        if self.is_64bit_windows():
            files.append(os.path.join(os.environ["SystemRoot"], "SysWOW64", "Windows.ApplicationModel.Store.dll"))
        for targetFile in files:
            folderName = "System32" if "System32" in targetFile else "SysWOW64"
            self.append_log(f"Restoring ownership for {folderName}...")
            if os.path.exists(targetFile):
                try:
                    result = subprocess.run(
                        ["icacls", targetFile, "/setowner", "NT SERVICE\\TrustedInstaller", "/t", "/c"],
                        shell=True, capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        self.append_log(f"Ownership restored to TrustedInstaller for {folderName}.")
                    else:
                        self.append_log(f"Failed to restore ownership for {folderName}: {result.stderr}")
                except Exception as e:
                    self.append_log(f"Error: {str(e)}")
            else:
                self.append_log(f"File not found in {folderName}.")

def main():
    app = QApplication(sys.argv)
    win = BedrockUnlocker()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()