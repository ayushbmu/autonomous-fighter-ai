"""
AutonomousFighter Desktop Application - PyQt6
Bot control panel with live game feed.
"""

import base64
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import asyncio
import websockets
from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class WebSocketWorker(QThread):
    """WebSocket connection worker thread."""

    telemetry_received = pyqtSignal(dict)
    connection_status = pyqtSignal(bool)

    def __init__(self, ws_url: str = "ws://127.0.0.1:8001/ws"):
        super().__init__()
        self.ws_url = ws_url
        self._stop_requested = False

    def run(self):
        asyncio.run(self._connect())

    async def _connect(self):
        while not self._stop_requested:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    self.connection_status.emit(True)
                    while not self._stop_requested:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                            if message and message != "pong":
                                try:
                                    data = json.loads(message)
                                    self.telemetry_received.emit(data)
                                except json.JSONDecodeError:
                                    pass
                        except asyncio.TimeoutError:
                            try:
                                await websocket.send("ping")
                            except Exception:
                                break
                        except Exception:
                            break
            except Exception:
                self.connection_status.emit(False)
                await asyncio.sleep(1.5)

    def stop(self):
        self._stop_requested = True
        self.wait(2000)


class BotControlWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutonomousFighter - Bot Control")
        self.setGeometry(60, 40, 800, 600)
        self.setMinimumSize(720, 480)
        self.setStyleSheet(self._get_stylesheet())

        self.current_data: Dict[str, Any] = {}
        self.last_frame_pixmap: Optional[QPixmap] = None
        self.bot_process: Optional[subprocess.Popen] = None
        self.ws_worker: Optional[WebSocketWorker] = None
        self.project_root = Path(__file__).resolve().parent

        self._setup_ui()
        self._set_running_state(False)

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("LIVE FEED")
        title.setFont(self._get_header_font())
        layout.addWidget(title)

        self.game_frame_label = QLabel("Bot stopped. Press START.")
        self.game_frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.game_frame_label.setStyleSheet("background-color: #121212; border: 2px solid #ff6600;")
        self.game_frame_label.setMinimumSize(640, 360)
        layout.addWidget(self.game_frame_label, stretch=1)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.start_button = QPushButton("START")
        self.start_button.clicked.connect(self._start_bot)
        controls.addWidget(self.start_button)

        self.stop_button = QPushButton("STOP")
        self.stop_button.clicked.connect(self._stop_bot)
        controls.addWidget(self.stop_button)

        controls.addStretch()

        self.connection_indicator = QLabel("OFFLINE")
        self.connection_indicator.setStyleSheet("color: #cc0000; font-weight: bold;")
        controls.addWidget(self.connection_indicator)

        self.fps_label = QLabel("FPS: 0.0")
        self.fps_label.setStyleSheet("color: #ffaa00;")
        controls.addWidget(self.fps_label)

        layout.addLayout(controls)

    def _start_ws(self):
        if self.ws_worker is not None and self.ws_worker.isRunning():
            return

        self.ws_worker = WebSocketWorker()
        self.ws_worker.telemetry_received.connect(self._on_telemetry)
        self.ws_worker.connection_status.connect(self._on_connection_status)
        self.ws_worker.start()

    def _stop_ws(self):
        if self.ws_worker is None:
            return
        self.ws_worker.stop()
        self.ws_worker = None
        self._on_connection_status(False)

    def _start_bot(self):
        if self.bot_process is not None and self.bot_process.poll() is None:
            return

        self.current_data = {}
        self.last_frame_pixmap = None
        self.game_frame_label.setText("Starting bot...")
        self.game_frame_label.setPixmap(QPixmap())
        self.fps_label.setText("FPS: 0.0")

        cmd = [sys.executable, "main.py"]
        try:
            # Create a detached process group so we can stop the bot cleanly on Windows.
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            self.bot_process = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                creationflags=creationflags,
            )
        except Exception as exc:
            self.game_frame_label.setText(f"Failed to start bot: {exc}")
            self.bot_process = None
            self._set_running_state(False)
            return

        self._start_ws()
        self._set_running_state(True)

    def _stop_bot(self):
        self._stop_ws()

        if self.bot_process is not None and self.bot_process.poll() is None:
            try:
                if os.name == "nt":
                    self.bot_process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    self.bot_process.terminate()
                self.bot_process.wait(timeout=3)
            except Exception:
                try:
                    self.bot_process.kill()
                except Exception:
                    pass

        self.bot_process = None
        self.current_data = {}
        self.last_frame_pixmap = None
        self.game_frame_label.setPixmap(QPixmap())
        self.game_frame_label.setText("Bot stopped. Press START.")
        self.fps_label.setText("FPS: 0.0")
        self._set_running_state(False)

    def _set_running_state(self, running: bool):
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _on_telemetry(self, data: Dict[str, Any]):
        self.current_data = data
        self.fps_label.setText(f"FPS: {float(data.get('fps', 0.0)):.1f}")

        encoded = data.get("live_frame_jpeg")
        if not encoded:
            return

        try:
            frame_data = base64.b64decode(encoded)
            pixmap = QPixmap()
            if not pixmap.loadFromData(frame_data):
                return
            self.last_frame_pixmap = pixmap
            self._render_scaled_frame()
        except Exception:
            return

    def _on_connection_status(self, connected: bool):
        if connected:
            self.connection_indicator.setText("ONLINE")
            self.connection_indicator.setStyleSheet("color: #00cc00; font-weight: bold;")
        else:
            self.connection_indicator.setText("OFFLINE")
            self.connection_indicator.setStyleSheet("color: #cc0000; font-weight: bold;")

    def _render_scaled_frame(self):
        if not self.last_frame_pixmap:
            return

        scaled = self.last_frame_pixmap.scaled(
            self.game_frame_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.game_frame_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_scaled_frame()

    def closeEvent(self, event):
        self._stop_bot()
        event.accept()

    def _get_stylesheet(self) -> str:
        return """
            QMainWindow {
                background-color: #0a0a0a;
                color: #ffffff;
            }
            QWidget {
                background-color: #161616;
            }
            QLabel {
                color: #ffffff;
            }
            QPushButton {
                background-color: #262626;
                color: #ffffff;
                border: 1px solid #ff6600;
                border-radius: 4px;
                padding: 8px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #333333;
            }
            QPushButton:disabled {
                background-color: #1b1b1b;
                color: #777777;
                border-color: #444444;
            }
        """

    def _get_header_font(self) -> QFont:
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 120)
        return font


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AutonomousFighter")

    window = BotControlWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
