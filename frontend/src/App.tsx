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
  interface ChatMessage { role: 'user' | 'assistant'; text: string }
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [result, setResult] = useState<GenerationResult | null>(null);
  // parsed reply and model properties are included in the assistant message now
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
          const stlUrl = data.stl_filename ? `/output.stl?filename=${encodeURIComponent(data.stl_filename)}` : '';
          const stepUrl = data.step_filename ? `/output.step?filename=${encodeURIComponent(data.step_filename)}` : '';
          setResult({ stl: stlUrl, step: stepUrl });

          const parsed = data.parsed_reply || null;
          const props = data.model_properties || null;

          // Build a single assistant reply string that includes parsed reply, properties and links
          let assistantText = '';
          if (parsed) {
            assistantText += `Detected Model: ${parsed}\n`;
          }
          if (props && Object.keys(props).length > 0) {
            assistantText += 'Model Properties:\n';
            for (const [k, v] of Object.entries(props)) {
              assistantText += ` - ${k}: ${String(v)}\n`;
            }
          }
          // Do not include raw download URLs in the assistant reply; downloads are available via the Download buttons

          if (!assistantText) {
            assistantText = 'Generation completed.';
          }

          // parsed info has been included into assistantText; append assistant message
          setMessages((prev) => [...prev, { role: 'assistant', text: assistantText }]);
          // scroll to bottom on new message
          setTimeout(() => {
            const el = document.getElementById('messages-end');
            if (el) el.scrollIntoView({ behavior: 'smooth' });
          }, 50);
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

  // Auto-scroll to bottom whenever messages update
  useEffect(() => {
    const el = document.getElementById('messages-end');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!prompt.trim()) return;
    setStatus('pending');
    setError(null);
    setResult(null);

    // Add current prompt to history
  setMessages((prev) => [...prev, { role: 'user', text: prompt }]);
    setPrompt(''); // Clear textbox for next query
  // Clear previous parsed results (they live in messages now)

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
    <div className="bg-gray-50 min-h-screen font-sans flex flex-col">
      {/* Fixed top-right download toolbar */}
      {result && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-3 bg-white/90 backdrop-blur rounded-full p-2 shadow">
          <div className="relative group">
            <a href={result.step} download title="Download STEP" className="flex items-center gap-2 px-3 py-2 rounded-full bg-white hover:bg-gray-100 shadow-sm">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-green-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v12m0 0l4-4m-4 4l-4-4" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 20H4" />
              </svg>
              <span className="text-sm font-medium text-gray-800">STEP</span>
            </a>
            <span className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 rounded bg-gray-800 text-white text-xs py-1 px-2 opacity-0 group-hover:opacity-100 transition-opacity">STEP</span>
          </div>
          <div className="relative group">
            <a href={result.stl} download title="Download STL" className="flex items-center gap-2 px-3 py-2 rounded-full bg-white hover:bg-gray-100 shadow-sm">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-green-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v12m0 0l4-4m-4 4l-4-4" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 20H4" />
              </svg>
              <span className="text-sm font-medium text-gray-800">STL</span>
            </a>
            <span className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 rounded bg-gray-800 text-white text-xs py-1 px-2 opacity-0 group-hover:opacity-100 transition-opacity">STL</span>
          </div>
        </div>
      )}
  <div className="p-3 pl-2 flex flex-col flex-1 h-screen w-full">
        {/* Header Section */}
        <div className="text-center mb-4">
          <h1 className="text-4xl font-bold text-gray-800 mb-1">Text-to-CAD Generator</h1>
          <p className="text-gray-600">
            Enter a natural language description of the 3D model you want to create.
          </p>
          {supportedLibraries.length > 0 && (
            <p className="text-sm text-gray-500 mt-2">
              Supported libraries: {supportedLibraries.join(', ')}
            </p>
          )}
          
        </div>

  <div className="grid grid-cols-1 lg:grid-cols-[40%_58%] gap-4 flex-1 items-stretch h-full">
    {/* Left Column - Input and Controls */}
    <div className="flex flex-col justify-end gap-4">
            {/* Chat History */}
            <div className="bg-white border border-gray-200 rounded-lg p-4 mb-1 overflow-y-auto shadow-sm flex-1 max-h-[calc(90vh-260px)]">
              {messages.length === 0 ? (
                <p className="text-gray-400 text-center">No messages yet — enter a prompt to start.</p>
              ) : (
                <div className="space-y-3 px-1">
                  {messages.map((m, idx) => (
                    <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`${m.role === 'user' ? 'bg-blue-600 text-white rounded-bl-xl rounded-tl-xl rounded-tr-xl' : 'bg-gray-100 text-gray-900 rounded-br-xl rounded-tr-xl rounded-tl-xl'} max-w-[80%] px-4 py-2 whitespace-pre-wrap break-words`}> 
                        <div className="flex items-center gap-2 text-xs opacity-80 mb-1 font-semibold">
                          {m.role === 'user' ? (
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white/90" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 21v-2a4 4 0 00-3-3.87"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 21v-2a4 4 0 013-3.87"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 7a4 4 0 110-8 4 4 0 010 8z"/></svg>
                          ) : (
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11c1.657 0 3-1.567 3-3.5S17.657 4 16 4s-3 1.567-3 3.5S14.343 11 16 11z"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 11c1.657 0 3-1.567 3-3.5S7.657 4 6 4 3 5.567 3 7.5 4.343 11 6 11z"/></svg>
                          )}
                          <span>{m.role === 'user' ? 'You' : 'Assistant'}</span>
                        </div>
                        <div className="text-sm">{m.text}</div>
                        <div className="text-right mt-1">
                          <button onClick={() => handleCopy(m.text, idx)} className={`p-1 rounded text-gray-500 hover:text-gray-700 ${copiedIndex === idx ? 'text-green-600' : ''}`} aria-label="Copy message">
                            {copiedIndex === idx ? (
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7"/></svg>
                            ) : (
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9"/></svg>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                  <div id="messages-end" />
                </div>
              )}
            </div>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
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

            {/* Generation Complete panel removed — download icons are moved to the app top-right */}
          </div>

          <div className="flex flex-col items-stretch justify-center min-h-[300px]">
            {status === 'complete' && result && showViewer ? (
              <div className="w-full">
                <h3 className="text-lg font-semibold text-gray-800 mb-3 text-center">3D Preview</h3>
                  <div className="bg-white rounded-lg overflow-hidden border border-gray-300 shadow-sm w-full overflow-auto" style={{ maxHeight: '60vh' }}>
                  <STLViewer 
                    url={result.stl} 
                  />
                </div>
                <p className="text-sm text-gray-600 text-center mt-2">
                  Click and drag to rotate • Mouse wheel to zoom
                </p>
              </div>
            ) : status === 'complete' && result && !showViewer ? (
              <div className="w-full p-8 border-2 border-dashed border-gray-300 rounded-lg text-center text-gray-500">
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
              <div className="w-full p-8 border-2 border-dashed border-gray-300 rounded-lg text-center text-gray-500">
                <div className="animate-spin mx-auto h-12 w-12 mb-4 text-blue-600">
                  <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2V6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M12 18V22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M4.92999 4.92999L7.75999 7.75999" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M16.24 16.24L19.07 19.07" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M2 12H6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M18 12H22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M4.92999 19.07L7.75999 16.24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><path d="M16.24 7.75999L19.07 4.92999" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <p>Generating your 3D model...</p>
                <p className="text-xs mt-1">Status: {status}</p>
              </div>
            ) : (
              <div className="w-full p-8 border-2 border-dashed border-gray-300 rounded-lg text-center text-gray-500">
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