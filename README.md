# AutonomousFighter

Production-grade autonomous fighting agent with pure Python/C++ stack:

- `perception`: Python OpenCV + YOLOv8 pipeline
- `brain`: Gymnasium + Stable-Baselines3 PPO training/runtime
- `muscles`: C++ SendInput DLL with jittered input timing
- `api`: FastAPI WebSocket telemetry server
- `ui_app.py`: PyQt6 native desktop application (no browser required)
- `main.py`: orchestrator loop

All four phases are implemented:

- Phase 1: C++ input DLL + Python ctypes wrapper
- Phase 2: real-time capture + YOLO detection + relative state extraction + annotated live feed
- Phase 3: Gymnasium environment + PPO train/eval pipeline + runtime policy selection
- Phase 4: FastAPI WebSocket API + PyQt6 native desktop UI

## Project Layout

```text
AutonomousFighter/
├── perception/          # Vision pipeline (OpenCV + YOLO)
├── brain/               # RL environment & policy (Gymnasium + PPO)
├── muscles/             # C++ input controller + Python wrapper
├── api/                 # FastAPI WebSocket server
├── scripts/             # Build & launch scripts
├── main.py              # Orchestrator loop
├── ui_app.py            # PyQt6 desktop UI (pure Python)
└── requirements.txt     # Python dependencies
```

## Quick Start

### 1) Launch the System

```powershell
# Automatic launch (finds Shadow Fight Arena window)
python launcher.py

# Or with specific game window
python launcher.py --window-title "My Game Title"
```

The launcher will:
- ✓ Start the bot backend (Python + C++)
- ✓ Launch the native desktop UI (PyQt6)
- ✓ Connect to the game window
- ✓ Begin capturing and processing

### 2) Desktop UI Features

- **Live Game Feed**: Real-time capture with YOLO bounding boxes
- **Telemetry**: FPS, current action, confidence, attack streak
- **Detections Table**: Live detection data with coordinates
- **Status Indicator**: Connection status (Online/Offline)
- **Dark Theme**: Orange/dark modern interface

```powershell
cd C:\Users\Ayush\AutonomousFighter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Or use the bootstrap script:

```powershell
cd C:\Users\Ayush\AutonomousFighter
./scripts/bootstrap.ps1
```

Optional: create a runtime environment file from `.env.example` and edit values.

## 2) Build Muscles DLL (C++)

```powershell
cd C:\Users\Ayush\AutonomousFighter\muscles
cmake -S . -B build
cmake --build build --config Release
```

Expected output DLL:

- `muscles/build/Release/autonomous_fighter_muscles.dll`

## 3) Smoke Test Native Input Wrapper

```powershell
cd C:\Users\Ayush\AutonomousFighter
python -m muscles.python_wrapper
```

## 4) Train PPO Brain

```powershell
cd C:\Users\Ayush\AutonomousFighter
python -m brain.train_ppo
```

Advanced training options:

```powershell
cd C:\Users\Ayush\AutonomousFighter
python -m brain.train_ppo --timesteps 1000000 --output-dir brain/models --n-envs 4 --device cuda
```

Run evaluation:

```powershell
cd C:\Users\Ayush\AutonomousFighter
python -m brain.evaluate --model brain/models/ppo_aggressive_fighter.zip --episodes 20 --max-steps 1500
```

## 5) Run Full Orchestrator + API

```powershell
cd C:\Users\Ayush\AutonomousFighter
python main.py --dll muscles/build/Release/autonomous_fighter_muscles.dll --yolo yolov8n.pt --left 0 --top 0 --width 1280 --height 720 --target-fps 30
```

Model-driven runtime with active window tracking:

```powershell
cd C:\Users\Ayush\AutonomousFighter
python main.py --dll muscles/build/Release/autonomous_fighter_muscles.dll --model brain/models/ppo_aggressive_fighter.zip --window-title "Your Game Window" --target-fps 30
```

You can now override most runtime values using environment variables:

- `AF_API_HOST`, `AF_API_PORT`
- `AF_YOLO_MODEL`
- `AF_CAPTURE_LEFT`, `AF_CAPTURE_TOP`, `AF_CAPTURE_WIDTH`, `AF_CAPTURE_HEIGHT`
- `AF_TARGET_FPS`
- `AF_KEY_TAP_MIN_MS`, `AF_KEY_TAP_MAX_MS`

You can also run the telemetry API standalone:

```powershell
cd C:\Users\Ayush\AutonomousFighter
python -m api.run
```

## 6) Run Dashboard

```powershell
cd C:\Users\Ayush\AutonomousFighter\ui
npm install
npm run dev
```

Dashboard URL:

- `http://localhost:3000`

WebSocket source:

- `ws://127.0.0.1:8000/ws`

## Notes

- The perception parser expects YOLO classes like `player` and `enemy`. Update class names in `perception/state_extractor.py` to match your trained labels.
- Reward shaping in `brain/reward.py` heavily biases offense: pressure, combos, and forward movement.
- Key mappings are configured in `main.py` and should be aligned with in-game controls.
- API health and connection stats endpoints are available at `/health` and `/stats`.
- The dashboard supports WebSocket auto-reconnect and displays the annotated YOLO live feed from the backend.
- Fight learning artifacts are written to `brain/learning/episodes/`, including per-fight screenshots and `summary.json` files.
- Labeled training data is written to `brain/learning/labels/<episode_id>/images/` and `brain/learning/labels/<episode_id>/labels/` as YOLO-style player/enemy annotations.
- Opponent-style memory is persisted in `brain/learning/strategy_state.json` and used at runtime to pick punish combos for aerial, zoning, rushdown, and scramble patterns.
- Runtime strategy now includes adaptive aggression modes, dynamic combo cadence, anti-repeat combo lockouts, and feint injection to avoid predictable pressure loops.

## CI and Verification

- Python CI workflow: `.github/workflows/python-ci.yml`
- UI CI workflow: `.github/workflows/ui-ci.yml`

Run backend tests locally:

```powershell
cd C:\Users\Ayush\AutonomousFighter
pytest -q
```

Or use:

```powershell
cd C:\Users\Ayush\AutonomousFighter
./scripts/test.ps1
```

## Dev and Release Automation

Launch backend + UI together:

```powershell
cd C:\Users\Ayush\AutonomousFighter
./scripts/dev-up.ps1 -Dll "muscles/build/Release/autonomous_fighter_muscles.dll" -Yolo "yolov8n.pt"
```

Create a release zip:

```powershell
cd C:\Users\Ayush\AutonomousFighter
./scripts/release.ps1
```
