"""
AutonomousFighter Desktop Application - PyQt6
Modern aggressive combat interface with live game display
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import websockets
from PyQt6.QtCore import QThread, Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QDialog,
    QSpinBox,
    QDialogButtonBox,
    QFrame,
    QProgressBar,
    QGridLayout,
)


class WebSocketWorker(QThread):
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
                                    self.telemetry_received.emit(json.loads(message))
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


class WindowSettingsDialog(QDialog):
    """Dialog to customize window dimensions."""
    def __init__(self, parent=None, current_width: int = 650, current_height: int = 900):
        super().__init__(parent)
        self.setWindowTitle("Combat Window Settings")
        self.setStyleSheet(self._get_stylesheet())
        
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("CUSTOMIZE WINDOW")
        title.setStyleSheet("color: #E52224; font-size: 14px; font-weight: 900; letter-spacing: 2px;")
        layout.addWidget(title)
        
        # Width control
        width_layout = QHBoxLayout()
        width_label = QLabel("Width (px):")
        width_label.setStyleSheet("color: #E52224; font-weight: bold;")
        self.width_spin = QSpinBox()
        self.width_spin.setRange(400, 1000)
        self.width_spin.setValue(current_width)
        self.width_spin.setSingleStep(10)
        self.width_spin.setStyleSheet(self._spinbox_style())
        width_layout.addWidget(width_label)
        width_layout.addStretch()
        width_layout.addWidget(self.width_spin)
        layout.addLayout(width_layout)
        
        # Height control
        height_layout = QHBoxLayout()
        height_label = QLabel("Height (px):")
        height_label.setStyleSheet("color: #E52224; font-weight: bold;")
        self.height_spin = QSpinBox()
        self.height_spin.setRange(700, 1400)
        self.height_spin.setValue(current_height)
        self.height_spin.setSingleStep(10)
        self.height_spin.setStyleSheet(self._spinbox_style())
        height_layout.addWidget(height_label)
        height_layout.addStretch()
        height_layout.addWidget(self.height_spin)
        layout.addLayout(height_layout)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.setStyleSheet(self._button_style())
        layout.addWidget(buttons)
    
    def _spinbox_style(self) -> str:
        return """
            QSpinBox {
                background-color: #000000;
                color: #E52224;
                border: 2px solid #E52224;
                border-radius: 8px;
                padding: 6px 10px;
                font-weight: bold;
                min-width: 90px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QSpinBox:focus {
                border: 2px solid #FFEB3B;
            }
        """
    
    def _button_style(self) -> str:
        return """
            QDialogButtonBox QPushButton {
                background-color: #000000;
                color: #E52224;
                border: 2px solid #E52224;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
                min-width: 70px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QDialogButtonBox QPushButton:hover {
                background-color: #E52224;
                color: #1E1E1E;
            }
        """
    
    def _get_stylesheet(self) -> str:
        return """
            QDialog {
                background-color: #1E1E1E;
                color: #E52224;
                border: 2px solid #E52224;
            }
            QLabel {
                color: #E52224;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """
    
    def get_dimensions(self) -> tuple[int, int]:
        return self.width_spin.value(), self.height_spin.value()


class BotControlWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutonomousFighter - Live Combat")
        
        # Load saved dimensions or use modern defaults
        self.window_width, self.window_height = self._load_dimensions()
        self.settings_file = Path(__file__).resolve().parent / "window_settings.json"
        
        # Set proper geometry to prevent zoom cutting data
        self.setGeometry(100, 60, self.window_width, self.window_height)
        self.setMinimumSize(500, 800)
        self.setMaximumSize(1200, 1500)
        
        self.current_data: Dict[str, Any] = {}
        self.last_frame_pixmap: Optional[QPixmap] = None
        self.bot_process: Optional[subprocess.Popen] = None
        self.ws_worker: Optional[WebSocketWorker] = None
        self.project_root = Path(__file__).resolve().parent
        self._fields: Dict[str, QLabel] = {}
        self.pulse_phase = 0
        self.pulse_timer = None

        self._setup_ui()
        self.setStyleSheet(self._get_stylesheet())
        self._set_running_state(False)
    
    def _load_dimensions(self) -> tuple[int, int]:
        """Load saved window dimensions or return defaults."""
        settings_file = Path(__file__).resolve().parent / "window_settings.json"
        try:
            if settings_file.exists():
                with open(settings_file, "r") as f:
                    settings = json.load(f)
                    width = settings.get("width", 650)
                    height = settings.get("height", 900)
                    return max(500, min(1000, width)), max(800, min(1400, height))
        except Exception:
            pass
        return 650, 900  # Modern default dimensions
    
    def _save_dimensions(self):
        """Save current window dimensions to file."""
        settings = {
            "width": self.window_width,
            "height": self.window_height,
        }
        try:
            with open(self.settings_file, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass

    def _setup_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 1. HEADER SECTION
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 6, 10, 6)

        self.title_label = QLabel("AUTONOMOUS COMBAT INTERFACE")
        self.title_label.setObjectName("titleLabel")
        self.title_label.setFont(self._get_header_font())
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.pulse_dot = QLabel("●")
        self.pulse_dot.setObjectName("pulseDot")
        self.pulse_dot.setStyleSheet("font-size: 18px; color: #E52224;")
        header_layout.addWidget(self.pulse_dot)

        self.connection_indicator = QLabel("OFFLINE")
        self.connection_indicator.setObjectName("statusPill")
        self.connection_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.connection_indicator)

        main_layout.addWidget(header_frame)

        # 2. GAMEPLAY CAPTURE CONTAINER
        video_container = QFrame()
        video_container.setObjectName("videoContainer")
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(4, 4, 4, 4)

        self.game_frame_label = QLabel("TARGET ACQUISITION STANDBY\n\nPRESS START TO INITIATE BOT CONTROL")
        self.game_frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.game_frame_label.setObjectName("frameLabel")
        video_layout.addWidget(self.game_frame_label)
        
        main_layout.addWidget(video_container, stretch=4)

        # 3. TELEMETRY / AI-ML STATS SECTION (BELOW CAPTURE)
        self.telemetry_card = QFrame()
        self.telemetry_card.setObjectName("telemetryCard")
        telemetry_layout = QGridLayout(self.telemetry_card)
        telemetry_layout.setContentsMargins(12, 10, 12, 10)
        telemetry_layout.setSpacing(12)

        self._fields = {}

        # Row 0, Column 0: PERCEPTION AI (Title & Confidence)
        card_perception = QFrame()
        card_perception.setObjectName("subCardConfidence")
        perp_layout = QHBoxLayout(card_perception)
        perp_layout.setContentsMargins(10, 8, 10, 8)
        perp_layout.setSpacing(10)
        
        left_layout = QVBoxLayout()
        left_layout.setSpacing(2)
        
        lbl_p_title = QLabel("PERCEPTION CONFIDENCE")
        lbl_p_title.setObjectName("metricTitle")
        lbl_p_title.setStyleSheet("color: #FFEB3B; font-weight: bold;")
        
        self.confidence_status_lbl = QLabel("STANDBY")
        self.confidence_status_lbl.setObjectName("confidenceStatus")
        self.confidence_status_lbl.setStyleSheet("color: #757575; font-size: 10px; font-weight: bold;")
        
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 100)
        self.confidence_bar.setValue(0)
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setFixedHeight(8)
        self.confidence_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #1A1A1A;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E52224, stop:1 #FFEB3B);
                border-radius: 4px;
            }
        """)
        
        left_layout.addWidget(lbl_p_title)
        left_layout.addWidget(self.confidence_status_lbl)
        left_layout.addWidget(self.confidence_bar)
        perp_layout.addLayout(left_layout, stretch=3)
        
        self.confidence_value_lbl = QLabel("0%")
        self.confidence_value_lbl.setObjectName("confidenceValueGiant")
        self.confidence_value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.confidence_value_lbl.setStyleSheet("color: #FFEB3B; font-size: 22px; font-weight: 900; font-family: 'Consolas', monospace;")
        perp_layout.addWidget(self.confidence_value_lbl, stretch=1)
        
        telemetry_layout.addWidget(card_perception, 0, 0)

        # Row 0, Column 1: ACTION & DECISION
        card_action = QFrame()
        card_action.setObjectName("subCardAction")
        act_layout = QVBoxLayout(card_action)
        act_layout.setContentsMargins(10, 8, 10, 8)
        act_layout.setSpacing(4)
        
        lbl_a_title = QLabel("ACTIVE COMMAND")
        lbl_a_title.setObjectName("metricTitle")
        lbl_a_title.setStyleSheet("color: #E52224; font-weight: bold;")
        self._fields["action"] = QLabel("IDLE")
        self._fields["action"].setObjectName("metricValue")
        
        act_layout.addWidget(lbl_a_title)
        act_layout.addWidget(self._fields["action"])
        telemetry_layout.addWidget(card_action, 0, 1)

        # Row 0, Column 2: COMBO LOGIC
        card_combo = QFrame()
        card_combo.setObjectName("subCardCombo")
        combo_layout = QVBoxLayout(card_combo)
        combo_layout.setContentsMargins(10, 8, 10, 8)
        combo_layout.setSpacing(4)
        
        lbl_c_title = QLabel("STRATEGY / COMBO")
        lbl_c_title.setObjectName("metricTitle")
        lbl_c_title.setStyleSheet("color: #00B0FF; font-weight: bold;")
        self._fields["combo"] = QLabel("None")
        self._fields["combo"].setObjectName("metricValue")
        
        combo_layout.addWidget(lbl_c_title)
        combo_layout.addWidget(self._fields["combo"])
        telemetry_layout.addWidget(card_combo, 0, 2)

        # Row 1, Column 0: CORE DETECTION
        card_detection = QFrame()
        card_detection.setObjectName("subCardDetections")
        det_layout = QVBoxLayout(card_detection)
        det_layout.setContentsMargins(10, 8, 10, 8)
        det_layout.setSpacing(4)
        
        lbl_d_title = QLabel("ENTITIES DETECTED")
        lbl_d_title.setObjectName("metricTitle")
        lbl_d_title.setStyleSheet("color: #FFEB3B; font-weight: bold;")
        self._fields["detections"] = QLabel("None")
        self._fields["detections"].setObjectName("metricValue")
        
        det_layout.addWidget(lbl_d_title)
        det_layout.addWidget(self._fields["detections"])
        telemetry_layout.addWidget(card_detection, 1, 0)

        # Row 1, Column 1: PERFORMANCE core (FPS)
        card_perf = QFrame()
        card_perf.setObjectName("subCardFps")
        perf_layout = QVBoxLayout(card_perf)
        perf_layout.setContentsMargins(10, 8, 10, 8)
        perf_layout.setSpacing(4)
        
        lbl_f_title = QLabel("ENGINE FPS (PROC/CAP)")
        lbl_f_title.setObjectName("metricTitle")
        lbl_f_title.setStyleSheet("color: #E52224; font-weight: bold;")
        self._fields["fps"] = QLabel("0.0 / 0.0")
        self._fields["fps"].setObjectName("metricValue")
        
        perf_layout.addWidget(lbl_f_title)
        perf_layout.addWidget(self._fields["fps"])
        telemetry_layout.addWidget(card_perf, 1, 1)

        # Row 1, Column 2: LEARNING METRICS
        card_learning = QFrame()
        card_learning.setObjectName("subCardSystem")
        learn_layout = QVBoxLayout(card_learning)
        learn_layout.setContentsMargins(10, 8, 10, 8)
        learn_layout.setSpacing(4)
        
        lbl_l_title = QLabel("COMBAT SYSTEM")
        lbl_l_title.setObjectName("metricTitle")
        lbl_l_title.setStyleSheet("color: #00B0FF; font-weight: bold;")
        self._fields["system"] = QLabel("STREAK: 0 | LRN: 0 | STANDBY")
        self._fields["system"].setObjectName("metricValue")
        
        learn_layout.addWidget(lbl_l_title)
        learn_layout.addWidget(self._fields["system"])
        telemetry_layout.addWidget(card_learning, 1, 2)

        main_layout.addWidget(self.telemetry_card, stretch=0)

        # 4. CONTROL BUTTONS FOOTER
        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.setContentsMargins(0, 4, 0, 4)

        self.start_button = QPushButton("START BOT")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self._start_bot)
        controls.addWidget(self.start_button)

        self.stop_button = QPushButton("STOP BOT")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self._stop_bot)
        controls.addWidget(self.stop_button)
        
        self.settings_button = QPushButton("SETTINGS")
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.clicked.connect(self._open_settings)
        controls.addWidget(self.settings_button)

        main_layout.addLayout(controls)

        # Pulse timer properties
        self.pulse_phase = 0
        self.pulse_timer = None
        self._start_pulse_animation()

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
    
    def _open_settings(self):
        """Open the window settings dialog."""
        dialog = WindowSettingsDialog(self, self.window_width, self.window_height)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_width, new_height = dialog.get_dimensions()
            self._apply_dimensions(new_width, new_height)
    
    def _apply_dimensions(self, width: int, height: int):
        """Apply new window dimensions and save them."""
        self.window_width = width
        self.window_height = height
        self._save_dimensions()
        self.resize(width, height)

    def _start_bot(self):
        if self.bot_process is not None and self.bot_process.poll() is None:
            return

        self.current_data = {}
        self.last_frame_pixmap = None
        self.game_frame_label.setText("LOADING COMBAT ENVIRONMENT...")
        self.game_frame_label.setPixmap(QPixmap())
        self._reset_fields()

        cmd = [sys.executable, "main.py"]
        try:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            self.bot_process = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                creationflags=creationflags,
            )
        except Exception as exc:
            self.game_frame_label.setText(f"Failed to start: {exc}")
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
        self.game_frame_label.setText("TARGET ACQUISITION STANDBY\n\nPRESS START TO INITIATE BOT CONTROL")
        self._reset_fields()
        self._set_running_state(False)

    def _set_running_state(self, running: bool):
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.connection_indicator.setText("ONLINE" if running else "OFFLINE")
        if running:
            self.connection_indicator.setStyleSheet("""
                background-color: rgba(0, 176, 255, 0.15);
                color: #00B0FF;
                border: 2px solid #00B0FF;
            """)
        else:
            self.connection_indicator.setStyleSheet("""
                background-color: rgba(229, 34, 36, 0.15);
                color: #E52224;
                border: 2px solid #E52224;
            """)

    def _on_telemetry(self, data: Dict[str, Any]):
        """Handle incoming telemetry data - display game frame and telemetry."""
        self.current_data = data
        
        # Display the game frame (clear gameplay capture with no overlay text)
        encoded = data.get("live_frame_jpeg")
        if encoded:
            try:
                frame_data = base64.b64decode(encoded)
                pixmap = QPixmap()
                if pixmap.loadFromData(frame_data):
                    if self.game_frame_label.text():
                        self.game_frame_label.setText("")  # Clean text label completely
                    self.last_frame_pixmap = pixmap
                    self._render_scaled_frame()
            except Exception:
                pass

        # Update stats text below
        try:
            # 1. Confidence Progress Bar and Labels
            confidence = float(data.get("confidence_score", 0.0))
            confidence_pct = int(confidence * 100)
            self.confidence_bar.setValue(confidence_pct)
            self.confidence_value_lbl.setText(f"{confidence_pct}%")
            
            # Update status text and color dynamically
            if confidence == 0:
                self.confidence_status_lbl.setText("STANDBY")
                self.confidence_status_lbl.setStyleSheet("color: #757575; font-size: 10px; font-weight: bold;")
            elif confidence < 0.4:
                self.confidence_status_lbl.setText("SEARCHING...")
                self.confidence_status_lbl.setStyleSheet("color: #E52224; font-size: 10px; font-weight: bold;")
            elif confidence < 0.7:
                self.confidence_status_lbl.setText("ACQUIRING")
                self.confidence_status_lbl.setStyleSheet("color: #FFEB3B; font-size: 10px; font-weight: bold;")
            else:
                self.confidence_status_lbl.setText("TARGET LOCKED")
                self.confidence_status_lbl.setStyleSheet("color: #00B0FF; font-size: 10px; font-weight: bold;")

            # 2. Current Action
            action = data.get("current_action", "IDLE")
            self._fields["action"].setText(action)

            # 3. Selected Combo / Strategy
            combo = data.get("selected_combo") or "None"
            self._fields["combo"].setText(combo)

            # 4. Detections
            detections = data.get("detections") or []
            labels = [d.get("label", "unknown") for d in detections]
            if labels:
                counts = {}
                for l in labels:
                    counts[l] = counts.get(l, 0) + 1
                det_parts = [f"{v} {k}" for k, v in counts.items()]
                det_str = ", ".join(det_parts)
                self._fields["detections"].setText(det_str)
            else:
                self._fields["detections"].setText("No Entities")

            # 5. Engine / Capture FPS
            fps = float(data.get("fps", 0.0))
            capture_fps = float(data.get("capture_fps", 0.0))
            self._fields["fps"].setText(f"{fps:.1f} / {capture_fps:.1f}")

            # 6. Combat system metrics
            streak = int(data.get("attack_streak", 0))
            fight_mem = data.get("fight_memory") or {}
            learned_combos = int(fight_mem.get("learned_combo_count", 0))
            ep_active = fight_mem.get("episode_active", False)
            ep_status = "ACTIVE" if ep_active else "STANDBY"
            self._fields["system"].setText(f"STREAK: {streak} | LRN: {learned_combos} | {ep_status}")
            
        except Exception as e:
            print(f"Error updating telemetry: {e}")

    def _on_connection_status(self, connected: bool):
        self.connection_indicator.setText("ONLINE" if connected else "OFFLINE")
        if connected:
            self.connection_indicator.setStyleSheet("""
                background-color: rgba(0, 176, 255, 0.15);
                color: #00B0FF;
                border: 2px solid #00B0FF;
            """)
        else:
            self.connection_indicator.setStyleSheet("""
                background-color: rgba(229, 34, 36, 0.15);
                color: #E52224;
                border: 2px solid #E52224;
            """)

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

    def _reset_fields(self) -> None:
        """Reset telemetry fields to default standby values."""
        if hasattr(self, '_fields') and self._fields:
            if "action" in self._fields:
                self._fields["action"].setText("STANDBY")
            if "combo" in self._fields:
                self._fields["combo"].setText("None")
            if "detections" in self._fields:
                self._fields["detections"].setText("None")
            if "fps" in self._fields:
                self._fields["fps"].setText("0.0 / 0.0")
            if "system" in self._fields:
                self._fields["system"].setText("STREAK: 0 | LRN: 0 | STANDBY")
        if hasattr(self, 'confidence_bar') and self.confidence_bar:
            self.confidence_bar.setValue(0)
        if hasattr(self, 'confidence_value_lbl') and self.confidence_value_lbl:
            self.confidence_value_lbl.setText("0%")
        if hasattr(self, 'confidence_status_lbl') and self.confidence_status_lbl:
            self.confidence_status_lbl.setText("STANDBY")
            self.confidence_status_lbl.setStyleSheet("color: #757575; font-size: 10px; font-weight: bold;")

    def _start_pulse_animation(self):
        """Start continuous pulse animation on the telemetry card and status indicator."""
        if self.pulse_timer is not None:
            return
        
        self.pulse_timer = QTimer()
        self.pulse_timer.timeout.connect(self._update_pulse)
        self.pulse_timer.start(80)  # Update every 80ms for responsive animation
    
    def _update_pulse(self):
        """Update the pulse effect on telemetry card and pulse dot."""
        if not hasattr(self, 'telemetry_card') or self.telemetry_card is None:
            return
        
        self.pulse_phase = (self.pulse_phase + 1) % 20
        intensity = (20 - abs(self.pulse_phase - 10)) / 10.0  # Creates pulse 0-1.0-0
        
        # Pulse alpha/opacity of the border
        alpha = int(100 + 155 * intensity)
        color_hex = f"rgba(229, 34, 36, {alpha/255.0:.2f})" # Pulse with #E52224
        
        # We can also pulse the connection pulse dot
        if hasattr(self, 'pulse_dot') and self.pulse_dot is not None:
            if self.connection_indicator.text() == "ONLINE":
                dot_color = f"rgba(0, 176, 255, {alpha/255.0:.2f})" # Blue online pulse
            else:
                dot_color = f"rgba(229, 34, 36, {alpha/255.0:.2f})" # Red offline pulse
            self.pulse_dot.setStyleSheet(f"color: {dot_color}; font-size: 18px; font-weight: bold;")

        style = f"""
            QFrame#telemetryCard {{
                background-color: #262626;
                border: 2px solid {color_hex};
                border-radius: 10px;
            }}
        """
        self.telemetry_card.setStyleSheet(style)

    def _get_stylesheet(self) -> str:
        return """
            QMainWindow {
                background-color: #1E1E1E;
                border: 3px solid #E52224;
            }
            QWidget {
                background-color: #1E1E1E;
            }
            QFrame#headerFrame {
                border-bottom: 2px solid #E52224;
                background-color: #262626;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QFrame#videoContainer {
                border: 3px solid #E52224;
                border-radius: 12px;
                background-color: #000000;
            }
            QFrame#telemetryCard {
                background-color: #262626;
                border: 2px solid #E52224;
                border-radius: 10px;
            }
            
            /* Subcards with unique aggressive neon left borders */
            QFrame#subCardConfidence {
                background-color: #2D2D2D;
                border: 1px solid #3E3E3E;
                border-left: 5px solid #FFEB3B; /* Yellow */
                border-radius: 6px;
            }
            QFrame#subCardConfidence:hover {
                border-color: #FFEB3B;
                background-color: #383838;
            }
            
            QFrame#subCardAction {
                background-color: #2D2D2D;
                border: 1px solid #3E3E3E;
                border-left: 5px solid #E52224; /* Red */
                border-radius: 6px;
            }
            QFrame#subCardAction:hover {
                border-color: #E52224;
                background-color: #383838;
            }
            
            QFrame#subCardCombo {
                background-color: #2D2D2D;
                border: 1px solid #3E3E3E;
                border-left: 5px solid #00B0FF; /* Blue */
                border-radius: 6px;
            }
            QFrame#subCardCombo:hover {
                border-color: #00B0FF;
                background-color: #383838;
            }
            
            QFrame#subCardDetections {
                background-color: #2D2D2D;
                border: 1px solid #3E3E3E;
                border-left: 5px solid #FFEB3B; /* Yellow */
                border-radius: 6px;
            }
            QFrame#subCardDetections:hover {
                border-color: #FFEB3B;
                background-color: #383838;
            }
            
            QFrame#subCardFps {
                background-color: #2D2D2D;
                border: 1px solid #3E3E3E;
                border-left: 5px solid #E52224; /* Red */
                border-radius: 6px;
            }
            QFrame#subCardFps:hover {
                border-color: #E52224;
                background-color: #383838;
            }
            
            QFrame#subCardSystem {
                background-color: #2D2D2D;
                border: 1px solid #3E3E3E;
                border-left: 5px solid #00B0FF; /* Blue */
                border-radius: 6px;
            }
            QFrame#subCardSystem:hover {
                border-color: #00B0FF;
                background-color: #383838;
            }

            QLabel {
                color: #ffffff;
                background-color: transparent;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QLabel#titleLabel {
                color: #E52224;
                font-weight: bold;
                letter-spacing: 2px;
            }
            QLabel#statusPill {
                background-color: #1E1E1E;
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: bold;
                letter-spacing: 1.5px;
                font-size: 11px;
                font-family: 'Consolas', monospace;
            }
            QLabel#frameLabel {
                background-color: #000000;
                color: #E52224;
                padding: 12px;
                font-weight: bold;
                letter-spacing: 1px;
                font-size: 13px;
                font-family: 'Consolas', monospace;
            }
            QLabel#metricTitle {
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1.2px;
            }
            QLabel#metricValue {
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Consolas', monospace;
            }
            
            /* Neon aggressive control buttons */
            QPushButton {
                background-color: rgba(229, 34, 36, 0.03);
                color: #E52224;
                border: 2px solid #E52224;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 12px;
                letter-spacing: 1.5px;
                font-family: 'Consolas', monospace;
            }
            QPushButton:hover {
                background-color: #E52224;
                color: #1E1E1E;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
                border-color: #b71c1c;
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: #1E1E1E;
                color: #555555;
                border: 2px solid #555555;
            }
            
            /* Start button override: Red */
            QPushButton#startButton {
                color: #E52224;
                border-color: #E52224;
                background-color: rgba(229, 34, 36, 0.03);
            }
            QPushButton#startButton:hover {
                background-color: #E52224;
                color: #1E1E1E;
            }
            QPushButton#startButton:pressed {
                background-color: #b71c1c;
                border-color: #b71c1c;
                color: #ffffff;
            }

            /* Stop button override: Blue */
            QPushButton#stopButton {
                color: #00B0FF;
                border-color: #00B0FF;
                background-color: rgba(0, 176, 255, 0.03);
            }
            QPushButton#stopButton:hover {
                background-color: #00B0FF;
                color: #1E1E1E;
            }
            QPushButton#stopButton:pressed {
                background-color: #0091ea;
                border-color: #0091ea;
                color: #ffffff;
            }

            /* Settings button override: Yellow */
            QPushButton#settingsButton {
                color: #FFEB3B;
                border-color: #FFEB3B;
                background-color: rgba(255, 235, 59, 0.03);
            }
            QPushButton#settingsButton:hover {
                background-color: #FFEB3B;
                color: #1E1E1E;
            }
            QPushButton#settingsButton:pressed {
                background-color: #fdd835;
                border-color: #fdd835;
                color: #1E1E1E;
            }
        """

    def _get_header_font(self) -> QFont:
        font = QFont("Consolas", 12, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 115)
        return font


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AutonomousFighter")

    window = BotControlWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()