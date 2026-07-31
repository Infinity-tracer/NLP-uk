import { useState, useCallback } from 'react';
import type { ProcessResult, AppState, TabType } from './api/types';
import { processDocument, type PipelineMode } from './api/documentApi';
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

  const handleFileUpload = useCallback(async (file: File, mode: PipelineMode = 'full') => {
    setCurrentFile(file);
    setAppState('processing');
    setError(null);

    try {
      const data = await processDocument(file, mode);
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
      {/* Sidebar - MediLab Style */}
      <aside className="w-16 bg-[#2c4964] flex flex-col items-center py-3 flex-shrink-0 shadow-medilab-lg">
        <div className="w-11 h-11 bg-[#1977cc] rounded-full flex items-center justify-center mb-4 shadow-md">
          <span className="text-white font-black text-xs tracking-tight font-heading">NHS</span>
        </div>
        <button
          onClick={handleReset}
          className={`w-11 h-11 rounded-full flex items-center justify-center text-white mb-2 transition-all duration-300 ${
            appState === 'upload' ? 'opacity-100 bg-[#1977cc]' : 'opacity-70 hover:opacity-100 hover:bg-[#1977cc]'
          }`}
          title="New Upload"
        >
          <span className="text-xl">📤</span>
        </button>
        <button
          onClick={() => setShowHistory(true)}
          className="w-11 h-11 rounded-full flex items-center justify-center text-white opacity-70 hover:opacity-100 hover:bg-[#1977cc] mb-2 transition-all duration-300"
          title="History"
        >
          <span className="text-xl">📋</span>
        </button>
        <button className="w-11 h-11 rounded-full flex items-center justify-center text-white opacity-70 hover:opacity-100 hover:bg-[#1977cc] mb-2 transition-all duration-300" title="Documents">
          <span className="text-xl">📄</span>
        </button>
        <button className="w-11 h-11 rounded-full flex items-center justify-center text-white opacity-70 hover:opacity-100 hover:bg-[#1977cc] mb-2 transition-all duration-300" title="Settings">
          <span className="text-xl">⚙️</span>
        </button>
        <div className="flex-1" />
        <button className="w-11 h-11 rounded-full flex items-center justify-center text-white opacity-70 hover:opacity-100 hover:bg-[#1977cc] transition-all duration-300" title="Profile">
          <span className="text-xl">👤</span>
        </button>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-h-0">
        {/* Top bar - MediLab Style */}
        <header className="h-[56px] bg-white border-b border-gray-100 flex items-center px-6 flex-shrink-0 shadow-medilab-header">
          <h1 className="text-base font-semibold text-[#2c4964] flex-1 font-heading">
            {appState === 'result' ? 'View Document' : appState === 'processing' ? `Processing: ${currentFile?.name || 'Document'}` : 'Document Extraction Portal'}
          </h1>
          <div className="flex items-center gap-3 text-sm text-[#444444]">
            <span className="font-medium">Admin A A</span>
            <div className="w-9 h-9 rounded-full bg-[#1977cc] text-white flex items-center justify-center font-bold text-sm shadow-md">
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

        {/* New upload button - MediLab Style */}
        {appState === 'result' && (
          <button
            onClick={handleReset}
            className="fixed bottom-6 right-6 bg-[#1977cc] text-white px-6 py-3 rounded-pill font-semibold shadow-medilab-lg hover:bg-[#2c4964] transition-all duration-300 z-50 font-nav"
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
