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
  const [prompt, setPrompt] = useState<string>('a sphere with a diameter of 40mm at the origin');
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [status, setStatus] = useState<GenerationStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [showViewer, setShowViewer] = useState<boolean>(true);

  // handles polling
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
          setResult({ stl: '/output.stl', step: '/output.step' });
          clearInterval(intervalId); // Stop polling
        } else if (data.status === 'error') {
          setStatus('error');
          setError(data.error_message || 'An unknown error occurred during generation.');
          clearInterval(intervalId); // Stop polling
        } else {
          // Keep polling if status is 'pending' or 'processing'
          setStatus(data.status);
        }
      } catch (err) {
        setStatus('error');
        setError('Failed to get generation status.');
        clearInterval(intervalId); // Stop polling on fetch failure
      }
    }, 2000); // Poll every 2 seconds

    // Cleanup function to clear the interval when the component unmounts
    return () => clearInterval(intervalId);
  }, [status]); // This effect re-runs whenever the 'status' changes

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setStatus('pending'); // Kick off the process
    setError(null);
    setResult(null);

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
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column - Input and Controls */}
          <div className="space-y-6">
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="e.g., a cube 20x20x20 with a 5mm hole through the center"
                rows={4}
                disabled={isLoading}
                className="w-full p-3 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:outline-none disabled:bg-gray-100 transition"
              />
              <button 
                type="submit" 
                disabled={isLoading} 
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
                  
                  <div className="flex items-center justify-center">
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

          {/* Right Column - 3D Viewer */}
          <div className="flex flex-col items-center justify-center">
            {status === 'complete' && result && showViewer ? (
              <div className="w-full">
                <h3 className="text-lg font-semibold text-gray-800 mb-3 text-center">3D Preview</h3>
                <div className="flex justify-center">
                  <STLViewer 
                    stlUrl={result.stl} 
                    width={480} 
                    height={360} 
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
                <div className="animate-spin mx-auto h-12 w-12 mb-4">
                  <svg className="h-full w-full" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
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