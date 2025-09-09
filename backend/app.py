# File: /backend/app.py

from fastapi import FastAPI, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import time
import json
import threading
from pydantic import BaseModel
import requests
import cadquery as cq
from cadquery import exporters

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- START CHANGES ---
OUTPUT_STL_FILE = "output.stl"
OUTPUT_STEP_FILE = "output.step"
GENERATED_MODEL_FILE = "generated_model.py"

# Helper to generate unique filenames
def get_unique_filename(ext: str) -> str:
    return f"output_{int(time.time() * 1000)}.{ext}"
# --- END CHANGES ---

EXECUTION_DELAY = 2
STL_FETCH_DELAY = 3

stl_generation_status = {
    "last_generated": None,
    "in_progress": False,
    "error": None
}
status_lock = threading.Lock()

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "codegemma"

class GenerateRequest(BaseModel):
    prompt: str

def clean_code(code: str) -> str:
    lines = code.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()

def execute_generated_code():
    global stl_generation_status
    with status_lock:
        stl_generation_status["in_progress"] = True
        stl_generation_status["error"] = None
    try:
        if not os.path.exists(GENERATED_MODEL_FILE):
            raise Exception("Generated model file not found")

        with open(GENERATED_MODEL_FILE, "r") as f:
            code = f.read()

        if not code.strip():
            raise Exception("Generated code is empty")

        exec_globals = {"cq": cq}
        local_scope = {}
        exec(code, exec_globals, local_scope)

        cad_object = None
        for val in local_scope.values():
            if isinstance(val, cq.Workplane):
                cad_object = val
                break
        
        if not cad_object:
            raise Exception("No CadQuery Workplane object found in the generated code.")

        exporters.export(cad_object, OUTPUT_STL_FILE)
        exporters.export(cad_object, OUTPUT_STEP_FILE)

        # Export both STL and STEP files with unique names
        stl_filename = get_unique_filename("stl")
        step_filename = get_unique_filename("step")
        exporters.export(cad_object, stl_filename)
        exporters.export(cad_object, step_filename)
        # --- END CHANGES ---

        with status_lock:
            stl_generation_status["last_generated"] = time.time()
            stl_generation_status["in_progress"] = False
            stl_generation_status["stl_filename"] = stl_filename
            stl_generation_status["step_filename"] = step_filename

        with status_lock:
            stl_generation_status["last_generated"] = time.time()
            stl_generation_status["in_progress"] = False
    except Exception as e:
        with status_lock:
            stl_generation_status["error"] = str(e)
            stl_generation_status["in_progress"] = False

class OllamaClient:
    def __init__(self, url, model_name):
        self.url = url
        self.model_name = model_name

    def chat(self, messages, max_tokens=1024, temperature=0.1):
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True, # Ensure stream is True for iter_lines
        }
        try:
            headers = {"Content-Type": "application/json"}
            response = requests.post(self.url, json=payload, headers=headers, timeout=120, stream=True)
            response.raise_for_status()
            
            full_content = ""
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    full_content += content
            
            return {"message": {"content": full_content}}

        except requests.exceptions.RequestException as e:
            raise Exception(f"Ollama request failed: {str(e)}")
        except ValueError as e:
            raise Exception(f"JSON decode error: {str(e)}")


ollama_client = OllamaClient(OLLAMA_URL, MODEL_NAME)

@app.post("/api/generate")
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    prompt = request.prompt

    with status_lock:
        stl_generation_status["last_generated"] = None
        stl_generation_status["in_progress"] = False
        stl_generation_status["error"] = None

    messages = [
        {"role": "system", "content": (
            "You are an expert CadQuery assistant. "
            "Always generate ONLY valid Python code that creates a shape and saves it to 'output.stl'. "
            "Do not include any explanations or markdown fences. "
            "Use 'from cadquery import exporters' and call exporters.export(obj, 'output.stl').\n\n"
            "Example format:\n"
            "import cadquery as cq\n"
            "from cadquery import exporters\n\n"
            "#....Your CadQuery code here....\n"
            "exporters.export(result, 'output.stl')"
        )},
        {"role": "user", "content": f"Create: {prompt}\nGenerate ONLY Python code:"}
    ]

    try:
        response = ollama_client.chat(messages)
        message = response.get("message", {}).get("content", "")
        if not message:
            raise Exception("Empty response from Ollama")

        cleaned_code = clean_code(message)

        with open(GENERATED_MODEL_FILE, "w") as f:
            f.write(cleaned_code)

        background_tasks.add_task(execute_generated_code)

        return JSONResponse({
            "message": "Model generation started.",
            "status": "pending",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



from fastapi import Query

# Serve STL by filename

@app.get("/output.stl")
async def get_stl(filename: str = Query(...)):
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(backend_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="STL file not found.")
    return FileResponse(file_path, media_type='application/octet-stream', filename=os.path.basename(filename))

# Serve STEP by filename
@app.get("/output.step")
async def get_step(filename: str = Query(...)):
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(backend_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="STEP file not found.")
    return FileResponse(file_path, media_type='application/octet-stream', filename=os.path.basename(filename))
# --- END CHANGES ---



@app.get("/api/generation-status")
async def generation_status():
    with status_lock:
        status = stl_generation_status.copy() # Make a copy to work with

    # Determine the overall status
    final_status = "pending"
    if status["in_progress"]:
        final_status = "processing"
    elif status["error"]:
        final_status = "error"
    elif status.get("stl_filename") and status["last_generated"] is not None:
        final_status = "complete"

    return {
        "status": final_status,
        "error_message": status["error"],
        "stl_filename": status.get("stl_filename"),
        "step_filename": status.get("step_filename"),
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)