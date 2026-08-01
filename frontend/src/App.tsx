import { useState, useCallback } from 'react';
import type { ProcessResult, AppState, TabType } from './api/types';
import { processDocument, type PipelineMode } from './api/documentApi';
import UploadPanel from './components/UploadPanel';
import ProcessingPanel from './components/ProcessingPanel';
import DocumentViewer from './components/DocumentViewer';
import DetailsPanel from './components/DetailsPanel';
import RightPanel from './components/RightPanel';
import HistoryPanel from './components/HistoryPanel';
import { IconUpload, IconHistory, IconDocument, IconSettings, IconUser, IconChevronLeft, IconChevronRight } from './components/icons/Icons';

export default function App() {
  const [appState, setAppState] = useState<AppState>('upload');
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentFile, setCurrentFile] = useState<File | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('details');
  const [showHistory, setShowHistory] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [leftPanelExpanded, setLeftPanelExpanded] = useState(true);
  const [centerPanelExpanded, setCenterPanelExpanded] = useState(true);
  const [rightPanelExpanded, setRightPanelExpanded] = useState(true);

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
    { id: 'upload', icon: <IconUpload size={20} />, label: 'New Upload', onClick: handleReset, active: appState === 'upload' },
    { id: 'history', icon: <IconHistory size={20} />, label: 'History', onClick: () => setShowHistory(true), active: false },
    { id: 'documents', icon: <IconDocument size={20} />, label: 'Documents', onClick: () => {}, active: false },
    { id: 'settings', icon: <IconSettings size={20} />, label: 'Settings', onClick: () => {}, active: false },
  ];

  return (
    <div className="h-screen flex overflow-hidden bg-[#f0f4f8] p-3 gap-3">
      {/* Sidebar - Collapsible */}
      <aside
        className={`bg-[#2c4964] flex flex-col items-center py-3 flex-shrink-0 rounded-2xl shadow-[0px_2px_15px_rgba(0,0,0,0.1)] transition-all duration-300 ${
          sidebarExpanded ? 'w-48' : 'w-16'
        }`}
        onMouseEnter={() => setSidebarExpanded(true)}
        onMouseLeave={() => setSidebarExpanded(false)}
      >
        {/* Logo */}
        <div className={`flex items-center gap-3 mb-4 px-2 ${sidebarExpanded ? 'w-full justify-start pl-3' : 'justify-center'}`}>
          <div className="w-11 h-11 bg-[#1977cc] rounded-full flex items-center justify-center shadow-md flex-shrink-0">
            <span className="text-white font-black text-xs tracking-tight">NHS</span>
          </div>
          {sidebarExpanded && (
            <span className="text-white font-semibold text-sm whitespace-nowrap">
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
            <span className="flex-shrink-0">{item.icon}</span>
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
          <IconUser size={20} />
          {sidebarExpanded && (
            <span className="text-sm font-medium whitespace-nowrap">Profile</span>
          )}
        </button>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-h-0 bg-white rounded-2xl shadow-[0px_2px_15px_rgba(0,0,0,0.08)] overflow-hidden">
        {/* Top bar */}
        <header className="h-14 bg-white border-b border-gray-100 flex items-center px-6 flex-shrink-0">
          <h1 className="text-base font-semibold text-[#2c4964] flex-1">
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
              {/* Left Panel - Document Viewer (Collapsible) */}
              <div
                className={`relative bg-white border-r border-gray-100 flex flex-col overflow-hidden transition-all duration-300 ease-in-out ${
                  leftPanelExpanded ? 'flex-1 min-w-[300px]' : 'w-11 flex-shrink-0'
                }`}
                onMouseEnter={() => !leftPanelExpanded && setLeftPanelExpanded(true)}
              >
                {leftPanelExpanded ? (
                  <>
                    <DocumentViewer result={result} file={currentFile} />
                    <button
                      onClick={() => setLeftPanelExpanded(false)}
                      className="absolute top-2 right-2 w-6 h-6 bg-white/90 hover:bg-[#1977cc] hover:text-white border border-gray-200 rounded-md flex items-center justify-center text-gray-400 transition-all z-10"
                      title="Collapse panel"
                    >
                      <IconChevronLeft size={12} />
                    </button>
                  </>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center py-4 cursor-pointer bg-gray-50/50 hover:bg-gray-100/50 transition-all">
                    <div className="writing-vertical text-[10px] font-bold text-[#2c4964] tracking-widest uppercase rotate-180" style={{ writingMode: 'vertical-rl' }}>
                      Document
                    </div>
                    <IconChevronRight size={12} className="text-gray-400 mt-3" />
                  </div>
                )}
              </div>

              {/* Center Panel - Details (Collapsible) */}
              <div
                className={`relative bg-white border-r border-gray-100 flex flex-col overflow-hidden transition-all duration-300 ease-in-out ${
                  centerPanelExpanded ? 'flex-1 min-w-[380px] max-w-[480px]' : 'w-11 flex-shrink-0'
                }`}
                onMouseEnter={() => !centerPanelExpanded && setCenterPanelExpanded(true)}
              >
                {centerPanelExpanded ? (
                  <>
                    <DetailsPanel
                      result={result}
                      activeTab={activeTab}
                      onTabChange={setActiveTab}
                      onDownload={handleDownload}
                      onReset={handleReset}
                    />
                    <button
                      onClick={() => setCenterPanelExpanded(false)}
                      className="absolute top-2 right-2 w-6 h-6 bg-white/90 hover:bg-[#1977cc] hover:text-white border border-gray-200 rounded-md flex items-center justify-center text-gray-400 transition-all z-10"
                      title="Collapse panel"
                    >
                      <IconChevronLeft size={12} />
                    </button>
                  </>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center py-4 cursor-pointer bg-gray-50/50 hover:bg-gray-100/50 transition-all">
                    <div className="writing-vertical text-[10px] font-bold text-[#2c4964] tracking-widest uppercase rotate-180" style={{ writingMode: 'vertical-rl' }}>
                      Details
                    </div>
                    <IconChevronRight size={12} className="text-gray-400 mt-3" />
                  </div>
                )}
              </div>

              {/* Right Panel - Patient/Doc Info (Collapsible) */}
              <div
                className={`relative bg-white flex flex-col overflow-hidden transition-all duration-300 ease-in-out ${
                  rightPanelExpanded ? 'w-[320px] flex-shrink-0' : 'w-11 flex-shrink-0'
                }`}
                onMouseEnter={() => !rightPanelExpanded && setRightPanelExpanded(true)}
              >
                {rightPanelExpanded ? (
                  <>
                    <RightPanel result={result} />
                    <button
                      onClick={() => setRightPanelExpanded(false)}
                      className="absolute top-2 right-2 w-6 h-6 bg-white/90 hover:bg-[#1977cc] hover:text-white border border-gray-200 rounded-md flex items-center justify-center text-gray-400 transition-all z-10"
                      title="Collapse panel"
                    >
                      <IconChevronRight size={12} />
                    </button>
                  </>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center py-4 cursor-pointer bg-gray-50/50 hover:bg-gray-100/50 transition-all">
                    <div className="writing-vertical text-[10px] font-bold text-[#2c4964] tracking-widest uppercase rotate-180" style={{ writingMode: 'vertical-rl' }}>
                      Info
                    </div>
                    <IconChevronLeft size={12} className="text-gray-400 mt-3" />
                  </div>
                )}
              </div>
            </div>
          )}
        </main>

        {/* New upload button */}
        {appState === 'result' && (
          <button
            onClick={handleReset}
            className="fixed bottom-6 right-6 bg-[#1977cc] text-white px-6 py-3 rounded-full font-semibold shadow-lg hover:bg-[#2c4964] transition-all duration-300 z-50 flex items-center gap-2"
          >
            <IconUpload size={18} />
            New Document
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
