import sys
import os
import subprocess
import shutil
import logging
from pathlib import Path
from typing import List, Optional
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QMessageBox, 
    QDesktopWidget, QTextEdit, QLabel, QProgressBar, QVBoxLayout, 
    QHBoxLayout, QWidget, QFrame
)
from PyQt5.QtGui import QIcon, QFont, QPalette
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
import platform

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Ensure the 'dll' directory exists
class WorkerThread(QThread):
    """Thread for handling long-running operations without blocking UI"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, operation, *args):
        super().__init__()
        self.operation = operation
        self.args = args
    
    def run(self):
        try:
            if self.operation == "unlock":
                self.unlock_operation()
            elif self.operation == "restore":
                self.restore_operation()
        except Exception as e:
            self.finished_signal.emit(False, str(e))
    
    def unlock_operation(self):
        """Perform unlock operation in separate thread"""
        self.log_signal.emit("Starting unlock operation...")
        
        # Get target files
        files = self.get_target_files()
        total_files = len(files)
        
        for i, target_file in enumerate(files):
            folder_name = "System32" if "System32" in target_file else "SysWOW64"
            self.log_signal.emit(f"Processing {folder_name}...")
            
            if self.process_dll_file(target_file, folder_name):
                self.log_signal.emit(f"Successfully processed {folder_name}")
            else:
                self.log_signal.emit(f"Failed to process {folder_name}")
            
            # Update progress
            progress = int((i + 1) / total_files * 50)  # 50% for deletion
            self.progress_signal.emit(progress)
        
        # Copy custom DLLs
        copy_success = self.copy_custom_dlls()
        self.progress_signal.emit(100)
        if copy_success:
            self.finished_signal.emit(True, "Unlock operation completed successfully")
        else:
            self.finished_signal.emit(False, "Unlock operation failed: One or more custom DLLs were not copied")
    
    def restore_operation(self):
        """Perform restore operation using sfc /scannow with accurate progress"""
        self.log_signal.emit("Starting system file checker...")
        self.progress_signal.emit(0)
        self.process = None  # Store process handle
        try:
            self.process = subprocess.Popen(
                ["sfc", "/scannow"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            for line in self.process.stdout:
                line = line.strip()
                if line:
                    self.log_signal.emit(line)
                    # Parse progress from "Verification XX% complete."
                    if "Verification" in line and "% complete" in line:
                        import re
                        match = re.search(r'(\d+)% complete', line)
                        if match:
                            percent = int(match.group(1))
                            self.progress_signal.emit(percent)
            
            self.process.wait()
            self.progress_signal.emit(100)
            
            if self.process.returncode == 0:
                self.finished_signal.emit(True, "System file check completed")
            else:
                self.finished_signal.emit(False, f"SFC returned error code: {self.process.returncode}")
                
        except Exception as e:
            self.finished_signal.emit(False, f"Error running sfc: {str(e)}")
    
    def get_target_files(self) -> List[str]:
        """Get list of target DLL files based on system architecture"""
        files = [os.path.join(os.environ["SystemRoot"], "System32", "Windows.ApplicationModel.Store.dll")]
        
        if self.is_64bit_system():
            files.append(os.path.join(os.environ["SystemRoot"], "SysWOW64", "Windows.ApplicationModel.Store.dll"))
        
        return files
    
    def is_64bit_system(self) -> bool:
        """Check if system is 64-bit"""
        return platform.machine().endswith('64') or os.environ.get('PROCESSOR_ARCHITECTURE', '').endswith('64')
    
    def process_dll_file(self, target_file: str, folder_name: str) -> bool:
        """Process a single DLL file (take ownership, grant permissions, delete)"""
        if not os.path.exists(target_file):
            self.log_signal.emit(f"{folder_name} file not present -- skipping")
            return True  # Not an error if file doesn't exist

        try:
            # Create backup
            backup_path = f"{target_file}.backup"
            if not os.path.exists(backup_path):
                shutil.copy2(target_file, backup_path)
                self.log_signal.emit(f"Created backup: {backup_path}")

            # Take ownership
            self.log_signal.emit(f"Taking ownership of {folder_name} file...")
            result = subprocess.run(
                ["takeown", "/f", target_file, "/a"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode != 0:
                self.log_signal.emit(f"Failed to take ownership: {result.stderr.strip()}")
                return False

            # Grant permissions
            self.log_signal.emit(f"Granting permissions for {folder_name}...")
            result = subprocess.run(
                ["icacls", target_file, "/grant", "Administrators:F"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode != 0:
                self.log_signal.emit(f"Failed to grant permissions: {result.stderr.strip()}")
                return False

            # Delete file
            self.log_signal.emit(f"Deleting {folder_name} file...")
            try:
                os.remove(target_file)
            except Exception as e:
                self.log_signal.emit(f"Error deleting {folder_name}: {str(e)}")
                return False

            if not os.path.exists(target_file):
                self.log_signal.emit(f"Successfully deleted {folder_name} file.")
                return True
            else:
                self.log_signal.emit(f"Failed to delete {folder_name} file.")
                return False

        except Exception as e:
            self.log_signal.emit(f"Error processing {folder_name}: {str(e)}")
            return False
    
    def copy_custom_dlls(self):
        """Copy custom DLL files to system directories. Returns True if all copies succeed."""
        self.log_signal.emit("Copying custom DLL files...")
        success = True
        try:
            if self.is_64bit_system():
                if not self.copy_dll_file("64-bit", "System32"):
                    success = False
                if not self.copy_dll_file("64-bit", "SysWOW64"):
                    success = False
            else:
                if not self.copy_dll_file("32-bit", "System32"):
                    success = False
        except Exception as e:
            self.log_signal.emit(f"Error copying custom DLLs: {str(e)}")
            success = False
        return success

    def copy_dll_file(self, arch_folder: str, system_folder: str) -> bool:
        """Copy a specific DLL file. Returns True if copy succeeds."""
        src_path = Path(resource_path(f"dll/{arch_folder}/{system_folder}/Windows.ApplicationModel.Store.dll"))
        dst_path = Path(os.environ["SystemRoot"]) / system_folder / "Windows.ApplicationModel.Store.dll"
        
        if src_path.exists():
            try:
                shutil.copy2(str(src_path), str(dst_path))
                self.log_signal.emit(f"Copied custom DLL to {system_folder}")
                return True
            except Exception as e:
                self.log_signal.emit(f"Error copying DLL to {system_folder}: {str(e)}")
                return False
        else:
            self.log_signal.emit(f"❌ Custom DLL not found for {system_folder}")
            return False


class BedrockUnlocker(QMainWindow):

    def is_64bit_system(self) -> bool:
        """Check if system is 64-bit"""
        return platform.machine().endswith('64') or os.environ.get('PROCESSOR_ARCHITECTURE', '').endswith('64')

    def __init__(self):
        super().__init__()
        self.worker_thread = None
        self.setup_logging()
        self.init_window()
        self.init_ui()
        self.check_required_files()
        
    def setup_logging(self):
        """Setup logging configuration"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / 'bedrock_unlocker.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def init_window(self):
        """Initialize main window properties"""
        self.setWindowTitle("MC Bedrock Unlocker v1.0")
        self.setFixedSize(800, 500)
        self.center_window()
        self.set_icon()
        self.setStyleSheet(self.get_stylesheet())

    
    def get_stylesheet(self) -> str:
        """Return application stylesheet with regular button styling (white theme)"""
        return """
        QMainWindow {
            background-color: #f8f8f8;
            color: #222222;
        }
        QPushButton {
            background-color: #e0e0e0;
            border: 2px solid #cccccc;
            border-radius: 0px;
            padding: 8px;
            font-weight: bold;
            color: #222222;
        }
        QPushButton:hover {
            background-color: #f0f0f0;
            border-color: #b0b0b0;
        }
        QPushButton:pressed {
            background-color: #d0d0d0;
        }
        QPushButton:disabled {
            background-color: #f4f4f4;
            border-color: #e0e0e0;
            color: #aaaaaa;
        }
        QTextEdit {
            background-color: #ffffff;
            border: 1px solid #cccccc;
            border-radius: 4px;
            padding: 4px;
            color: #222222;
            font-family: monospace;
        }
        QProgressBar {
            border: 1px solid #cccccc;
            border-radius: 4px;
            text-align: center;
            background: #f4f4f4;
            color: #222222;
        }
        QProgressBar::chunk {
            background-color: #4CAF50;
            border-radius: 3px;
        }
        QLabel {
            color: #222222;
        }
        """

    def set_icon(self):
        """Set window icon if available"""
        icon_path = Path(resource_path("assets/icon/icon.png"))
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def center_window(self):
        """Center window on screen"""
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def init_ui(self):
        """Initialize user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title_label = QLabel("MC Bedrock Unlocker")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(title_label)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        
        # Unlock button
        self.unlock_button = QPushButton("🔓 Unlock Bedrock")
        self.unlock_button.setFont(QFont("Arial", 14, QFont.Bold))
        self.unlock_button.setMinimumHeight(50)
        self.unlock_button.clicked.connect(self.unlock_action)
        button_layout.addWidget(self.unlock_button)
        
        # Restore button
        self.restore_button = QPushButton("🔄 Restore Original")
        self.restore_button.setFont(QFont("Arial", 14, QFont.Bold))
        self.restore_button.setMinimumHeight(50)
        self.restore_button.clicked.connect(self.restore_action)
        button_layout.addWidget(self.restore_button)
        
        layout.addLayout(button_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Info layout
        info_layout = QHBoxLayout()
        
        # System info
        self.arch_label = QLabel(f"Architecture: {self.get_system_info()}")
        self.arch_label.setFont(QFont("Arial", 10))
        info_layout.addWidget(self.arch_label)
        
        info_layout.addStretch()
        
        # Credit
        credit_label = QLabel("Created by: dheemansa")
        credit_label.setFont(QFont("Arial", 10))
        info_layout.addWidget(credit_label)
        
        layout.addLayout(info_layout)
        
        # Log display
        log_label = QLabel("Activity Log:")
        log_label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(log_label)
        
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 10))
        self.log_display.setMinimumHeight(200)
        layout.addWidget(self.log_display)
        
        # Initial log message
        self.append_log("Application started successfully")
        self.append_log(f"System: {platform.system()} {platform.release()}")
        self.append_log(f"Architecture: {self.get_system_info()}")

    def get_system_info(self) -> str:
        """Get system architecture information"""
        if platform.machine().endswith('64'):
            return "64-bit"
        elif platform.machine().endswith('86'):
            return "32-bit"
        else:
            return platform.machine()

    def append_log(self, message: str):
        """Append message to log display and logger"""
        self.log_display.append(message)
        self.logger.info(message)

    def set_ui_enabled(self, enabled: bool):
        """Enable/disable UI elements during operations"""
        self.unlock_button.setEnabled(enabled)
        self.restore_button.setEnabled(enabled)
        self.progress_bar.setVisible(not enabled)
        if not enabled:
            self.progress_bar.setValue(0)

    def unlock_action(self):
        """Handle unlock button click"""
        if not self.check_admin_privileges():
            QMessageBox.warning(
                self,
                "Administrator Required",
                "This application requires administrator privileges to modify system files.\n"
                "Please restart as administrator."
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirm Unlock",
            "This will modify system DLL files to unlock Minecraft Bedrock.\n\n"
            "⚠️ Warning: This modifies system files. Ensure you have:\n"
            "• Created a system restore point\n"
            "• Backed up important data\n"
            "• Custom DLL files in the 'dll' folder\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.start_unlock_operation()

    def restore_action(self):
        """Handle restore button click"""
        if not self.check_admin_privileges():
            QMessageBox.warning(
                self,
                "Administrator Required",
                "Administrator privileges required for system file restoration."
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirm Restore",
            "This will run 'sfc /scannow' to restore original system files.\n\n"
            "⚠️ This process may take 10-30 minutes and cannot be cancelled.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.start_restore_operation()

    def check_admin_privileges(self) -> bool:
        """Check if running with administrator privileges"""
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False

    def start_unlock_operation(self):
        """Start unlock operation in worker thread"""
        self.set_ui_enabled(False)
        self.append_log("=" * 50)
        self.append_log("Starting unlock operation...")
        
        self.worker_thread = WorkerThread("unlock")
        self.worker_thread.log_signal.connect(self.append_log)
        self.worker_thread.progress_signal.connect(self.progress_bar.setValue)
        self.worker_thread.finished_signal.connect(self.on_operation_finished)
        self.worker_thread.start()

    def start_restore_operation(self):
        """Start restore operation in worker thread"""
        self.set_ui_enabled(False)
        self.append_log("=" * 50)
        self.append_log("Starting restore operation...")
        
        self.worker_thread = WorkerThread("restore")
        self.worker_thread.log_signal.connect(self.append_log)
        self.worker_thread.progress_signal.connect(self.progress_bar.setValue)
        self.worker_thread.finished_signal.connect(self.on_operation_finished)
        self.worker_thread.start()

    def on_operation_finished(self, success: bool, message: str):
        """Handle operation completion"""
        self.set_ui_enabled(True)
        self.append_log("=" * 50)
        
        if success:
            self.append_log(f"✅ {message}")
            QMessageBox.information(self, "Success", message)
        else:
            self.append_log(f"❌ Operation failed: {message}")
            QMessageBox.critical(self, "Error", f"Operation failed:\n{message}")

    def check_required_files(self):
        """Check if all required DLL files are present before enabling UI."""
        self.set_ui_enabled(False)
        self.append_log("Running files check, please wait...")

        missing = []
        if self.is_64bit_system():
            paths = [
                Path(resource_path("dll/64-bit/System32/Windows.ApplicationModel.Store.dll")),
                Path(resource_path("dll/64-bit/SysWOW64/Windows.ApplicationModel.Store.dll"))
            ]
        else:
            paths = [
                Path(resource_path("dll/32-bit/System32/Windows.ApplicationModel.Store.dll"))
            ]

        for p in paths:
            if not p.exists():
                missing.append(str(p))

        if not missing:
            self.append_log("All required DLL files found. Ready to use.")
            self.set_ui_enabled(True)
        else:
            self.append_log("❌ Necessary files are missing:")
            for file in missing:
                self.append_log(f"Missing: {file}")
            QMessageBox.critical(
                self,
                "Missing Files",
                "Necessary files are not found.\nPlease report this issue to the developers with necessary information."
            )
            self.set_ui_enabled(False)

    

    def closeEvent(self, event):
        """Handle application close event"""
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Operation in Progress",
                "An operation is currently running. Force close?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Attempt to terminate restore process if running
                if self.worker_thread.operation == "restore" and hasattr(self.worker_thread, "process"):
                    try:
                        self.worker_thread.process.terminate()
                        self.worker_thread.process.wait(timeout=5)
                        self.append_log("Restore process terminated.")
                    except Exception as e:
                        self.append_log(f"Error terminating restore process: {str(e)}")
                self.worker_thread.terminate()
                self.worker_thread.wait()
                event.accept()
                sys.exit(0)  # Ensure proper exit
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("MC Bedrock Unlocker")
    app.setApplicationVersion("2.0")
    
    # Set application icon
    icon_path = Path(resource_path("assets/icon/icon.png"))
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    window = BedrockUnlocker()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
