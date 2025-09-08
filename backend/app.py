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
OUTPUT_STEP_FILE = "output.step" # ADDED: Define STEP file name
GENERATED_MODEL_FILE = "generated_model.py"
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

        # --- START CHANGES ---
        # The generated code should create a CadQuery object, often named 'result'
        exec_globals = {"cq": cq}
        local_scope = {}
        exec(code, exec_globals, local_scope)

        # Find the CadQuery object in the local scope
        cad_object = None
        for val in local_scope.values():
            if isinstance(val, cq.Workplane):
                cad_object = val
                break
        
        if not cad_object:
            raise Exception("No CadQuery Workplane object found in the generated code.")

        # Export both STL and STEP files
        exporters.export(cad_object, OUTPUT_STL_FILE)
        exporters.export(cad_object, OUTPUT_STEP_FILE)
        # --- END CHANGES ---

        with status_lock:
            stl_generation_status["last_generated"] = time.time()
            stl_generation_status["in_progress"] = False
    except Exception as e:
        with status_lock:
            stl_generation_status["error"] = str(e)
            stl_generation_status["in_progress"] = False

class OllamaClient:
    # ... (no changes needed in this class)
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
            "Always generate ONLY valid Python code that creates a shape. "
            "Do not include any explanations or markdown fences. "
            "The final CadQuery object must be assigned to a variable, for example 'result = cq.Workplane...'. "
            "Do NOT include any export code yourself.\n\n"
            "Example format:\n"
            "import cadquery as cq\n\n"
            "result = cq.Workplane('XY').box(10, 20, 30)"
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

# --- START CHANGES ---
# IMPORTANT: The model generation from your LLM might not be perfect.
# We're updating the prompt to make it more reliable and removing the
# `exporters` part from the prompt, as we now handle that in our Python code.

@app.get("/output.stl")
async def get_stl():
    if not os.path.exists(OUTPUT_STL_FILE):
        raise HTTPException(status_code=404, detail="STL file not found.")
    return FileResponse(OUTPUT_STL_FILE, media_type='application/octet-stream', filename='output.stl')

# ADDED: New endpoint to serve the STEP file
@app.get("/output.step")
async def get_step():
    if not os.path.exists(OUTPUT_STEP_FILE):
        raise HTTPException(status_code=404, detail="STEP file not found.")
    return FileResponse(OUTPUT_STEP_FILE, media_type='application/octet-stream', filename='output.step')
# --- END CHANGES ---


@app.get("/api/generation-status")
async def generation_status():
    with status_lock:
        status = stl_generation_status.copy() # Make a copy to work with
    
    stl_exists = os.path.exists(OUTPUT_STL_FILE)
    
    # Determine the overall status
    final_status = "pending"
    if status["in_progress"]:
        final_status = "processing"
    elif status["error"]:
        final_status = "error"
    elif stl_exists and status["last_generated"] is not None:
        final_status = "complete"

    return {
        "status": final_status,
        "error_message": status["error"],
    }


if __name__ == "__main__":
    uvicorn.run("app:main", host="0.0.0.0", port=5000, reload=True)