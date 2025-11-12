\# 🧩 CAD Model Generator

A small prototype **web app** that uses a **local LLM (via Ollama)** to generate **CadQuery scripts** and export **3D models (STL and STEP)**.

The backend runs a **FastAPI** service that asks the LLM to produce a CadQuery script, executes it in a controlled background task, and exports the results.  
The frontend is a **Vite + React** app that can send prompts and view generated STL files.

---

## ✨ Features

- 🧠 Ask an LLM to generate a **CadQuery script** from a natural-language prompt.  
- ⚙️ Background execution of generated CadQuery code to produce **STL** and **STEP** files.  
- 🔗 Simple **REST API** to request generation, check status, and download outputs.  
- 💻 Minimal **React (Vite)** frontend to submit prompts and preview STL models.  
- 🧶 *(Optional)* Generate **G-code** from STL files using a detected local slicer (PrusaSlicer or CuraEngine).

---

## 🗂️ Repository Structure

### **Backend**

Handles:
- FastAPI app  
- CadQuery execution  
- Model export (STL/STEP)  
- Optional G-code generation

```

backend/
├── app.py                  # FastAPI application
├── requirements.txt        # Python dependencies
├── generated_model_script.txt  # (runtime) last model script from LLM
├── output_*.stl / .step    # Generated model files

```

### **Frontend**

A **Vite + React** app that communicates with the backend and displays STL models.

```

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── App.jsx
├── package.json
└── vite.config.js

````

---

## ⚡ Quick Start (Windows / PowerShell)

> These commands assume you have **Python** and **Node.js** installed.  
> Adjust as needed for your system.

---

### 🐍 1. Backend Setup (with Conda)

**1. Navigate to backend folder:**
```bash
cd .\backend
````

**2. Create a Conda environment:**

```bash
conda create -n cad_api python=3.10
```

**3. Activate it:**

```bash
conda activate cad_api
```

**4. Install core dependencies:**

```bash
pip install -r requirements.txt
```

**5. Install CadQuery extension libraries:**

```bash
pip install "git+https://github.com/meadiode/cq_gears.git" "git+https://github.com/gumyr/cq_warehouse.git"
```

> 📝 Note: CadQuery and its extensions are expected to be available in this environment.

---

### 🧠 2. Run Ollama (Required)

Ensure **Ollama** is running locally at:
**[http://localhost:11434](http://localhost:11434)**

Start Ollama with the required model:

```bash
ollama run llama-cad:latest
```

If you use a different model or host, update `MODEL_NAME` and `OLLAMA_URL` in **backend/app.py**.

---

### 🧰 3. Install a Slicer (Optional, for G-code)

To generate **G-code**, install a compatible slicer like **PrusaSlicer**.

* 📥 Download: [PrusaSlicer](https://www.prusa3d.com/page/prusaslicer_424/)
* 🧭 Default Install Path:
  `C:\Program Files\Prusa3D\PrusaSlicer`

If installed elsewhere, add the folder containing `prusa-slicer-console.exe` to your **PATH** environment variable.

If no slicer is detected, the backend uses a basic fallback generator (not suitable for printing).

---

### 🚀 4. Start the Backend

From the backend folder:

```bash
source .venv/Scripts/activate
python app.py
```

> The backend runs at **[http://0.0.0.0:5000](http://0.0.0.0:5000)** by default.

---

### 💻 5. Frontend Setup

Open a new terminal and run:

```bash
cd ..\frontend
npm install
npm run dev
```

The frontend runs at:
👉 **[http://localhost:5173](http://localhost:5173)**

---

## 🔌 API / Usage

### **POST /api/generate**

**Body:**

```json
{ "prompt": "describe the model you want" }
```

**Response:** Acknowledges generation started.

Backend writes the CadQuery script to `generated_model_script.txt` and runs it in a background task.

---

### **GET /api/generation-status**

Returns:

```json
{
  "status": "complete",
  "stl_filename": "output_12345.stl",
  "step_filename": "output_12345.step",
  "error_message": null
}
```

---

### **GET /output.stl?filename=<name>**

Downloads the generated STL file.

### **GET /output.step?filename=<name>**

Downloads the generated STEP file.

---

### **POST /api/generate-gcode**

**Body:**

```json
{
  "filename": "output_12345.stl",
  "layer_height": 0.2,
  "infill_density": 20,
  "print_speed": 60,
  "nozzle_temp": 200,
  "bed_temp": 60
}
```

**Response:**

```json
{
  "success": true,
  "gcode_filename": "output_12345.gcode"
}
```

---

### **GET /api/download-gcode/{filename}**

Downloads the generated G-code file.

---

## 🔄 Example Flow

1. **POST** a prompt to `/api/generate`
2. **Poll** `/api/generation-status` until `"status": "complete"`
3. **Download** the STL file via `/output.stl`
4. *(Optional)* **Generate G-code** with `/api/generate-gcode`
5. *(Optional)* **Download G-code** via `/api/download-gcode/{filename}`

---

## ⚠️ Notes & Implementation Details

* The backend writes the LLM-generated CadQuery code to
  `generated_model_script.txt` (not `.py`) to avoid Uvicorn auto-reload.
* The executed script must define:

  ```python
  result = cq.Workplane("XY").box(10, 10, 10)
  ```
* The backend expects `result` to be a **CadQuery Workplane or Shape**.
* Both `.stl` and `.step` files are exported for each successful run.
* Files are saved as `output_<timestamp>.stl` and `.step` in the backend folder.

---

## 🧩 Troubleshooting

**CadQuery Installation:**
If `pip install cadquery` fails, follow the [official installation guide](https://cadquery.readthedocs.io/).
Conda simplifies native dependency setup on Windows.

**Ollama Errors:**
Ensure Ollama is running and the model name in `app.py` matches your local model.

**G-code Fails / “No slicer available”:**

* Check PrusaSlicer or CuraEngine installation.
* Add their path to the system `PATH` if installed manually.

**Permissions:**
Ensure the backend can write to the `backend/` directory.

---

## 📁 Example Files

Several exported example models are included:

* `output_*.stl`
* `output_*.step`

You can use these to test the frontend STL viewer.

---