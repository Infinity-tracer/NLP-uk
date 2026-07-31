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
  const [sidebarExpanded, setSidebarExpanded] = useState(false);

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

  const sidebarItems = [
    { id: 'upload', icon: '📤', label: 'New Upload', onClick: handleReset, active: appState === 'upload' },
    { id: 'history', icon: '📋', label: 'History', onClick: () => setShowHistory(true), active: false },
    { id: 'documents', icon: '📄', label: 'Documents', onClick: () => {}, active: false },
    { id: 'settings', icon: '⚙️', label: 'Settings', onClick: () => {}, active: false },
  ];

  return (
    <div className="h-screen flex overflow-hidden">
      {/* Sidebar - Collapsible MediLab Style */}
      <aside
        className={`bg-[#2c4964] flex flex-col items-center py-3 flex-shrink-0 shadow-medilab-lg transition-all duration-300 ${
          sidebarExpanded ? 'w-48' : 'w-16'
        }`}
        onMouseEnter={() => setSidebarExpanded(true)}
        onMouseLeave={() => setSidebarExpanded(false)}
      >
        {/* Logo */}
        <div className={`flex items-center gap-3 mb-4 px-2 ${sidebarExpanded ? 'w-full justify-start pl-3' : 'justify-center'}`}>
          <div className="w-11 h-11 bg-[#1977cc] rounded-full flex items-center justify-center shadow-md flex-shrink-0">
            <span className="text-white font-black text-xs tracking-tight font-heading">NHS</span>
          </div>
          {sidebarExpanded && (
            <span className="text-white font-semibold text-sm font-heading whitespace-nowrap animate-fade-in">
              Doc Portal
            </span>
          )}
        </div>

        {/* Navigation Items */}
        {sidebarItems.map((item) => (
          <button
            key={item.id}
            onClick={item.onClick}
            className={`flex items-center gap-3 mb-2 transition-all duration-300 ${
              sidebarExpanded
                ? 'w-full px-3 py-2.5 rounded-lg mx-2 justify-start'
                : 'w-11 h-11 rounded-full justify-center'
            } ${
              item.active
                ? 'bg-[#1977cc] text-white'
                : 'text-white opacity-70 hover:opacity-100 hover:bg-[#1977cc]'
            }`}
            title={item.label}
          >
            <span className="text-xl flex-shrink-0">{item.icon}</span>
            {sidebarExpanded && (
              <span className="text-sm font-medium whitespace-nowrap">{item.label}</span>
            )}
          </button>
        ))}

        <div className="flex-1" />

        {/* Profile */}
        <button
          className={`flex items-center gap-3 transition-all duration-300 ${
            sidebarExpanded
              ? 'w-full px-3 py-2.5 rounded-lg mx-2 justify-start'
              : 'w-11 h-11 rounded-full justify-center'
          } text-white opacity-70 hover:opacity-100 hover:bg-[#1977cc]`}
          title="Profile"
        >
          <span className="text-xl flex-shrink-0">👤</span>
          {sidebarExpanded && (
            <span className="text-sm font-medium whitespace-nowrap">Profile</span>
          )}
        </button>

        {/* Collapse indicator */}
        <div className={`mt-3 text-white/50 text-xs transition-opacity duration-300 ${sidebarExpanded ? 'opacity-100' : 'opacity-0'}`}>
          ← Collapse
        </div>
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
