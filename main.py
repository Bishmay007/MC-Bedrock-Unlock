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
        self.copy_custom_dlls()
        self.progress_signal.emit(100)
        self.finished_signal.emit(True, "Unlock operation completed successfully")
    
    def restore_operation(self):
        """Perform restore operation using sfc /scannow"""
        self.log_signal.emit("Starting system file checker...")
        self.progress_signal.emit(10)
        
        try:
            process = subprocess.Popen(
                ["sfc", "/scannow"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            for line in process.stdout:
                line = line.strip()
                if line:
                    self.log_signal.emit(line)
            
            process.wait()
            self.progress_signal.emit(100)
            
            if process.returncode == 0:
                self.finished_signal.emit(True, "System file check completed")
            else:
                self.finished_signal.emit(False, f"SFC returned error code: {process.returncode}")
                
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
            self.log_signal.emit(f"File not found in {folder_name}")
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
                self.log_signal.emit(f"Failed to take ownership: {result.stderr}")
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
                self.log_signal.emit(f"Failed to grant permissions: {result.stderr}")
                return False
            
            # Delete file
            self.log_signal.emit(f"Deleting {folder_name} file...")
            os.remove(target_file)
            
            return not os.path.exists(target_file)
            
        except Exception as e:
            self.log_signal.emit(f"Error processing {folder_name}: {str(e)}")
            return False
    
    def copy_custom_dlls(self):
        """Copy custom DLL files to system directories"""
        self.log_signal.emit("Copying custom DLL files...")
        
        try:
            if self.is_64bit_system():
                self.copy_dll_file("64-bit", "System32")
                self.copy_dll_file("64-bit", "SysWOW64")
            else:
                self.copy_dll_file("32-bit", "System32")
        except Exception as e:
            self.log_signal.emit(f"Error copying custom DLLs: {str(e)}")
    
    def copy_dll_file(self, arch_folder: str, system_folder: str):
        """Copy a specific DLL file"""
        src_path = Path("dll") / arch_folder / system_folder / "Windows.ApplicationModel.Store.dll"
        dst_path = Path(os.environ["SystemRoot"]) / system_folder / "Windows.ApplicationModel.Store.dll"
        
        if src_path.exists():
            shutil.copy2(str(src_path), str(dst_path))
            self.log_signal.emit(f"Copied custom DLL to {system_folder}")
        else:
            self.log_signal.emit(f"Warning: Custom DLL not found for {system_folder}")


class BedrockUnlocker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker_thread = None
        self.setup_logging()
        self.init_window()
        self.init_ui()
        
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
        self.setWindowTitle("MC Bedrock Unlocker v2.0")
        self.setFixedSize(800, 500)
        self.center_window()
        self.set_icon()
        self.setStyleSheet(self.get_stylesheet())

    def get_stylesheet(self) -> str:
        """Return application stylesheet"""
        return """
        QMainWindow {
            background-color: #f8f8f8;
            color: #222222;
        }
        QPushButton {
            background-color: #e0e0e0;
            border: 2px solid #cccccc;
            border-radius: 8px;
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
            font-family: 'Consolas', 'Courier New', monospace;
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
        icon_path = Path("assets/icon/icon.png")
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
                self.worker_thread.terminate()
                self.worker_thread.wait()
                event.accept()
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
    icon_path = Path("assets/icon/icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    window = BedrockUnlocker()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()