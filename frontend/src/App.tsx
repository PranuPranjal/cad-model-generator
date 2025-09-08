import { useState } from 'react';

// Define a type for the successful API response
interface GenerationResult {
  step: string;
  stl: string;
}

function App() {
  const [prompt, setPrompt] = useState<string>('a sphere with a diameter of 40mm at the origin');
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsLoading(true);
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
        throw new Error(errorData.detail || 'An unknown error occurred.');
      }

      const data: GenerationResult = await response.json();
      setResult(data);

    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-gray-50 min-h-screen flex items-center justify-center font-sans">
      <div className="container mx-auto max-w-2xl text-center p-5">
        <h1 className="text-4xl font-bold text-gray-800 mb-2">Text-to-CAD Generator</h1>
        <p className="text-gray-600 mb-8">
          Enter a natural language description of the 3D model you want to create.
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g., a cube 20x20x20 with a 5mm hole through the center"
            rows={4}
            disabled={isLoading}
            className="w-full p-3 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:outline-none disabled:bg-gray-100 transition"
          />
          <button type="submit" disabled={isLoading} className="w-full bg-blue-600 text-white font-bold py-3 px-4 rounded-lg shadow-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition">
            {isLoading ? 'Generating...' : 'Generate CAD'}
          </button>
        </form>

        {error && (
          <div className="mt-8 p-4 rounded-lg text-left bg-red-100 border border-red-400 text-red-700">
            <strong>Error:</strong> {error}
          </div>
        )}

        {result && (
          <div className="mt-8 p-6 rounded-lg text-left bg-green-100 border border-green-400">
            <h3 className="text-lg font-semibold text-green-800">Generation Complete!</h3>
            <p className="text-green-700">Your model files are ready for download.</p>
            <div className="mt-4 flex gap-4">
              <a href={result.step} className="flex-1 text-center bg-green-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-green-700 no-underline transition">
                Download .STEP
              </a>
              <a href={result.stl} className="flex-1 text-center bg-green-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-green-700 no-underline transition">
                Download .STL
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;