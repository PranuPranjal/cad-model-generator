import { useState, useEffect } from 'react';
import STLViewer from './components/STLViewer';

interface GenerationResult {
  step: string;
  stl: string;
  gcode?: string;
}

type GenerationStatus = 'idle' | 'pending' | 'processing' | 'complete' | 'error';
type GCodeStatus = 'idle' | 'processing' | 'complete' | 'error';

interface GCodeSettings {
  layer_height: number;
  infill_density: number;
  print_speed: number;
  nozzle_temp: number;
  bed_temp: number;
}

function App() {
  const [prompt, setPrompt] = useState<string>(
    'generate cadquery script for a sphere with a diameter of 40mm at the origin'
  );
  const [promptHistory, setPromptHistory] = useState<string[]>([]);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [status, setStatus] = useState<GenerationStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [showViewer, setShowViewer] = useState<boolean>(true);
  const [supportedLibraries, setSupportedLibraries] = useState<string[]>([]);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  // G-code feature states
  const [showGCodePanel, setShowGCodePanel] = useState<boolean>(false);
  const [gcodeSettings, setGcodeSettings] = useState<GCodeSettings>({
    layer_height: 0.2,
    infill_density: 20,
    print_speed: 60,
    nozzle_temp: 200,
    bed_temp: 60,
  });
  const [gcodeStatus, setGcodeStatus] = useState<GCodeStatus>('idle');
  const [gcodeFile, setGcodeFile] = useState<string | null>(null);

  // Fetch available libraries
  useEffect(() => {
    const fetchLibraries = async () => {
      try {
        const response = await fetch('/api/libraries');
        const data = await response.json();
        if (data.libraries) {
          const names = data.libraries.map((l: any) => l.name);
          setSupportedLibraries(names);
        }
      } catch (err) {
        console.error('Failed to fetch supported libraries:', err);
      }
    };
    fetchLibraries();
  }, []);

  // Poll backend for model generation status
  useEffect(() => {
    if (status !== 'pending' && status !== 'processing') return;

    const intervalId = setInterval(async () => {
      try {
        const response = await fetch('/api/generation-status');
        const data = await response.json();

        if (data.status === 'complete') {
          setStatus('complete');
          setResult({
            stl: data.stl_filename
              ? `/output.stl?filename=${encodeURIComponent(data.stl_filename)}`
              : '',
            step: data.step_filename
              ? `/output.step?filename=${encodeURIComponent(data.step_filename)}`
              : '',
          });
          clearInterval(intervalId);
        } else if (data.status === 'error') {
          setStatus('error');
          setError(
            data.error_message || 'An unknown error occurred during generation.'
          );
          clearInterval(intervalId);
        } else {
          setStatus(data.status);
        }
      } catch {
        setStatus('error');
        setError('Failed to get generation status.');
        clearInterval(intervalId);
      }
    }, 2000);

    return () => clearInterval(intervalId);
  }, [status]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    setStatus('pending');
    setError(null);
    setResult(null);
    setGcodeFile(null);
    setGcodeStatus('idle');
    setShowGCodePanel(false);

    setPromptHistory((prev) => [...prev, prompt]);
    setPrompt('');

    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to start generation.');
      }
    } catch (err: any) {
      setStatus('error');
      setError(err.message);
    }
  };

  const handleCopy = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  // G-code generation
  const handleGenerateGCode = async () => {
    if (!result?.stl) return;
    setGcodeStatus('processing');
    setError(null);

    const filename = new URL(result.stl, window.location.origin).searchParams.get(
      'filename'
    );

    try {
      const response = await fetch('/api/generate-gcode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, ...gcodeSettings }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to generate G-code.');
      }

      const data = await response.json();
      setGcodeStatus('complete');
      setGcodeFile(`/api/download-gcode/${data.filename}`);
    } catch (err: any) {
      console.error('G-code generation failed:', err);
      setGcodeStatus('error');
      setError(err.message);
    }
  };

  const isLoading = status === 'pending' || status === 'processing';

  return (
    <div className="bg-gray-50 min-h-screen font-sans">
      <div className="container mx-auto max-w-6xl p-5">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">
            Text-to-CAD Generator
          </h1>
          <p className="text-gray-600">
            Enter a natural language description of the 3D model you want to
            create.
          </p>
          {supportedLibraries.length > 0 && (
            <p className="text-sm text-gray-500 mt-2">
              Supported libraries: {supportedLibraries.join(', ')}
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* LEFT PANEL */}
          <div className="space-y-6">
            <div className="bg-white border border-gray-200 rounded-lg p-4 mb-2 max-h-60 overflow-y-auto shadow-sm">
              {promptHistory.length === 0 ? (
                <p className="text-gray-400 text-center">
                  Your prompt history will appear here.
                </p>
              ) : (
                <ul className="space-y-2">
                  {promptHistory.map((p, idx) => (
                    <li
                      key={idx}
                      className="flex items-center justify-between bg-gray-100 rounded px-3 py-2 text-gray-800 text-sm"
                    >
                      <span className="flex-grow mr-3 break-all">{p}</span>
                      <button
                        onClick={() => handleCopy(p, idx)}
                        className={`flex-shrink-0 text-gray-600 hover:text-gray-900 font-semibold py-1 px-2 rounded transition flex items-center gap-1 ${
                          copiedIndex === idx ? 'text-green-600' : ''
                        }`}
                      >
                        {copiedIndex === idx ? 'Copied!' : 'Copy'}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* PROMPT FORM */}
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="e.g., a spur gear with 20 teeth, module 1.5, and width 10mm"
                rows={4}
                disabled={isLoading}
                className="w-full p-3 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:outline-none disabled:bg-gray-100 transition"
              />
              <button
                type="submit"
                disabled={isLoading || !prompt.trim()}
                className="w-full bg-blue-600 text-white font-bold py-3 px-4 rounded-lg shadow-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition"
              >
                {isLoading ? `Processing... (${status})` : 'Generate CAD'}
              </button>
            </form>

            {status === 'error' && error && (
              <div className="p-4 rounded-lg bg-red-100 border border-red-400 text-red-700">
                <strong>Error:</strong> {error}
              </div>
            )}

            {/* RESULT */}
            {status === 'complete' && result && (
              <div className="p-6 rounded-lg bg-green-100 border border-green-400">
                <h3 className="text-lg font-semibold text-green-800 mb-2">
                  Generation Complete!
                </h3>
                <p className="text-green-700 mb-4">
                  Your model files are ready for download.
                </p>

                <div className="space-y-3">
                  <div className="flex gap-3">
                    <a
                      href={result.step}
                      download
                      className="flex-1 text-center bg-green-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-green-700 transition"
                    >
                      Download .STEP
                    </a>
                    <a
                      href={result.stl}
                      download
                      className="flex-1 text-center bg-green-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-green-700 transition"
                    >
                      Download .STL
                    </a>
                  </div>

                  {/* NEW: G-code Feature */}
                  <div className="pt-3">
                    {!showGCodePanel ? (
                      <button
                        onClick={() => setShowGCodePanel(true)}
                        className="w-full bg-yellow-500 text-white font-bold py-2 px-4 rounded-lg hover:bg-yellow-600 transition"
                      >
                        G-code Settings
                      </button>
                    ) : (
                      <div className="bg-white p-4 rounded-lg border border-yellow-400 shadow-sm mt-3">
                        <h4 className="text-lg font-semibold text-yellow-700 mb-2">
                          G-code Settings
                        </h4>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          <label>
                            Layer Height (mm)
                            <input
                              type="number"
                              step="0.05"
                              value={gcodeSettings.layer_height}
                              onChange={(e) =>
                                setGcodeSettings({
                                  ...gcodeSettings,
                                  layer_height: parseFloat(e.target.value),
                                })
                              }
                              className="w-full border border-gray-300 rounded p-1"
                            />
                          </label>
                          <label>
                            Infill (%)
                            <input
                              type="number"
                              value={gcodeSettings.infill_density}
                              onChange={(e) =>
                                setGcodeSettings({
                                  ...gcodeSettings,
                                  infill_density: parseInt(e.target.value),
                                })
                              }
                              className="w-full border border-gray-300 rounded p-1"
                            />
                          </label>
                          <label>
                            Speed (mm/s)
                            <input
                              type="number"
                              value={gcodeSettings.print_speed}
                              onChange={(e) =>
                                setGcodeSettings({
                                  ...gcodeSettings,
                                  print_speed: parseInt(e.target.value),
                                })
                              }
                              className="w-full border border-gray-300 rounded p-1"
                            />
                          </label>
                          <label>
                            Nozzle Temp (°C)
                            <input
                              type="number"
                              value={gcodeSettings.nozzle_temp}
                              onChange={(e) =>
                                setGcodeSettings({
                                  ...gcodeSettings,
                                  nozzle_temp: parseInt(e.target.value),
                                })
                              }
                              className="w-full border border-gray-300 rounded p-1"
                            />
                          </label>
                          <label>
                            Bed Temp (°C)
                            <input
                              type="number"
                              value={gcodeSettings.bed_temp}
                              onChange={(e) =>
                                setGcodeSettings({
                                  ...gcodeSettings,
                                  bed_temp: parseInt(e.target.value),
                                })
                              }
                              className="w-full border border-gray-300 rounded p-1"
                            />
                          </label>
                        </div>
                        <div className="mt-4 flex gap-2">
                          <button
                            onClick={handleGenerateGCode}
                            disabled={gcodeStatus === 'processing'}
                            className="flex-1 bg-yellow-600 text-white py-2 px-3 rounded font-semibold hover:bg-yellow-700 transition"
                          >
                            {gcodeStatus === 'processing'
                              ? 'Generating...'
                              : 'Generate G-code'}
                          </button>
                          <button
                            onClick={() => setShowGCodePanel(false)}
                            className="flex-1 bg-gray-300 text-gray-700 py-2 px-3 rounded font-semibold hover:bg-gray-400 transition"
                          >
                            Close
                          </button>
                        </div>
                        {gcodeStatus === 'complete' && gcodeFile && (
                          <div className="mt-3 text-center">
                            <a
                              href={gcodeFile}
                              download
                              className="text-yellow-700 font-semibold underline"
                            >
                              Download G-code File
                            </a>
                          </div>
                        )}
                        {gcodeStatus === 'error' && (
                          <p className="text-red-600 mt-2 text-sm text-center">
                            G-code generation failed.
                          </p>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-center pt-2">
                    <button
                      onClick={() => setShowViewer(!showViewer)}
                      className="text-green-700 hover:text-green-800 font-medium underline"
                    >
                      {showViewer ? 'Hide' : 'Show'} 3D Preview
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* RIGHT PANEL */}
          <div className="flex flex-col items-center justify-center min-h-[400px]">
            {status === 'complete' && result && showViewer ? (
              <div className="w-full">
                <h3 className="text-lg font-semibold text-gray-800 mb-3 text-center">
                  3D Preview
                </h3>
                <div className="bg-white rounded-lg overflow-hidden border border-gray-300 shadow-sm">
                  <STLViewer url={result.stl} />
                </div>
                <p className="text-sm text-gray-600 text-center mt-2">
                  Click and drag to rotate • Mouse wheel to zoom
                </p>
              </div>
            ) : isLoading ? (
              <div className="w-full max-w-md p-8 border-2 border-dashed border-gray-300 rounded-lg text-center text-gray-500">
                <p>Generating your 3D model...</p>
              </div>
            ) : (
              <div className="w-full max-w-md p-8 border-2 border-dashed border-gray-300 rounded-lg text-center text-gray-500">
                <p>Ready to Generate</p>
                <p className="text-xs mt-1">
                  Enter a description and click "Generate CAD" to create your 3D
                  model
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;