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
import subprocess
import tempfile
import struct
import shutil
import sys

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GENERATED_MODEL_FILE = "generated_model_script.txt"
CAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CAD")

# Ensure CAD directory exists
os.makedirs(CAD_DIR, exist_ok=True)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "llama-cad:latest"

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


class GCodeRequest(BaseModel):
    filename: str
    layer_height: float = 0.2
    infill_density: int = 20
    print_speed: int = 60
    nozzle_temp: int = 200
    bed_temp: int = 60


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
            # Import modules to make them available in the exec scope if installed
            import cq_gears  # type: ignore
            import cq_warehouse  # type: ignore
            exec_globals["cq_gears"] = cq_gears
            exec_globals["cq_warehouse"] = cq_warehouse
        except ImportError as ie:
            # Not fatal — warn and continue
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

        stl_path = os.path.join(CAD_DIR, stl_filename)
        step_path = os.path.join(CAD_DIR, step_filename)

        exporters.export(cad_object, stl_path)
        exporters.export(cad_object, step_path)

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

    # Find the first occurrence of Something(...). This is a naive parser but useful for UI.
    match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)', code)
    if not match:
        return None, None

    parsed_reply = match.group(0).strip()
    args_str = match.group(2).strip()
    if not args_str:
        return parsed_reply, {}

    props = {}
    # Split on commas that are not inside parentheses (small, naive parser)
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
                    # Ollama stream returns JSON per-line; parse it
                    try:
                        data = json.loads(line)
                    except ValueError:
                        # skip lines that aren't JSON
                        continue
                    content = data.get("message", {}).get("content", "")
                    full_content += content

            return {"message": {"content": full_content}}

        except requests.exceptions.RequestException as e:
            raise Exception(f"Ollama request failed: {str(e)}")
        except ValueError as e:
            raise Exception(f"JSON decode error while reading Ollama response: {str(e)}")


ollama_client = OllamaClient(OLLAMA_URL, MODEL_NAME)


@app.get("/api/libraries")
async def get_libraries():
    """Return available CAD library modules for the frontend dropdown (prevents frontend 404)."""
    return {
        "libraries": [
            {"name": "cadquery", "description": "Base library for solids and primitives (box, sphere, etc.)"},
            {"name": "cq_gears", "description": "For gears: SpurGear, BevelGear, RingGear, etc."},
            {"name": "cq_warehouse.fastener", "description": "For screws, bolts, nuts, washers"},
            {"name": "cq_warehouse.bearing", "description": "For ball bearings and shafts"}
        ]
    }


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
    file_path = os.path.join(CAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"STL file not found: {filename}")
    return FileResponse(file_path, media_type='model/stl', filename=os.path.basename(filename))


@app.get("/output.step")
async def get_step(filename: str = Query(...)):
    """Serves the generated STEP file."""
    file_path = os.path.join(CAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"STEP file not found: {filename}")
    return FileResponse(file_path, media_type='application/step', filename=os.path.basename(filename))


# ---------------------------
# G-code helper functions
# ---------------------------

def find_slicer():
    """
    Cross-platform slicer detection:
    Tries PrusaSlicer first, then CuraEngine.
    Supports both Windows CMD paths and Git Bash paths (/c/Program Files/...).
    Returns (slicer_type, slicer_path).
    """
    possible_prusa = [
        shutil.which("prusa-slicer-console"),
        shutil.which("prusa-slicer"),
        r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe",
        r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe",
        "/c/Program Files/Prusa3D/PrusaSlicer/prusa-slicer-console",
        "/c/Program Files/Prusa3D/PrusaSlicer/prusa-slicer"
    ]

    possible_cura = [
        shutil.which("CuraEngine"),
        r"C:\Program Files\UltiMaker Cura 5.11.0\CuraEngine.exe",
        "/c/Program Files/UltiMaker Cura 5.11.0/CuraEngine.exe"
    ]

    def normalize_path(p):
        if not p:
            return None
        p = os.path.normpath(p.replace("/", os.sep))
        return p if os.path.exists(p) else None

    prusa_path = next((normalize_path(p) for p in possible_prusa if normalize_path(p)), None)
    cura_path = next((normalize_path(p) for p in possible_cura if normalize_path(p)), None)

    if prusa_path:
        print(f"✅ Found PrusaSlicer at: {prusa_path}")
        return "prusa", prusa_path
    elif cura_path:
        print(f"✅ Found CuraEngine at: {cura_path}")
        return "cura", cura_path
    else:
        print("❌ No slicer found. Please verify installation path.")
        return None, None


def create_prusa_config_ini(settings: dict) -> str:
    """Create a temporary PrusaSlicer config file with the given settings."""
    config_content = f"""# generated by CAD Model Generator
layer_height = {settings['layer_height']}
fill_density = {settings['infill_density']}%
temperature = {settings['nozzle_temp']}
bed_temperature = {settings['bed_temp']}
perimeter_speed = {settings['print_speed']}
external_perimeter_speed = {settings['print_speed']}
infill_speed = {settings['print_speed']}
solid_infill_speed = {settings['print_speed']}
top_solid_infill_speed = {settings['print_speed']}
support_material_speed = {settings['print_speed']}
bridge_speed = {settings['print_speed']}
gap_fill_speed = {settings['print_speed']}
travel_speed = 130
first_layer_speed = 30
perimeters = 2
top_solid_layers = 3
bottom_solid_layers = 3
fill_pattern = grid
nozzle_diameter = 0.4
filament_diameter = 1.75
extrusion_multiplier = 1
retract_length = 2
retract_speed = 40
"""
    fd, path = tempfile.mkstemp(suffix='.ini', text=True)
    with os.fdopen(fd, 'w') as f:
        f.write(config_content)
    return path


def run_slicer(stl_path: str, gcode_path: str, settings: dict = None) -> bool:
    """
    Universal slicer runner — tries PrusaSlicer first, then CuraEngine.
    """
    slicer_type, slicer_path = find_slicer()
    if not slicer_path:
        print("No slicer detected. Will attempt fallback.")
        return False

    defaults = {
        "layer_height": 0.2,
        "infill_density": 20,
        "print_speed": 60,
        "nozzle_temp": 200,
        "bed_temp": 60,
    }
    if settings:
        defaults.update(settings)

    config_path = None  # For prusa
    tmp_json_path = None  # For cura
    cmd = []

    try:
        if slicer_type == "prusa":
            config_path = create_prusa_config_ini(defaults)
            cmd = [
                slicer_path,
                "--export-gcode",
                f"--load={config_path}",
                "--output", gcode_path,
                stl_path,
            ]
        else:  # CuraEngine
            tmp_json = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='w', encoding='utf-8')
            cura_config = {
                "layer_height": defaults["layer_height"],
                "infill_sparse_density": defaults["infill_density"],
                "material_print_temperature": defaults["nozzle_temp"],
                "material_bed_temperature": defaults["bed_temp"],
                "speed_print": defaults["print_speed"],
            }
            json.dump(cura_config, tmp_json)
            tmp_json_path = tmp_json.name
            tmp_json.close()
            cmd = [
                slicer_path, "slice",
                "-j", tmp_json_path,
                "-o", gcode_path,
                "-l", stl_path,
            ]

        print(f"🛠️ Running {'PrusaSlicer' if slicer_type == 'prusa' else 'CuraEngine'}:")
        print(" ".join(f'"{c}"' if " " in c else c for c in cmd))

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip())
        if result.returncode == 0 and os.path.exists(gcode_path):
            print("✅ G-code generation completed successfully.")
            return True
        print(f"❌ Slicer returned code {result.returncode}")
        return False
    except Exception as e:
        print(f"⚠️ Slicing failed: {e}")
        return False
    finally:
        # Clean up temp files
        if config_path and os.path.exists(config_path):
            os.remove(config_path)
        if tmp_json_path and os.path.exists(tmp_json_path):
            os.remove(tmp_json_path)


def get_stl_bounding_box(stl_path: str):
    """Read a binary STL file's bounding box (robust but minimal)."""
    try:
        with open(stl_path, 'rb') as f:
            header = f.read(80)
            num_triangles = struct.unpack('<I', f.read(4))[0]

            min_x = min_y = min_z = float('inf')
            max_x = max_y = max_z = float('-inf')

            for _ in range(num_triangles):
                # normal vector
                f.read(12)
                for _ in range(3):
                    x, y, z = struct.unpack('<fff', f.read(12))
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    min_z = min(min_z, z)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
                    max_z = max(max_z, z)
                f.read(2)  # attribute byte count

            return {
                'min': (min_x, min_y, min_z),
                'max': (max_x, max_y, max_z),
                'size': (max_x - min_x, max_y - min_y, max_z - min_z)
            }
    except Exception:
        # fallback bounding box
        return {
            'min': (0, 0, 0),
            'max': (50, 50, 50),
            'size': (50, 50, 50)
        }


def generate_gcode_content(bb, layer_height, infill_density, print_speed, nozzle_temp, bed_temp):
    """Generate a very simple G-code approximation for fallback use."""
    width, depth, height = bb['size']

    gcode = f"""; Generated G-code (fallback)
; Model dimensions: {width:.2f} x {depth:.2f} x {height:.2f} mm
; Layer height: {layer_height} mm
; Infill density: {infill_density}%
; Print speed: {print_speed} mm/s
; Nozzle temp: {nozzle_temp}C
; Bed temp: {bed_temp}C

M104 S{nozzle_temp} ; Set nozzle temperature
M140 S{bed_temp} ; Set bed temperature
M190 S{bed_temp} ; Wait for bed temp
M109 S{nozzle_temp} ; Wait for nozzle temp
G28 ; Home
G92 E0 ; Reset extruder
"""

    num_layers = max(1, int(height / layer_height))
    feed_rate = print_speed * 60

    for layer in range(num_layers):
        z = (layer + 1) * layer_height
        gcode += f"\n; Layer {layer+1}/{num_layers}\nG1 Z{z:.3f} F{feed_rate}\n"
        # simple perimeter rectangle
        gcode += f"G1 X{bb['min'][0]:.3f} Y{bb['min'][1]:.3f} F{feed_rate}\n"
        gcode += f"G1 X{bb['max'][0]:.3f} Y{bb['min'][1]:.3f} E{layer*0.1:.3f} F{feed_rate}\n"
        gcode += f"G1 X{bb['max'][0]:.3f} Y{bb['max'][1]:.3f} E{layer*0.15:.3f} F{feed_rate}\n"
        gcode += f"G1 X{bb['min'][0]:.3f} Y{bb['max'][1]:.3f} E{layer*0.2:.3f} F{feed_rate}\n"
        gcode += f"G1 X{bb['min'][0]:.3f} Y{bb['min'][1]:.3f} E{layer*0.25:.3f} F{feed_rate}\n"

        if infill_density > 0:
            infill_lines = max(1, int((bb['size'][0]) / 5))
            for i in range(infill_lines):
                x = bb['min'][0] + i * 5
                gcode += f"G1 X{x:.3f} Y{bb['min'][1]:.3f} F{feed_rate}\n"
                gcode += f"G1 X{x:.3f} Y{bb['max'][1]:.3f} E{layer*0.3 + i*0.05:.3f} F{feed_rate}\n"

    gcode += """
; End G-code
G91
G1 E-2 F2700
G1 Z5 F3000
G90
M104 S0
M140 S0
M84
"""
    return gcode


def generate_basic_gcode(stl_path: str, gcode_path: str, settings: dict):
    """Create fallback G-code using bounding box slicing."""
    try:
        bb = get_stl_bounding_box(stl_path)
        gcode = generate_gcode_content(bb, settings["layer_height"], settings["infill_density"],
                                      settings["print_speed"], settings["nozzle_temp"], settings["bed_temp"])
        with open(gcode_path, "w") as f:
            f.write(gcode)
        return True
    except Exception as e:
        print("Fallback G-code generation failed:", e)
        return False


def stl_to_gcode(stl_path: str, gcode_path: str, settings: dict):
    """
    Convert STL to G-code using PrusaSlicer CLI or CuraEngine.
    Falls back to a simple generator if neither is available.
    """
    # Try to find and run any available slicer
    success = run_slicer(stl_path, gcode_path, settings)
    if success and os.path.exists(gcode_path):
        return True

    # Fallback to basic G-code generator
    print("⚠️ No slicer available, using fallback G-code generator")
    return generate_basic_gcode(stl_path, gcode_path, settings)


@app.post("/api/generate-gcode")
async def generate_gcode(request: GCodeRequest):
    print("CuraEngine path:", shutil.which("CuraEngine"))

    """Generate G-code from an existing STL file in CAD_DIR."""
    stl_file = os.path.join(CAD_DIR, request.filename)
    if not os.path.exists(stl_file):
        raise HTTPException(status_code=404, detail="STL file not found")

    gcode_filename = request.filename.replace(".stl", ".gcode")
    gcode_path = os.path.join(CAD_DIR, gcode_filename)

    settings = {
        "layer_height": request.layer_height,
        "infill_density": request.infill_density,
        "print_speed": request.print_speed,
        "nozzle_temp": request.nozzle_temp,
        "bed_temp": request.bed_temp
    }

    try:
        success = stl_to_gcode(stl_file, gcode_path, settings)
        if not success or not os.path.exists(gcode_path):
            raise Exception("G-code generation failed")
        file_size = os.path.getsize(gcode_path)
        return {"success": True, "filename": gcode_filename, "size": file_size, "message": "G-code generated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"G-code generation failed: {e}")


@app.get("/api/download-gcode/{filename}")
async def download_gcode(filename: str):
    """Download a generated G-code file."""
    file_path = os.path.join(CAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="G-code file not found")
    return FileResponse(file_path, media_type='text/plain', filename=os.path.basename(filename))


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
