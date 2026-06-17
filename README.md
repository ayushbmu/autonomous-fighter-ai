# AutonomousFighter 🤖🥊

An advanced, production-grade autonomous combat engine designed for **Shadow Fight Arena**, built using a high-performance Python and C++ stack. The system combines real-time Computer Vision, Reinforcement Learning, and low-level Windows input automation to orchestrate intelligent, human-like combat gameplay.

---

## 🌟 Core Technology Stack

The engine's intelligence and reactivity are driven by three core pillars:

1. **Visual Perception (OpenCV & YOLOv8)**
   * **Target Detection:** A custom-trained **YOLOv8** model processes real-time screen captures to locate the player and enemy, drawing bounding boxes and estimating coordinates.
   * **HUD Processing:** Custom **OpenCV** masking operations parse the screen’s head-up display in real time, calculating the health percentages of both fighters and estimating the shadow energy meter using HSV thresholding.
   * **Telemetry Pipeline:** Integrates a multi-threaded frame capture wrapper (`mss`) running asynchronously to feed the perception pipeline without blocking the main combat thread.

2. **Decision Making (Reinforcement Learning & Strategy Memory)**
   * **Gymnasium Environment:** A custom-designed `AutonomousFighterEnv` models the combat as a Markov Decision Process (MDP) with a 10-dimensional continuous observation space and a discrete action space mapping to combat moves.
   * **PPO Training:** Employs **Stable-Baselines3** to train Proximal Policy Optimization (PPO) policies, utilizing reward shaping designed around aggression, damage ratios, combo streaks, and pressure metrics.
   * **Adaptive Combo Learner:** A strategy memory system (`strategy_memory.py`) dynamically analyzes match results, tracks opponent styles (e.g., zoning, rushdown, aerial), and selects optimal combo sequences to punish opponent patterns in real time.

3. **Input Injection (C++ SendInput DLL)**
   * **High Performance:** Standard Python keyboard simulation libraries suffer from high latency and predictability. This project uses a custom C++ DLL compiled with the Windows `SendInput` API.
   * **Anti-Detection Mechanics:** The Python ctypes wrapper (`InputExecutor`) injects microsecond-level randomized delay and jitter (human-like tap timings) to mimic human reactions and avoid simple anti-cheat pattern detection.

---

## 📂 Project Architecture

The workspace is organized into modular components that separate concerns across the perception-action loop:

```text
AutonomousFighter/
├── api/                    # FastAPI WebSocket server for real-time telemetry streaming
├── brain/                  # RL Gymnasium environments, policy wrappers, and strategy memory
│   ├── models/             # Directory for trained PPO models (.zip format)
│   └── learning/           # Persisted strategy memory state and fight telemetry histories
├── muscles/                # Low-level C++ input automation DLL and ctypes wrapper
│   ├── src/ & include/     # C++ SendInput source code
│   └── CMakeLists.txt      # Build configuration for compilation
├── perception/             # Vision pipeline (Screen capture, YOLO detector, HUD parser)
├── common/                 # Shared settings loader and logging configurations
├── scripts/                # Launch, test, build, and bootstrap automation utilities
├── main.py                 # Core orchestrator loop binding perception, brain, and muscles
├── ui_app.py               # Modern PyQt6 native desktop dashboard
├── requirements.txt        # Python dependency list
└── .env.example            # Environment configuration template
```

---

## 🛠️ Installation & Setup

Follow these steps to compile the native modules and configure the combat engine environment on Windows:

### 1. Clone & Set Up the Python Environment
Initialize a Python virtual environment and install dependencies:
```powershell
# Create virtual environment
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```
*Alternatively, you can run the bootstrap script:*
```powershell
.\scripts\bootstrap.ps1
```

### 2. Configure Environment Variables
Copy the template configuration file to a live `.env` file:
```powershell
copy .env.example .env
```
Open `.env` in your editor and adjust the settings:
* **`AF_YOLO_MODEL`**: The filename of your YOLOv8 weights (e.g., `yolov8n.pt` or `yolov8m.pt`).
* **`AF_CAPTURE_LEFT`, `AF_CAPTURE_TOP`, `AF_CAPTURE_WIDTH`, `AF_CAPTURE_HEIGHT`**: Target region dimensions matching your game display window.
* **`AF_TARGET_FPS`**: The target execution rate of the perception-action loop.

### 3. Download Model Weights
Model weights must be acquired separately and are **not** tracked in this repository due to file size constraints.
* Download the desired **YOLOv8** model weights (e.g., `yolov8n.pt` or `yolov8m.pt`) from the [Ultralytics Release page](https://github.com/ultralytics/assets/releases).
* Place the `.pt` file(s) directly into the root directory of this project (`AutonomousFighter/`).

### 4. Compile the Muscles DLL (C++)
The low-level input automation requires compiling the native C++ DLL. Make sure you have Visual Studio (with C++ build tools) and CMake installed:
```powershell
cd muscles
cmake -S . -B build
cmake --build build --config Release
```
This produces the compiled library:
`muscles/build/Release/autonomous_fighter_muscles.dll`

---

## 🚀 Running the Engine

The engine provides an automated startup script that locates the active game window and spins up all backend/frontend processes.

### Launching with UI (PyQt6 Desktop App)
Run the launcher script:
```powershell
python launcher.py
```
This launcher automatically:
1. Locates the active **Shadow Fight Arena** game window.
2. Launches the backend combat orchestrator loop.
3. Spins up the FastAPI WebSocket server (`api/`).
4. Launches the native dark-themed PyQt6 Control Panel displaying:
   * **Live Gameplay Feed:** Live frame rendering with YOLO bounding boxes and HUD ROI overlays.
   * **Perception Confidence:** Target lock status bar.
   * **Active Commands:** Live combat actions executed by the agent.
   * **Strategy Metrics:** Combo sequences and strategy styles chosen by the adaptive learner.

---

## 🧠 Training & Evaluation

To retrain the PPO brain policy on custom combat scenarios:

```powershell
# Train the PPO agent
python -m brain.train_ppo --timesteps 1000000 --output-dir brain/models --n-envs 4 --device cuda

# Evaluate a trained policy model
python -m brain.evaluate --model brain/models/ppo_aggressive_fighter.zip --episodes 20 --max-steps 1500
```

---

## 🧪 CI & Verification

Unit and integration tests are located in the `tests/` directory. Run them to verify telemetry, settings, and state extraction:
```powershell
# Run backend tests
pytest -q
```
*Alternatively, execute the test script:*
```powershell
.\scripts\test.ps1
```
