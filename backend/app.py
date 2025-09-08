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

OUTPUT_FILE = "output.stl"
GENERATED_MODEL_FILE = "generated_model.py"
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

        exec_globals = {"cq": cq, "exporters": exporters}
        exec(code, exec_globals)

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
            "max_tokens": max_tokens,
            "temperature": temperature
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

# chat with the model to generate the cad file
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
                    "exporters.export(result, 'output.stl')")},
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
            "message": "Model generated and execution started",
            "status": "code_written",
            "next_step": f"STL will be generated after {EXECUTION_DELAY}s delay"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# display the .stl file
@app.get("/output.stl")
async def get_stl():
    with status_lock:
        in_progress = stl_generation_status["in_progress"]
        error = stl_generation_status["error"]
        last_generated = stl_generation_status["last_generated"]

    if not os.path.exists(OUTPUT_FILE):
        raise HTTPException(status_code=404, detail="STL not found")

    if in_progress:
        raise HTTPException(status_code=423, detail="Generation in progress")

    if error:
        raise HTTPException(status_code=500, detail=error)

    if last_generated and (time.time() - last_generated < STL_FETCH_DELAY):
        remaining = STL_FETCH_DELAY - (time.time() - last_generated)
        raise HTTPException(status_code=425, detail=f"STL not ready yet. Remaining seconds: {round(remaining,1)}")

    return FileResponse(OUTPUT_FILE)

@app.get("/api/generation-status")
async def generation_status():
    with status_lock:
        in_progress = stl_generation_status["in_progress"]
        error = stl_generation_status["error"]
        last_generated = stl_generation_status["last_generated"]
    stl_exists = os.path.exists(OUTPUT_FILE)
    file_size = os.path.getsize(OUTPUT_FILE) if stl_exists else 0
    return {
        "stl_exists": stl_exists,
        "file_size": file_size,
        "in_progress": in_progress,
        "last_generated": last_generated,
        "error": error,
        "delays": {
            "execution_delay": EXECUTION_DELAY,
            "fetch_delay": STL_FETCH_DELAY
        }
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
