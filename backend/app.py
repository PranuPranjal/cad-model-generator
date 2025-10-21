from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import time
import json
import threading
import re
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

GENERATED_MODEL_FILE = "generated_model_script.txt"

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "ask-cad"

generation_status = {
    "in_progress": False,
    "error": None,
    "stl_filename": None,
    "step_filename": None,
    "parsed_reply": None,
    "model_properties": None,
    "last_generated": None,
}
status_lock = threading.Lock()


class GenerateRequest(BaseModel):
    prompt: str


def get_unique_filename(ext: str) -> str:
    return f"output_{int(time.time() * 1000)}.{ext}"


def clean_code(code: str) -> str:
    """Cleans the generated code by removing unnecessary prefixes and ensuring proper formatting."""
    code = re.sub(r'^\s*\.?Response\s*:?', '', code.strip(), flags=re.IGNORECASE)
    py_marker = '```python'
    if py_marker in code:
        start_index = code.find(py_marker) + len(py_marker)
        end_index = code.find('```', start_index)
        if end_index != -1:
            code = code[start_index:end_index].strip()

    marker = '```'
    if marker in code:
        start_index = code.find(marker) + len(marker)
        end_index = code.find(marker, start_index)
        if end_index != -1:
            code = code[start_index:end_index].strip()

    code = code.strip()

    # Ensure newline after any import statement if next token is code
    code = re.sub(r'(\bimport[^\n]+)\s+(?=\w)', r'\1\n', code)

    # Ensure newline before 'result =' (if it's on same line)
    code = re.sub(r'\s*(?=\bresult\s*=)', r'\n', code)

    return code


def execute_generated_code():
    """Executes the generated CadQuery code and exports STL and STEP files."""
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

        # Prepare the 'exec' environment for executing the AI-generated code
        exec_globals = {"cq": cq, "__builtins__": __builtins__}

        try:
            # Import modules to make them available in the exec scope
            import cq_gears
            import cq_warehouse
            exec_globals["cq_gears"] = cq_gears
            exec_globals["cq_warehouse"] = cq_warehouse
        except ImportError as ie:
            print(f"WARNING: A pre-installed library was not found: {ie}")
            pass

        local_scope = {}
        exec(code, exec_globals, local_scope)

        cad_object = local_scope.get("result")

        # Handle gear-like objects by calling .build() to get the solid
        if hasattr(cad_object, "build") and callable(cad_object.build):
            cad_object = cad_object.build()

        if not cad_object:
            raise Exception("A CadQuery object named 'result' was not found in the generated code.")

        stl_filename = get_unique_filename("stl")
        step_filename = get_unique_filename("step")

        exporters.export(cad_object, stl_filename)
        exporters.export(cad_object, step_filename)

        with status_lock:
            generation_status["last_generated"] = time.time()
            generation_status["in_progress"] = False
            generation_status["stl_filename"] = stl_filename
            generation_status["step_filename"] = step_filename

    except Exception as e:
        with status_lock:
            generation_status["error"] = str(e)
            generation_status["in_progress"] = False


def parse_model_from_code(code: str):
    """Parse the first model instantiation from the generated code.

    Returns a tuple (parsed_reply_str, properties_dict).
    Example: code contains "SpurGear(module=2.8, teeth_number=42, width=26.0)"
    -> ("SpurGear(module=2.8, teeth_number=42, width=26.0)", {"module":2.8, "teeth_number":42, ...})
    """
    if not code:
        return None, None

    # Find the first occurrence of Something(...)
    match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)', code)
    if not match:
        return None, None

    parsed_reply = match.group(0).strip()
    args_str = match.group(2).strip()
    if not args_str:
        return parsed_reply, {}

    props = {}
    # Split on commas that are not inside parentheses (very small, naive parser)
    parts = re.split(r',\s*(?![^()]*\))', args_str)
    positional_index = 0
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '=' in part:
            key, val = part.split('=', 1)
            key = key.strip()
            val = val.strip()
            # strip quotes for string values
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                props[key] = val[1:-1]
            else:
                # try to coerce to int/float
                try:
                    if '.' in val:
                        props[key] = float(val)
                    else:
                        props[key] = int(val)
                except Exception:
                    # fallback to raw string
                    props[key] = val
        else:
            # positional argument -> store as arg0, arg1, ...
            key = f"arg{positional_index}"
            positional_index += 1
            v = part
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                props[key] = v[1:-1]
            else:
                try:
                    if '.' in v:
                        props[key] = float(v)
                    else:
                        props[key] = int(v)
                except Exception:
                    props[key] = v

    return parsed_reply, props


class OllamaClient:
    """Client for interacting with the Ollama API."""
    def __init__(self, url, model_name):
        self.url = url
        self.model_name = model_name

    def chat(self, messages):
        """Sends a chat request to the Ollama API and returns the response."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
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


@app.post("/api/generate")
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Handles the generation request by sending a prompt to the LLM and executing the generated code."""
    prompt = request.prompt

    with status_lock:
        generation_status["in_progress"] = True
        generation_status["error"] = None
        generation_status["stl_filename"] = None
        generation_status["step_filename"] = None
        generation_status["last_generated"] = None

    messages = [
        {"role": "system", "content": (
            "You are a CadQuery script generator. Your only purpose is to translate a user's text description into a valid CadQuery Python script."
            "\n\n**Follow these rules STRICTLY:**\n"
            "1. **Code ONLY:** Your entire output must be ONLY Python code. Do not include any other text, explanations, or markdown fences (like ```python).\n"
            "2. **Imports:** Include ALL necessary imports at the beginning:\n"
            "   - `import cadquery as cq` for basic CadQuery primitives (Box, Cylinder, Sphere, Cone, etc.)\n"
            "   - `from cq_gears import SpurGear, BevelGear, RingGear, etc.` for gears\n"
            "   - `from cq_warehouse.fastener import ButtonHeadScrew, CheeseHeadScrew, CounterSunkScrew, HexHeadScrew, etc.` for fasteners\n"
            "   - `from cq_warehouse.bearing import SingleRowCappedDeepGrooveBallBearing, etc.` for bearings\n"
            "3. **Result Variable:** You MUST create the final CadQuery 3D object and assign it to a variable named exactly `result`.\n"
            "4. **No Exporting:** Do NOT include any lines for exporting the file (e.g., `exporters.export(...)`). This is handled separately by the backend.\n"
            "5. **Use appropriate libraries:**\n"
            "   - For gears: use cq_gears library\n"
            "   - For fasteners (screws, bolts, nuts): use cq_warehouse.fastener\n"
            "   - For bearings: use cq_warehouse.bearing\n"
            "   - For basic shapes (box, cylinder, sphere, cone): use cadquery (cq)\n\n"
            "⚠️ For cq_gears (SpurGear, BevelGear, etc.), always call .build() before assigning to `result`.\n"

            "**Examples:**\n\n"
            "User: Create a spur gear with 20 teeth, module 1.5, and width 10mm\n"
            "Your Output:\n"
            "from cq_gears import SpurGear\n"
            "gear = SpurGear(module=1.5, teeth_number=20, width=10.0)\n"
            "result = gear.build()\n\n"
            "User: Create a buttonhead screw M5-0.8 length 20mm type iso7380_1\n"
            "Your Output:\n"
            "from cq_warehouse.fastener import ButtonHeadScrew\n"
            "result = ButtonHeadScrew(size=\"M5-0.8\", length=20, fastener_type=\"iso7380_1\")\n\n"
            "User: Create a single row capped deep groove ball bearing size M3-10-4 type SKT\n"
            "Your Output:\n"
            "from cq_warehouse.bearing import SingleRowCappedDeepGrooveBallBearing\n"
            "result = SingleRowCappedDeepGrooveBallBearing(size=\"M3-10-4\", bearing_type=\"SKT\")\n\n"
            "User: Create a box with length 100, width 50, and height 30\n"
            "Your Output:\n"
            "import cadquery as cq\n"
            "result = cq.Workplane(\"XY\").box(100.0, 50.0, 30.0)\n\n"
            "User: Generate a cylinder with radius 20 and height 60\n"
            "Your Output:\n"
            "import cadquery as cq\n"
            "result = cq.Workplane(\"XY\").cylinder(60.0, 20.0)\n\n"
            "User: Create a sphere with radius 15\n"
            "Your Output:\n"
            "import cadquery as cq\n"
            "result = cq.Sphere(15.0)"
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

        # Parse the cleaned code to extract a simple textual reply and properties
        parsed_reply, properties = parse_model_from_code(cleaned_code)
        with status_lock:
            generation_status["parsed_reply"] = parsed_reply
            generation_status["model_properties"] = properties

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
    """Returns the current status of the model generation process."""
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
        "parsed_reply": status.get("parsed_reply"),
        "model_properties": status.get("model_properties"),
    }


@app.get("/output.stl")
async def get_stl(filename: str = Query(...)):
    """Serves the generated STL file."""
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"STL file not found: {filename}")
    return FileResponse(file_path, media_type='model/stl', filename=os.path.basename(filename))


@app.get("/output.step")
async def get_step(filename: str = Query(...)):
    """Serves the generated STEP file."""
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"STEP file not found: {filename}")
    return FileResponse(file_path, media_type='application/step', filename=os.path.basename(filename))


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)