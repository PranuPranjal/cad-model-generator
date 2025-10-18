# CAD Model Generator

A small prototype web app that uses a local LLM (via Ollama) to generate CadQuery scripts and export 3D models (STL and STEP). The backend runs a FastAPI service that asks the LLM to produce a CadQuery script, executes the generated script in a controlled background task, and exports the results. The frontend is a Vite + React app that can send prompts and view generated STL files.

## Features

- Ask an LLM to generate a CadQuery script from a natural-language prompt.
- Background execution of generated CadQuery code to produce STL and STEP files.
- Simple REST API to request generation, check status, and download outputs.
- Minimal React frontend (Vite) to submit prompts and preview STL files.

## Repository Structure

### Backend

- **FastAPI backend, CadQuery execution and exported model files.**
  - `app.py`: FastAPI application; endpoints: `/api/generate`, `/api/generation-status`, `/output.stl`, `/output.step`.
  - `requirements.txt`: Python package requirements used by the project.
  - `generated_model_script.txt`: (runtime) the last model script produced by the LLM.
  - `output_*.stl` / `output_*.step`: example/generated model files produced by the app.

### Frontend

- **Vite + React frontend that communicates with the backend and displays STL models.**

## Quick Start (Windows / PowerShell)

The commands below assume you have Python and Node.js installed on your system. Adjust commands for your environment if needed.

### Backend - Create a Conda Environment and Install Dependencies

This project is best run using a Conda environment to handle CadQuery's complex dependencies.

```powershell
# Navigate to the backend directory
cd .\backend

# 1. Create a new Conda environment (e.g., named "cad_api")
conda create -n cad_api python=3.10

# 2. Activate the new environment
conda activate cad_api

# 3. Install the core Python packages from requirements.txt
pip install -r requirements.txt

# 4. Install the required CadQuery extension libraries (cq_gears and cq_warehouse)
pip install "git+https://github.com/meadiode/cq_gears.git" "git+https://github.com/gumyr/cq_warehouse.git"
```

**Note:** CadQuery and its extensions are pre-installed in this environment. The `app.py` server assumes these libraries (`cadquery`, `cq_gears`, `cq_warehouse`) are available in the environment and does not install them at runtime.

### Run Ollama (Required)

This project expects an Ollama server running locally at `http://localhost:11434`. The app is configured to use the Hugging Face model `hf.co/Pranu999/cad-gen:Q4_K_M`. Start Ollama with that model, for example:

```powershell
ollama run hf.co/Pranu999/cad-gen:Q4_K_M
```

If you use a different model or host/port, update `MODEL_NAME` and `OLLAMA_URL` in `backend/app.py`.

### Start the Backend

```powershell
# From backend folder, with the virtualenv activated
python app.py
```

The backend runs Uvicorn at `http://0.0.0.0:5000` by default (see `app.py`).

### Frontend - Install and Run

```powershell
cd ..\frontend
npm install
npm run dev
```

The Vite dev server will show the frontend UI (by default at `http://localhost:5173`). The frontend can POST prompts to the backend and preview generated STLs.

## API / Usage

### POST `/api/generate`

- **Body:** JSON `{ "prompt": "describe the model you want" }`
- **Response:** Acknowledges generation started. Backend writes the returned CadQuery script to `generated_model_script.txt` and runs it in a background task to export files.

### GET `/api/generation-status`

- Returns JSON with status (`pending`/`processing`/`complete`/`error`), optional `error_message`, and filenames (`stl_filename`, `step_filename`) when available.

### GET `/output.stl?filename=<name>`

- Download/serve the generated STL file (use the exact filename returned by `/api/generation-status`).

### GET `/output.step?filename=<name>`

- Download/serve the generated STEP file.

## Example Flow

1. POST a prompt to `/api/generate`.
2. Poll `/api/generation-status` until status becomes `complete` and note the `stl_filename`.
3. Download the file with `/output.stl?filename=<stl_filename>`.

## Notes and Important Implementation Details

- The backend intentionally writes the LLM-produced CadQuery script to `generated_model_script.txt` (a `.txt` file) instead of a `.py` file. This avoids triggering Uvicorn's auto-reload when the file is updated, which would otherwise interrupt the background task that runs the script.
- The executed script must expose a CadQuery object named exactly `result` (for example: `result = cq.Workplane("XY").box(10, 10, 10)`). The backend only executes the script and expects `result` to be either a `cq.Workplane` or a `cq.Shape`.
- The backend exports both an STL and a STEP file for each successful generation and saves them in the `backend/` folder with names like `output_<timestamp>.stl` and `output_<timestamp>.step`.

## Troubleshooting

- **CadQuery Installation:** If `pip install cadquery` fails or the exporter fails at runtime, follow the official CadQuery installation instructions for your OS. On Windows, using a conda-based environment can simplify native dependency issues.
- **Ollama Errors:** If the backend cannot reach Ollama, ensure the Ollama service is running locally and accessible at `http://localhost:11434`. Check that the model name configured in `app.py` (`MODEL_NAME`) matches a model you have available.
- **Permissions / Files:** If the backend fails to write or serve output files, check that the running Python process has write permissions to the `backend/` folder.

## Example Files

Several exported example files are included in the `backend/` folder (`output_*.stl`, `output_*.step`). These were produced by the app during development and can be used to test the frontend viewer.

## License & Contact

This repository is a prototype. No license file is included. For questions or contributions, open an issue or submit a pull request in the repository.