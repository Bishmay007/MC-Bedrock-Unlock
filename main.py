import sys
import os
import subprocess
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QMessageBox, QDesktopWidget, QTextEdit
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt


# ...existing code...

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

    def init_ui(self):
        # Unlock button: wide and centered
        self.unlock_button = QPushButton("Unlock", self)
        self.unlock_button.setFont(QFont("", 26))
        self.unlock_button.setGeometry(50, 40, 400, 70)
        self.unlock_button.clicked.connect(self.unlock_action)

        # Restore button: smaller, placed to the right of Unlock
        self.restore_button = QPushButton("Restore", self)
        self.restore_button.setFont(QFont("", 18))
        self.restore_button.setGeometry(480, 55, 150, 45)
        self.restore_button.clicked.connect(self.restore_action)

        # Log display: taller and wider
        self.log_display = QTextEdit(self)
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("", 13))
        self.log_display.setGeometry(50, 130, 580, 220)

    def append_log(self, message):
        self.log_display.append(message)

    def unlock_action(self):
        self.append_log("Unlock button pressed. Attempting to delete DLL files...")
        files = [
            os.path.join(os.environ["SystemRoot"], "System32", "Windows.ApplicationModel.Store.dll"),
            os.path.join(os.environ["SystemRoot"], "SysWOW64", "Windows.ApplicationModel.Store.dll")
        ]
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
        QMessageBox.information(self, "Unlock", "Unlock operation finished.")

    def restore_action(self):
        self.append_log("Restore button was clicked!")
        QMessageBox.information(self, "Restore", "Restore button was clicked!")

    def restore_ownership(self):
        files = [
            os.path.join(os.environ["SystemRoot"], "System32", "Windows.ApplicationModel.Store.dll"),
            os.path.join(os.environ["SystemRoot"], "SysWOW64", "Windows.ApplicationModel.Store.dll")
        ]
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