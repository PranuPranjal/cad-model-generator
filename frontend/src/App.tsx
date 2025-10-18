import { useState, useEffect } from 'react';
import STLViewer from './components/STLViewer';

// type for successful API response
interface GenerationResult {
  step: string;
  stl: string;
}


// states for the generation process
type GenerationStatus = 'idle' | 'pending' | 'processing' | 'complete' | 'error';

function App() {
  const [prompt, setPrompt] = useState<string>('generate cadquery script for a sphere with a diameter of 40mm at the origin');
  const [promptHistory, setPromptHistory] = useState<string[]>([]);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [status, setStatus] = useState<GenerationStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [showViewer, setShowViewer] = useState<boolean>(true);
  const [supportedLibraries, setSupportedLibraries] = useState<string[]>([]);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  useEffect(() => {
    const fetchLibraries = async () => {
      try {
        const response = await fetch('/api/libraries');
        const data = await response.json();
        setSupportedLibraries(data.libraries || []);
      } catch (err) {
        console.error('Failed to fetch supported libraries:', err);
      }
    };
    fetchLibraries();
  }, []);

  useEffect(() => {
    // only poll if status is 'pending' or 'processing'
    if (status !== 'pending' && status !== 'processing') {
      return;
    }

    const intervalId = setInterval(async () => {
      try {
        const response = await fetch('/api/generation-status');
        const data = await response.json();

        if (data.status === 'complete') {
          setStatus('complete');
          setResult({
            stl: data.stl_filename ? `/output.stl?filename=${encodeURIComponent(data.stl_filename)}` : '',
            step: data.step_filename ? `/output.step?filename=${encodeURIComponent(data.step_filename)}` : '',
          });
          clearInterval(intervalId);
        } else if (data.status === 'error') {
          setStatus('error');
          setError(data.error_message || 'An unknown error occurred during generation.');
          clearInterval(intervalId);
        } else {
          // Keep polling if status is 'pending' or 'processing'
          setStatus(data.status);
        }
      } catch (err) {
        setStatus('error');
        setError('Failed to get generation status.');
        clearInterval(intervalId);
      }
    }, 2000);

    // Cleanup function to clear the interval when the component unmounts
    return () => clearInterval(intervalId);
  }, [status]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!prompt.trim()) return;
    setStatus('pending');
    setError(null);
    setResult(null);

    // Add current prompt to history
    setPromptHistory((prev) => [...prev, prompt]);
    setPrompt(''); // Clear textbox for next query

    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start generation.');
      }
      // The polling `useEffect` will take over from here
    } catch (err: any) {
      setStatus('error');
      setError(err.message);
    }
  };

  const handleCopy = (text: string, index: number) => {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
        document.execCommand('copy');
        setCopiedIndex(index);
        setTimeout(() => setCopiedIndex(null), 2000);
    } catch (err) {
        console.error('Failed to copy: ', err);
    }
    document.body.removeChild(textArea);
  };

  const isLoading = status === 'pending' || status === 'processing';

  return (
    <div className="bg-gray-50 min-h-screen font-sans">
      <div className="container mx-auto max-w-6xl p-5">
        {/* Header Section */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">Text-to-CAD Generator</h1>
          <p className="text-gray-600">
            Enter a natural language description of the 3D model you want to create.
          </p>
          {supportedLibraries.length > 0 && (
            <p className="text-sm text-gray-500 mt-2">
              Supported libraries: {supportedLibraries.join(', ')}
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column - Input and Controls */}
          <div className="space-y-6">
            {/* Chat History */}
            <div className="bg-white border border-gray-200 rounded-lg p-4 mb-2 max-h-60 overflow-y-auto shadow-sm">
              {promptHistory.length === 0 ? (
                <p className="text-gray-400 text-center">Your prompt history will appear here.</p>
              ) : (
                <ul className="space-y-2">
                  {promptHistory.map((p, idx) => (
                    <li key={idx} className="flex items-center justify-between bg-gray-100 rounded px-3 py-2 text-gray-800 text-sm">
                      <span className="flex-grow mr-3 break-all">{p}</span>
                      <button
                        onClick={() => handleCopy(p, idx)}
                        title="Copy prompt"
                        className={`flex-shrink-0 text-gray-600 hover:text-gray-900 font-semibold py-1 px-2 rounded transition flex items-center gap-1 ${copiedIndex === idx ? 'text-green-600' : ''}`}
                      >
                        {copiedIndex === idx ? (
                          <>
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                            Copied!
                          </>
                        ) : (
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
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

            {status === 'complete' && result && (
              <div className="p-6 rounded-lg bg-green-100 border border-green-400">
                <h3 className="text-lg font-semibold text-green-800 mb-2">Generation Complete!</h3>
                <p className="text-green-700 mb-4">Your model files are ready for download.</p>
                
                <div className="space-y-3">
                  <div className="flex gap-3">
                    <a 
                      href={result.step} 
                      download 
                      className="flex-1 text-center bg-green-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-green-700 no-underline transition"
                    >
                      Download .STEP
                    </a>
                    <a 
                      href={result.stl} 
                      download 
                      className="flex-1 text-center bg-green-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-green-700 no-underline transition"
                    >
                      Download .STL
                    </a>
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

          <div className="flex flex-col items-center justify-center min-h-[400px]">
            {status === 'complete' && result && showViewer ? (
              <div className="w-full">
                <h3 className="text-lg font-semibold text-gray-800 mb-3 text-center">3D Preview</h3>
                <div className="bg-white rounded-lg overflow-hidden border border-gray-300 shadow-sm">
                  <STLViewer 
                    url={result.stl} 
                  />
                </div>
                <p className="text-sm text-gray-600 text-center mt-2">
                  Click and drag to rotate • Mouse wheel to zoom
                </p>
              </div>
            ) : status === 'complete' && result && !showViewer ? (
              <div className="w-full max-w-md p-8 border-2 border-dashed border-gray-300 rounded-lg text-center text-gray-500">
                <div className="mb-4">
                  <svg className="mx-auto h-12 w-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                </div>
                <p>3D Preview Hidden</p>
                <p className="text-xs mt-1">Click "Show 3D Preview" to view your model</p>
              </div>
            ) : isLoading ? (
              <div className="w-full max-w-md p-8 border-2 border-dashed border-gray-300 rounded-lg text-center text-gray-500">
                <div className="animate-spin mx-auto h-12 w-12 mb-4 text-blue-600">
                  <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2V6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M12 18V22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M4.92999 4.92999L7.75999 7.75999" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M16.24 16.24L19.07 19.07" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M2 12H6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M18 12H22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M4.92999 19.07L7.75999 16.24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M16.24 7.75999L19.07 4.92999" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <p>Generating your 3D model...</p>
                <p className="text-xs mt-1">Status: {status}</p>
              </div>
            ) : (
              <div className="w-full max-w-md p-8 border-2 border-dashed border-gray-300 rounded-lg text-center text-gray-500">
                <div className="mb-4">
                  <svg className="mx-auto h-12 w-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                  </svg>
                </div>
                <p>Ready to Generate</p>
                <p className="text-xs mt-1">Enter a description and click "Generate CAD" to create your 3D model</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;