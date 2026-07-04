import { useState, useCallback } from 'react';
import type { ProcessResult, AppState, TabType } from './api/types';
import { processDocument } from './api/documentApi';
import UploadPanel from './components/UploadPanel';
import ProcessingPanel from './components/ProcessingPanel';
import DocumentViewer from './components/DocumentViewer';
import DetailsPanel from './components/DetailsPanel';
import RightPanel from './components/RightPanel';
import HistoryPanel from './components/HistoryPanel';

export default function App() {
  const [appState, setAppState] = useState<AppState>('upload');
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentFile, setCurrentFile] = useState<File | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('details');
  const [showHistory, setShowHistory] = useState(false);

  const handleFileUpload = useCallback(async (file: File) => {
    setCurrentFile(file);
    setAppState('processing');
    setError(null);

    try {
      const data = await processDocument(file);
      if (data.error && !data.doc_id) {
        setError(data.error);
        setAppState('upload');
        return;
      }
      setResult(data);
      setAppState('result');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to process document');
      setAppState('upload');
    }
  }, []);

  const handleReset = useCallback(() => {
    setAppState('upload');
    setResult(null);
    setError(null);
    setCurrentFile(null);
    setActiveTab('details');
  }, []);

  const handleDownload = useCallback(() => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${result.filename || 'result'}_processed.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  const handleSelectFromHistory = useCallback((selectedResult: ProcessResult) => {
    setResult(selectedResult);
    setCurrentFile(null);
    setAppState('result');
    setShowHistory(false);
  }, []);

  return (
    <div className="h-screen flex overflow-hidden">
      {/* Sidebar */}
      <aside className="w-16 bg-nhs-dark flex flex-col items-center py-3 flex-shrink-0">
        <div className="w-11 h-11 bg-nhs-blue rounded-lg flex items-center justify-center mb-4">
          <span className="text-white font-black text-sm tracking-tight">NHS</span>
        </div>
        <button
          onClick={handleReset}
          className={`w-11 h-11 rounded-lg flex items-center justify-center text-white mb-1 ${
            appState === 'upload' ? 'opacity-100 bg-white/15' : 'opacity-70 hover:opacity-100 hover:bg-white/15'
          }`}
          title="New Upload"
        >
          <span className="text-xl">📤</span>
        </button>
        <button
          onClick={() => setShowHistory(true)}
          className="w-11 h-11 rounded-lg flex items-center justify-center text-white opacity-70 hover:opacity-100 hover:bg-white/15 mb-1"
          title="History"
        >
          <span className="text-xl">📋</span>
        </button>
        <button className="w-11 h-11 rounded-lg flex items-center justify-center text-white opacity-70 hover:opacity-100 hover:bg-white/15 mb-1" title="Documents">
          <span className="text-xl">📄</span>
        </button>
        <button className="w-11 h-11 rounded-lg flex items-center justify-center text-white opacity-70 hover:opacity-100 hover:bg-white/15 mb-1" title="Settings">
          <span className="text-xl">⚙️</span>
        </button>
        <div className="flex-1" />
        <button className="w-11 h-11 rounded-lg flex items-center justify-center text-white opacity-70 hover:opacity-100 hover:bg-white/15" title="Profile">
          <span className="text-xl">👤</span>
        </button>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-h-0">
        {/* Top bar */}
        <header className="h-[52px] bg-white border-b-2 border-nhs-blue flex items-center px-5 flex-shrink-0">
          <h1 className="text-sm font-semibold text-nhs-dark flex-1">
            {appState === 'result' ? 'View Document' : appState === 'processing' ? `Processing: ${currentFile?.name || 'Document'}` : 'Document Extraction Portal'}
          </h1>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span>Admin A A</span>
            <div className="w-8 h-8 rounded-full bg-nhs-blue text-white flex items-center justify-center font-bold text-sm">
              AA
            </div>
          </div>
        </header>

        {/* Main area */}
        <main className="flex-1 flex overflow-hidden">
          {appState === 'upload' && (
            <UploadPanel onFileUpload={handleFileUpload} error={error} />
          )}

          {appState === 'processing' && (
            <ProcessingPanel filename={currentFile?.name || 'Document'} />
          )}

          {appState === 'result' && result && (
            <div className="flex flex-1 overflow-hidden">
              <DocumentViewer result={result} file={currentFile} />
              <DetailsPanel
                result={result}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                onDownload={handleDownload}
                onReset={handleReset}
              />
              <RightPanel result={result} />
            </div>
          )}
        </main>

        {/* New upload button */}
        {appState === 'result' && (
          <button
            onClick={handleReset}
            className="fixed bottom-6 right-6 bg-nhs-blue text-white px-5 py-3 rounded-lg font-semibold shadow-lg hover:bg-nhs-dark transition-colors z-50"
          >
            + New Document
          </button>
        )}
      </div>

      {/* History Modal */}
      {showHistory && (
        <HistoryPanel
          onSelectRun={handleSelectFromHistory}
          onClose={() => setShowHistory(false)}
        />
      )}
    </div>
  );
}
