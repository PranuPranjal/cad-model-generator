from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
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

# --- Global Constants & State ---

# IMPORTANT FIX: Changed the generated file to a .txt extension.
# The `uvicorn` server with `reload=True` watches for changes in .py files.
# By writing our generated code to a .py file, we were causing the server
# to restart, which killed the background task before it could create the
# STL/STEP files. Using .txt avoids this problem entirely.
GENERATED_MODEL_FILE = "generated_model_script.txt"

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "deepseek-coder:6.7b"

generation_status = {
    "in_progress": False,
    "error": None,
    "stl_filename": None,
    "step_filename": None,
    "last_generated": None,
}
status_lock = threading.Lock()


class GenerateRequest(BaseModel):
    prompt: str


def get_unique_filename(ext: str) -> str:
    """Creates a unique filename based on the current timestamp to avoid conflicts."""
    return f"output_{int(time.time() * 1000)}.{ext}"

def clean_code(code: str) -> str:
    """
    Extracts Python code from a string that might include markdown fences.
    This acts as a safeguard in case the model doesn't follow instructions perfectly.
    """
    py_marker = '```python'
    if py_marker in code:
        start_index = code.find(py_marker) + len(py_marker)
        end_index = code.find('```', start_index)
        if end_index != -1:
            return code[start_index:end_index].strip()

    marker = '```'
    if marker in code:
        start_index = code.find(marker) + len(marker)
        end_index = code.find(marker, start_index)
        if end_index != -1:
            return code[start_index:end_index].strip()

    return code.strip()


def execute_generated_code():
    """
    Executes the generated CadQuery script in a controlled environment
    and handles exporting the resulting 3D model.
    This function is designed to be run in a background thread.
    """
    global generation_status
    with status_lock:
        generation_status["in_progress"] = True
        generation_status["error"] = None
    try:
        if not os.path.exists(GENERATED_MODEL_FILE):
            raise Exception(f"Generated script file not found: {GENERATED_MODEL_FILE}")

        with open(GENERATED_MODEL_FILE, "r") as f:
            code = f.read()

        if not code.strip():
            raise Exception("Generated code is empty.")

        # Execute the script in a restricted scope
        exec_globals = {"cq": cq}
        local_scope = {}
        exec(code, exec_globals, local_scope)

        cad_object = local_scope.get("result")
        
        if not cad_object or not isinstance(cad_object, (cq.Workplane, cq.Shape)):
            raise Exception("A CadQuery object (Workplane or Shape) named 'result' was not found in the generated code.")

        # Generate unique filenames and export both STL and STEP files
        stl_filename = get_unique_filename("stl")
        step_filename = get_unique_filename("step")
        
        exporters.export(cad_object, stl_filename)
        exporters.export(cad_object, step_filename)

        # Update status upon successful completion
        with status_lock:
            generation_status["last_generated"] = time.time()
            generation_status["in_progress"] = False
            generation_status["stl_filename"] = stl_filename
            generation_status["step_filename"] = step_filename

    except Exception as e:
        with status_lock:
            generation_status["error"] = str(e)
            generation_status["in_progress"] = False

class OllamaClient:
    """A simple client to interact with the Ollama API."""
    def __init__(self, url, model_name):
        self.url = url
        self.model_name = model_name

    def chat(self, messages):
        """Sends a chat request to the Ollama API and returns the full response."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True, # Use streaming to read the complete response
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
            raise Exception(f"JSON decode error while reading Ollama response: {str(e)}")


ollama_client = OllamaClient(OLLAMA_URL, MODEL_NAME)


# --- API Endpoints ---
@app.post("/api/generate")
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    prompt = request.prompt

    with status_lock:
        generation_status["in_progress"] = True
        generation_status["error"] = None
        generation_status["stl_filename"] = None
        generation_status["step_filename"] = None
        generation_status["last_generated"] = None

    # System prompt to guide the LLM's output
    messages = [
        {"role": "system", "content": (
            "You are a CadQuery script generator. Your only purpose is to translate a user's text description into a valid CadQuery Python script.\n\n"
            "**Follow these rules STRICTLY:**\n"
            "1. **Code ONLY:** Your entire output must be ONLY Python code. Do not include any other text, explanations, or markdown fences (like ```python).\n"
            "2. **Imports:** The script must begin with `import cadquery as cq`.\n"
            "3. **Result Variable:** You MUST create the final CadQuery 3D object and assign it to a variable named exactly `result`.\n"
            "4. **No Exporting:** Do NOT include any lines for exporting the file (e.g., `exporters.export(...)`). This is handled separately by the backend.\n\n"
            "**Example:**\n"
            "User Prompt: a sphere with a diameter of 40mm at the origin\n\n"
            "Your Output:\n"
            "import cadquery as cq\n\n"
            "result = cq.Workplane(\"XY\").sphere(20)"
        )},
        {"role": "user", "content": f"Create the following model: {prompt}"}
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
        with status_lock:
            generation_status["error"] = str(e)
            generation_status["in_progress"] = False
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/generation-status")
async def get_generation_status():
    """Returns the current status of the 3D model generation process."""
    with status_lock:
        status = generation_status.copy()

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

@app.get("/output.stl")
async def get_stl(filename: str = Query(...)):
    """Serves a specific STL file by its unique name."""
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"STL file not found: {filename}")
    return FileResponse(file_path, media_type='model/stl', filename=os.path.basename(filename))


@app.get("/output.step")
async def get_step(filename: str = Query(...)):
    """Serves a specific STEP file by its unique name."""
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"STEP file not found: {filename}")
    return FileResponse(file_path, media_type='application/step', filename=os.path.basename(filename))


# --- Main Execution ---
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
