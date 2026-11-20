import { useEffect, useRef, useState } from 'react';
import Editor, { DiffEditor } from '@monaco-editor/react';
import { createMarkdownReport, detectLanguage, readJsonResponse } from './api';
import {
  AlertCircle,
  ArrowDownToLine,
  Braces,
  CheckCircle2,
  Check,
  ChevronDown,
  CircleCheck,
  Code2,
  Copy,
  DatabaseZap,
  Eye,
  FileCheck2,
  FileCode2,
  FileText,
  Filter,
  LockKeyhole,
  MessageCircle,
  RotateCcw,
  RefreshCw,
  ScanLine,
  Send,
  Shield,
  ShieldAlert,
  Sparkles,
  Upload,
  TriangleAlert,
  X,
} from 'lucide-react';
import './index.css';

const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
const MAX_FILE_BYTES = 100_000;
const API_HEALTH_CHECK_INTERVAL = 5_000;

const examples = {
  python: {
    filename: 'main.py',
    code: 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n\n\nprint(greet("Developer"))\n',
  },
  java: {
    filename: 'Main.java',
    code: 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, developer!");\n    }\n}\n',
  },
};

const statItems = [
  { key: 'total', label: 'Total issues', icon: AlertCircle, color: 'violet' },
  { key: 'critical', label: 'Critical', icon: X, color: 'red' },
  { key: 'high', label: 'High', icon: ShieldAlert, color: 'orange' },
  { key: 'medium', label: 'Medium', icon: TriangleAlert, color: 'amber' },
  { key: 'low', label: 'Low', icon: CheckCircle2, color: 'blue' },
  { key: 'security', label: 'Security findings', icon: ShieldAlert, color: 'orange' },
  { key: 'quality', label: 'Code quality', icon: Sparkles, color: 'blue' },
];

const severityFilters = ['all', 'critical', 'error', 'high', 'medium', 'warning', 'low', 'info'];
const categories = ['all', 'Security', 'Code quality', 'Compilation', 'Syntax'];

function severityLabel(severity) {
  return severity ? severity.charAt(0).toUpperCase() + severity.slice(1) : 'Info';
}

function displaySeverity(finding) {
  return finding.severity_level || finding.severity;
}

function findingsForSeverity(findings, severity) {
  const groupedSeverity = {
    critical: ['critical', 'error'],
    medium: ['medium', 'warning'],
    low: ['low', 'info'],
  };
  const matches = groupedSeverity[severity] || [severity];
  return findings.filter((finding) => matches.includes(finding.severity));
}

function qualityLabel(value) {
  const score = String(value || 'high').toLowerCase();
  if (score === 'low') return 'Low';
  if (score === 'medium') return 'Medium';
  return 'High';
}

function App() {
  const [language, setLanguage] = useState('python');
  const [languageSource, setLanguageSource] = useState('auto');
  const [filename, setFilename] = useState(examples.python.filename);
  const [code, setCode] = useState(examples.python.code);
  const [analysis, setAnalysis] = useState(null);
  const [backendStatus, setBackendStatus] = useState('checking');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isPreviewingPdf, setIsPreviewingPdf] = useState(false);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState('');
  const [activeFinding, setActiveFinding] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showDiff, setShowDiff] = useState(false);
  const [severityFilter, setSeverityFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [expandedFinding, setExpandedFinding] = useState(null);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [assistantQuestion, setAssistantQuestion] = useState('');
  const [assistantMessages, setAssistantMessages] = useState([]);
  const [isAskingAssistant, setIsAskingAssistant] = useState(false);
  const fileInputRef = useRef(null);
  const editorRef = useRef(null);

  useEffect(() => () => {
    if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl);
  }, [pdfPreviewUrl]);

  useEffect(() => {
    let isMounted = true;
    let timeoutId;

    async function checkBackend() {
      try {
        const response = await fetch(`${API_URL}/api/health`);
        const result = await readJsonResponse(response, 'Backend health check');
        if (isMounted) {
          setBackendStatus(result.status !== 'ok'
            ? 'offline'
            : result.service === 'ai-code-review-agent'
              ? 'online'
              : 'misconfigured');
        }
      } catch {
        if (isMounted) setBackendStatus('offline');
      }

      if (isMounted) {
        timeoutId = window.setTimeout(checkBackend, API_HEALTH_CHECK_INTERVAL);
      }
    }

    checkBackend();
    return () => {
      isMounted = false;
      window.clearTimeout(timeoutId);
    };
  }, []);

  const counts = analysis?.counts || {
    total: 0,
    errors: 0,
    warnings: 0,
    security: 0,
    quality: 0,
  };

  function changeLanguage(nextLanguage, source = 'manual') {
    setLanguage(nextLanguage);
    setLanguageSource(source);
    setFilename((currentFilename) => {
      const suffix = nextLanguage === 'python' ? '.py' : '.java';
      return currentFilename.replace(/\.(py|java)$/i, '') + suffix;
    });
    setAnalysis(null);
    setPdfPreviewUrl('');
    setAssistantMessages([]);
    setAssistantQuestion('');
    setError('');
    setNotice(source === 'manual' ? `${nextLanguage === 'python' ? 'Python' : 'Java'} selected manually.` : '');
    setActiveFinding(null);
  }

  function handleCodeChange(value) {
    const nextCode = value ?? '';
    setCode(nextCode);
    const detectedLanguage = detectLanguage(nextCode);
    if (detectedLanguage && detectedLanguage !== language) {
      changeLanguage(detectedLanguage, 'auto');
    } else if (detectedLanguage) {
      setLanguageSource('auto');
    } else if (languageSource !== 'manual') {
      setLanguageSource('uncertain');
    }
    if (analysis) {
      setAnalysis(null);
      setPdfPreviewUrl('');
      setAssistantMessages([]);
      setAssistantQuestion('');
      setNotice('');
    }
  }

  async function loadSourceFile(file) {
    if (!file) return;
    const extension = file.name.split('.').pop()?.toLowerCase();
    const fileLanguage = extension === 'py' ? 'python' : extension === 'java' ? 'java' : null;
    if (!fileLanguage) {
      setError('Choose a Python (.py) or Java (.java) source file.');
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setError('Source files must be no larger than 100 KB.');
      return;
    }
    try {
      const contents = await file.text();
      setLanguage(fileLanguage, 'auto');
      setFilename(file.name);
      setCode(contents);
      setAnalysis(null);
      setPdfPreviewUrl('');
      setAssistantMessages([]);
      setAssistantQuestion('');
      setActiveFinding(null);
      setError('');
      setNotice(`${file.name} is ready for static review.`);
    } catch {
      setError('The selected file could not be read. Try choosing it again.');
    }
  }

  async function handleFileUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    await loadSourceFile(file);
  }

  async function handleDrop(event) {
    event.preventDefault();
    setIsDraggingFile(false);
    await loadSourceFile(event.dataTransfer.files?.[0]);
  }

  function clearCode() {
    setCode('');
    setFilename(language === 'python' ? 'main.py' : 'Main.java');
    setAnalysis(null);
    setPdfPreviewUrl('');
    setAssistantMessages([]);
    setAssistantQuestion('');
    setActiveFinding(null);
    setExpandedFinding(null);
    setLanguageSource('uncertain');
    setError('');
    setNotice('');
  }

  async function analyzeCode() {
    if (!code.trim()) {
      setError('Paste some code or upload a Python or Java source file to get started.');
      return;
    }
    if (languageSource === 'uncertain') {
      setError('Language is uncertain. Select Python or Java from the language control before analysis.');
      return;
    }
    setError('');
    setNotice('');
    setAnalysis(null);
    setPdfPreviewUrl('');
    setAssistantMessages([]);
    setAssistantQuestion('');
    setIsAnalyzing(true);
    const requestBody = {
      code,
      filename,
      ...(languageSource === 'manual' ? { language } : {}),
    };
    try {
      const response = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });
      const result = await readJsonResponse(response, 'Analysis');
      setAnalysis(result);
      setAssistantMessages([]);
      setActiveFinding(result.findings[0] || null);
      setExpandedFinding(result.findings.length ? 0 : null);
      setShowDiff(false);
      setSeverityFilter('all');
      setCategoryFilter('all');
      setNotice('Analysis complete. Findings below are from the backend static checks.');
    } catch (requestError) {
      if (requestError instanceof TypeError) setBackendStatus('offline');
      setError(
        requestError instanceof TypeError
          ? `Could not connect to the analysis API. Start this project’s backend at ${API_URL || 'http://127.0.0.1:8001'}, then retry.`
          : requestError.message || 'Analysis failed. Please try again.',
      );
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function copyText(value, successMessage) {
    try {
      await navigator.clipboard.writeText(value);
      setNotice(successMessage);
      setError('');
    } catch {
      setError('Clipboard access was blocked by your browser. Select and copy the code manually.');
    }
  }

  async function downloadReport() {
    if (!analysis) return;
    setIsDownloading(true);
    setError('');
    try {
      const report = { ...analysis };
      delete report.suggested_code;
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${analysis.filename}.review.json`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (downloadError) {
      setError(downloadError.message || 'The report could not be downloaded.');
    } finally {
      setIsDownloading(false);
    }
  }

  async function fetchPdfReport() {
    const response = await fetch(`${API_URL}/api/report/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code,
        filename,
        language: analysis.language,
      }),
    });
    if (!response.ok) await readJsonResponse(response, 'PDF report');
    const blob = await response.blob();
    if (!blob.size || !blob.type.startsWith('application/pdf')) {
      throw new Error('The PDF report endpoint returned an invalid file.');
    }
    return blob;
  }

  async function downloadPdfReport() {
    if (!analysis || isDownloading || isPreviewingPdf) return;
    setIsDownloading(true);
    setError('');
    try {
      const blob = await fetchPdfReport();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${analysis.filename}.review.pdf`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      setNotice('PDF review report downloaded.');
    } catch (downloadError) {
      if (downloadError instanceof TypeError) setBackendStatus('offline');
      setError(downloadError.message || 'The PDF report could not be downloaded.');
    } finally {
      setIsDownloading(false);
    }
  }

  async function previewPdfReport() {
    if (!analysis || isDownloading || isPreviewingPdf) return;
    setIsPreviewingPdf(true);
    setError('');
    try {
      const blob = await fetchPdfReport();
      setPdfPreviewUrl(URL.createObjectURL(blob));
      setNotice('PDF report preview is ready.');
    } catch (previewError) {
      if (previewError instanceof TypeError) setBackendStatus('offline');
      setError(previewError.message || 'The PDF report preview could not be generated.');
    } finally {
      setIsPreviewingPdf(false);
    }
  }

  function downloadMarkdownReport() {
    if (!analysis) return;
    try {
      const blob = new Blob([createMarkdownReport(analysis)], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${analysis.filename}.review.md`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (downloadError) {
      setError(downloadError.message || 'The Markdown report could not be downloaded.');
    }
  }

  async function askAssistant(event) {
    event.preventDefault();
    const question = assistantQuestion.trim();
    if (!question || isAskingAssistant) return;
    setIsAskingAssistant(true);
    setError('');
    try {
      const response = await fetch(`${API_URL}/api/assistant`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          language: analysis?.language || language,
          finding: activeFinding
            ? {
              title: activeFinding.title,
              category: activeFinding.type,
              explanation: activeFinding.explanation,
            }
            : null,
          history: assistantMessages.slice(-6).map(({ question: previousQuestion, answer }) => ({
            question: previousQuestion,
            answer,
          })),
        }),
      });
      const result = await readJsonResponse(response, 'Code assistant');
      setAssistantMessages((current) => [...current, { question, ...result }]);
      setAssistantQuestion('');
    } catch (requestError) {
      if (requestError instanceof TypeError) setBackendStatus('offline');
      setError(requestError.message || 'The code assistant request failed.');
    } finally {
      setIsAskingAssistant(false);
    }
  }

  function goToFinding(finding) {
    setActiveFinding(finding);
    if (finding.line) {
      editorRef.current?.revealLineInCenter(finding.line);
      editorRef.current?.setPosition({ lineNumber: finding.line, column: 1 });
      editorRef.current?.focus();
    }
  }

  const visibleFindings = (analysis?.findings || [])
    .map((finding, index) => ({ finding, index }))
    .filter(({ finding }) => (
      (severityFilter === 'all' || findingsForSeverity([finding], severityFilter).length > 0)
      && (categoryFilter === 'all' || (finding.category || finding.type) === categoryFilter)
    ));

  const dashboardCounts = {
    total: counts.total,
    security: counts.security,
    quality: counts.quality,
    ...(analysis?.summary?.severity_breakdown || {}),
  };

  const reviewSummary = analysis
    ? analysis.summary?.overview || (counts.security
      ? `${counts.security} security risk${counts.security === 1 ? '' : 's'} detected. ${counts.errors} error${counts.errors === 1 ? '' : 's'} and ${counts.warnings} warning${counts.warnings === 1 ? '' : 's'} need attention. Start with the highest-severity findings and validate each recommended fix.`
      : counts.total
        ? `${counts.total} issue${counts.total === 1 ? '' : 's'} found, with no security risks flagged by the available checks. Review the findings and rerun analysis after changes.`
        : 'No issues were reported by the available static checks. Continue with tests and a human review for security-sensitive changes.')
    : '';

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="AI Code and Security home">
          <span className="brand-mark"><Shield size={20} /></span>
          <span className="brand-copy">
            <span className="brand-name">REVIEW<span>STUDIO</span></span>
            <span className="brand-caption">LOCAL STATIC ANALYSIS</span>
          </span>
        </a>
        <nav className="topbar-nav" aria-label="Main navigation">
          <a href="#dashboard">Dashboard</a>
          <a href="#workspace">Code Analysis</a>
          <a href="#results">Findings</a>
          <a href="#assistant">AI Assistant</a>
          <a href="#reports">Reports</a>
        </nav>
        <div className={`topbar-status backend-${backendStatus}`} role="status" aria-live="polite">
          <span className="online-dot" />
          <span>
            {backendStatus === 'checking'
              ? 'Checking API'
              : backendStatus === 'online'
                ? 'Analysis API connected'
                : backendStatus === 'misconfigured'
                  ? 'Wrong API service'
                  : 'Analysis API offline'}
          </span>
          <span className="privacy-label"><LockKeyhole size={13} /> Never executes submitted code</span>
        </div>
      </header>

      <section className="hero-section" id="dashboard">
        <div className="hero-copy">
          <span className="eyebrow"><Sparkles size={14} /> DEVELOPER CODE INTELLIGENCE</span>
          <h1>AI Code Review<br /><span className="gradient-text">&amp; Security Analysis Agent</span></h1>
          <p>Clear findings, practical fixes, and security guidance in one focused workspace.</p>
        </div>
        <div className="hero-actions" aria-label="Code actions">
          <button
            className="button button-quiet"
            type="button"
            onClick={clearCode}
            disabled={!code && !analysis}
          >
            <RotateCcw size={15} /> Clear code
          </button>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={16} /> Upload code
          </button>
          <input
            ref={fileInputRef}
            className="visually-hidden"
            type="file"
            accept=".py,.java,text/x-python,text/x-java"
            onChange={handleFileUpload}
            aria-label="Upload a Python .py or Java .java source file"
          />
          <button
            className="button button-primary"
            type="button"
            onClick={analyzeCode}
            disabled={isAnalyzing || !code.trim() || languageSource === 'uncertain'}
          >
            {isAnalyzing ? <RefreshCw className="spin" size={16} /> : <ScanLine size={16} />}
            {isAnalyzing ? 'Analyzing code...' : 'Analyze code'}
          </button>
        </div>
      </section>

      {(error || notice) && (
        <div className={`message-banner ${error ? 'message-error' : 'message-success'}`} role={error ? 'alert' : 'status'}>
          {error ? <TriangleAlert size={17} /> : <CircleCheck size={17} />}
          <span>{error || notice}</span>
          <button className="message-close" type="button" onClick={() => { setError(''); setNotice(''); }} aria-label="Dismiss">
            <X size={15} />
          </button>
        </div>
      )}

      <section className="workspace" id="workspace" aria-label="Code review workspace">
        <article
          className={`panel editor-panel ${isDraggingFile ? 'drop-target' : ''}`}
          onDragEnter={(event) => { event.preventDefault(); setIsDraggingFile(true); }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) setIsDraggingFile(false);
          }}
          onDrop={handleDrop}
        >
          <div className="panel-heading">
            <div className="panel-title">
              <span className="panel-icon"><Code2 size={16} /></span>
              <div>
                <h2>Code workspace</h2>
                <p>Paste or type code — its language is detected automatically</p>
              </div>
            </div>
            <label className={`language-select-wrap language-${languageSource}`}>
              <Braces size={15} />
              <select
                className="language-select"
                value={language}
                onChange={(event) => changeLanguage(event.target.value, 'manual')}
                aria-label="Programming language; automatically detected, select manually if needed"
                title={languageSource === 'auto' ? 'Detected from the source' : 'Selected manually'}
              >
                <option value="python">Python</option>
                <option value="java">Java</option>
              </select>
              <ChevronDown className="select-chevron" size={14} />
              <span className="language-source">
                {languageSource === 'auto' ? 'AUTO' : languageSource === 'manual' ? 'MANUAL' : 'CHOOSE'}
              </span>
            </label>
          </div>
          <div className="file-tab">
            <FileCode2 size={15} />
            <span>{filename}</span>
            <span className="file-extension">{language === 'python' ? 'PY' : 'JAVA'}</span>
            <button
              className="icon-button copy-source"
              type="button"
              onClick={() => copyText(code, 'Source code copied to clipboard.')}
              aria-label="Copy source code"
              title="Copy source code"
            >
              <Copy size={15} />
            </button>
          </div>
          <div className="editor-frame">
            <Editor
              height="438px"
              language={language}
              theme="vs-dark"
              value={code}
              onChange={handleCodeChange}
              onMount={(editor) => { editorRef.current = editor; }}
              options={{
                automaticLayout: true,
                minimap: { enabled: false },
                fontSize: 13,
                fontFamily: "'JetBrains Mono', 'Cascadia Code', Consolas, monospace",
                fontLigatures: true,
                lineNumbers: 'on',
                lineNumbersMinChars: 3,
                scrollBeyondLastLine: false,
                tabSize: 4,
                wordWrap: 'on',
                padding: { top: 16, bottom: 18 },
                renderLineHighlight: 'gutter',
                roundedSelection: true,
                suggestOnTriggerCharacters: true,
                scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
              }}
            />
          </div>
          <div className="editor-footer">
            <span><span className="editor-language-dot" /> {language === 'python' ? 'Python' : 'Java'} {languageSource === 'auto' ? 'detected' : 'selected'}</span>
            <span>{code.split('\n').length} lines</span>
            <span className="editor-footer-right"><LockKeyhole size={12} /> Source is never executed</span>
          </div>
          {isDraggingFile && (
            <div className="drop-overlay" aria-live="polite">
              <span><Upload size={24} /></span>
              <strong>Drop a .py or .java file to review</strong>
            </div>
          )}
        </article>
      </section>

      {analysis && (
        <>
          <section className="stats-grid" aria-label="Analysis issue counts">
            {statItems.map(({ key, label, icon: Icon, color }) => (
              <article className="stat-card" key={key}>
                <span className={`stat-icon ${color}`}><Icon size={17} /></span>
                <div className="stat-copy">
                  <span className="stat-label">{label}</span>
                  <span className="stat-value">{dashboardCounts[key] ?? 0}</span>
                </div>
                <span className="stat-live"><span className="online-dot" /> CHECKED</span>
              </article>
            ))}
          </section>
          <section className="summary-strip" aria-live="polite">
            <span className="summary-icon"><FileCheck2 size={17} /></span>
            <div>
              <strong>Review summary</strong>
              <p>{reviewSummary}</p>
              <div className="review-metrics">
                <span className="health-score">
                  <strong>{analysis.health_score ?? analysis.summary?.health_score ?? 100}</strong>
                  <span>/ 100 code health</span>
                </span>
                <span className={`review-status status-${(analysis.review_status || 'Needs Review').toLowerCase().replaceAll(' ', '-')}`}>
                  {analysis.review_status || 'Needs Review'}
                </span>
              </div>
              <div className="quality-summary-row">
                <span className={`quality-pill quality-${analysis.quality || 'high'}`}>
                  {qualityLabel(analysis.quality)} quality
                </span>
              </div>
              <div className="summary-breakdowns">
                <p><strong>Security:</strong> {analysis.summary?.security_summary}</p>
                <p><strong>Code quality:</strong> {analysis.summary?.quality_summary}</p>
              </div>
              <div className="severity-chart" aria-label="Severity distribution chart">
                {['critical', 'high', 'medium', 'low'].map((severity) => {
                  const value = dashboardCounts[severity] || 0;
                  const percentage = counts.total
                    ? Math.round((value / counts.total) * 100)
                    : 0;
                  return (
                    <div className="severity-chart-row" key={severity}>
                      <span>{severityLabel(severity)} <strong>{value}</strong></span>
                      <span className="severity-chart-track">
                        <span
                          className={`severity-chart-fill severity-${severity}`}
                          style={{ width: `${percentage}%` }}
                        />
                      </span>
                    </div>
                  );
                })}
              </div>
              {analysis.summary?.priority_findings?.length > 0 && (
                <ul className="summary-priorities">
                  {analysis.summary.priority_findings.slice(0, 3).map((finding) => (
                    <li key={`${finding.title}-${finding.line}`}>
                      <span>{severityLabel(displaySeverity(finding))} · {finding.title}{finding.line ? ` (line ${finding.line})` : ''}</span>
                      <small>{finding.recommended_fix}</small>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <span className={`result-status ${counts.total ? 'has-findings' : 'all-clear'}`}>
              {counts.total ? `${counts.total} ISSUES` : 'ALL CLEAR'}
            </span>
          </section>
        </>
      )}

      <section className="results-section" id="results" aria-label="Analysis results">
        <article className="panel findings-panel">
          <div className="panel-heading findings-heading">
            <div className="panel-title">
              <span className="panel-icon findings-icon"><ShieldAlert size={16} /></span>
              <div>
                <h2>{analysis ? 'Findings & fixes' : 'Review results'}</h2>
                <p>{analysis ? `${counts.total} issue${counts.total === 1 ? '' : 's'} · ${filename}` : 'Your real analysis results will appear here'}</p>
              </div>
            </div>
            {analysis && <span className={`result-status ${counts.total ? 'has-findings' : 'all-clear'}`}>{counts.total ? `${counts.total} FOUND` : 'ALL CLEAR'}</span>}
          </div>
          {analysis ? (
            <>
              <div className="filter-row">
                <span><Filter size={13} /> Filter</span>
                <div className="filter-options" role="group" aria-label="Filter findings by severity">
                  {severityFilters.map((severity) => (
                    <button
                      className={`filter-chip ${severityFilter === severity ? 'filter-active' : ''}`}
                      key={severity}
                      type="button"
                      onClick={() => setSeverityFilter(severity)}
                      aria-pressed={severityFilter === severity}
                    >
                      {severity === 'all' ? 'All' : severityLabel(severity)}
                      {severity === 'all' && <span>{counts.total}</span>}
                      {severity !== 'all' && (
                        <span>{findingsForSeverity(analysis.findings, severity).length}</span>
                      )}
                    </button>
                  ))}
                </div>
                <label className="category-filter">
                  <span>Category</span>
                  <select
                    value={categoryFilter}
                    onChange={(event) => setCategoryFilter(event.target.value)}
                    aria-label="Filter findings by category"
                  >
                    {categories.map((category) => (
                      <option key={category} value={category}>
                        {category === 'all' ? 'All categories' : category}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="finding-list">
                {visibleFindings.length ? visibleFindings.map(({ finding, index }) => (
                  <article
                    className={`finding-card ${activeFinding === finding ? 'finding-active' : ''}`}
                    key={`${finding.title}-${finding.line}-${index}`}
                  >
                    <span className={`finding-indicator severity-${displaySeverity(finding)}`} />
                    <span className="finding-content">
                      <button
                        className="finding-toggle"
                        type="button"
                        onClick={() => {
                          goToFinding(finding);
                          setExpandedFinding(expandedFinding === index ? null : index);
                        }}
                        aria-expanded={expandedFinding === index}
                      >
                      <span className="finding-topline">
                        <span className={`severity-badge severity-${displaySeverity(finding)}`}>{severityLabel(displaySeverity(finding))}</span>
                        {finding.finding_id && <span className="finding-id">{finding.finding_id}</span>}
                        <span className="finding-category">{finding.type}</span>
                        {finding.line && <span className="finding-line">L{finding.line}</span>}
                      </span>
                      <span className="finding-title">{finding.title}</span>
                      <span className="finding-description">{finding.explanation}</span>
                      </button>
                      {expandedFinding === index && (
                        <div className="finding-details">
                          {finding.guidance && (
                            finding.guidance.url ? (
                              <a className="guidance-reference" href={finding.guidance.url} target="_blank" rel="noreferrer">
                                <Shield size={13} /> {finding.rule_id || finding.guidance.reference} · {finding.guidance.standard}
                              </a>
                            ) : (
                              <span className="guidance-reference">
                                <Shield size={13} /> {finding.guidance.standard} · {finding.guidance.reference}
                              </span>
                            )
                          )}
                          {finding.line && (
                            <div className="code-context">
                              <span>Source context · line {finding.line}</span>
                              <code>{code.split('\n')[finding.line - 1]?.trim() || 'Source line unavailable'}</code>
                            </div>
                          )}
                          <span className="finding-fix"><Check size={13} /><span><strong>Recommended fix</strong>{finding.recommended_fix}</span></span>
                          {finding.remediation && (
                            <div className="remediation-comparison">
                              <div>
                                <span>Original code</span>
                                <pre>{finding.remediation.original_code || 'Source context is unavailable for this finding.'}</pre>
                              </div>
                              <div>
                                <span>Corrected code example</span>
                                {finding.remediation.corrected_code ? (
                                  <>
                                    <pre>{finding.remediation.corrected_code}</pre>
                                    <button
                                      className="button button-secondary button-small"
                                      type="button"
                                      onClick={() => copyText(
                                        finding.remediation.corrected_code,
                                        `Fixed code example for ${finding.finding_id || 'finding'} copied.`,
                                      )}
                                    >
                                      <Copy size={13} /> Copy fixed code
                                    </button>
                                  </>
                                ) : (
                                  <p className="remediation-unavailable">
                                    A safe code example cannot be inferred from this diagnostic alone.
                                    Use the recommendation above and validate the change.
                                  </p>
                                )}
                              </div>
                              <p><strong>Why the original is problematic:</strong> {finding.remediation.why_problematic}</p>
                              <p><strong>Why this correction is safer:</strong> {finding.remediation.why_better}</p>
                              {finding.remediation.example_is_template && (
                                <small>Illustrative template — adapt placeholders to your application and database.</small>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </span>
                  </article>
                )) : (
                  <div className="empty-result">
                    <span className="empty-result-icon"><CheckCircle2 size={21} /></span>
                    <h3>{analysis.findings.length ? 'No findings at this severity' : 'Looking good.'}</h3>
                    <p>{analysis.findings.length ? 'Choose another filter to see findings.' : 'No findings from the available static checks. Validate security-sensitive code with your own tests too.'}</p>
                  </div>
                )}
              </div>
              <div className="findings-footer">
                <span><LockKeyhole size={13} /> Static checks only · submitted source never executes</span>
                <span>
                  {Object.entries(analysis.tools || {}).map(([tool, status]) => (
                    <span className={`tool-chip ${status}`} key={tool} title={`${tool}: ${status}`}>
                      {tool} {status === 'available' ? <Check size={10} /> : <span>—</span>}
                    </span>
                  ))}
                </span>
              </div>
            </>
          ) : (
            <div className="empty-workspace">
              <span className="empty-scan-icon"><ScanLine size={23} /></span>
              <h3>Ready for a real review</h3>
              <p>Paste or upload Python / Java above, then analyze to see backend findings here.</p>
              <div className="analysis-checks">
                <span><Check size={13} /> Syntax &amp; compilation</span>
                <span><Check size={13} /> Security vulnerabilities</span>
                <span><Check size={13} /> Code quality</span>
              </div>
            </div>
          )}
        </article>
      </section>

      <section className="capability-rail" aria-label="Implemented and planned review capabilities">
        <span className="capability-heading"><DatabaseZap size={15} /> Secure coding intelligence</span>
        <span className="capability-item capability-active"><CheckCircle2 size={13} /> Syntax &amp; compiler checks</span>
        <span className="capability-item capability-active"><Shield size={13} /> OWASP-guided security checks</span>
        <span className="capability-item capability-active"><Check size={13} /> Remediation guidance</span>
        <span className="capability-separator" />
        <span className="capability-item capability-active"><FileText size={13} /> PR summary &amp; reports</span>
        <span className="capability-item capability-active"><MessageCircle size={13} /> Local knowledge assistant</span>
      </section>

      {analysis && (
        <section className="bottom-actions" id="reports" aria-label="Review actions">
          <div className="analysis-summary">
            <span className="summary-icon"><FileText size={16} /></span>
            <span>
              <strong>Review complete</strong>
              <small>{analysis.auto_fixes_applied ? 'Ruff applied automatic fixes to the suggested version.' : 'No automatic edits to the suggested version.'}</small>
            </span>
          </div>
          <div className="bottom-action-buttons">
            {analysis.suggested_code !== code && (
              <>
                <button className={`button ${showDiff ? 'button-active' : 'button-secondary'}`} type="button" onClick={() => setShowDiff(!showDiff)}>
                  <Code2 size={15} /> {showDiff ? 'Hide diff' : 'View code diff'}
                </button>
                <button className="button button-secondary" type="button" onClick={() => copyText(analysis.suggested_code, 'Suggested code copied to clipboard.')}>
                  <Copy size={15} /> Copy suggested code
                </button>
              </>
            )}
            <button className="button button-secondary" type="button" onClick={downloadReport} disabled={isDownloading}>
              {isDownloading ? <RefreshCw className="spin" size={15} /> : <ArrowDownToLine size={15} />}
              {isDownloading ? 'Generating...' : 'JSON report'}
            </button>
            <button className="button button-secondary" type="button" onClick={downloadMarkdownReport}>
              <ArrowDownToLine size={15} /> Markdown report
            </button>
            <button
              className="button button-secondary"
              type="button"
              onClick={previewPdfReport}
              disabled={isDownloading || isPreviewingPdf}
            >
              {isPreviewingPdf ? <RefreshCw className="spin" size={15} /> : <Eye size={15} />}
              {isPreviewingPdf ? 'Preparing preview...' : 'Preview PDF'}
            </button>
            <button
              className="button button-secondary"
              type="button"
              onClick={downloadPdfReport}
              disabled={isDownloading || isPreviewingPdf}
            >
              {isDownloading ? <RefreshCw className="spin" size={15} /> : <ArrowDownToLine size={15} />}
              {isDownloading ? 'Generating...' : 'Download PDF'}
            </button>
            <button className="button button-primary" type="button" onClick={analyzeCode} disabled={isAnalyzing}>
              <RefreshCw size={15} /> Re-analyze
            </button>
          </div>
        </section>
      )}

      {analysis && pdfPreviewUrl && (
        <section className="panel pdf-preview-panel" aria-label="PDF report preview">
          <div className="panel-heading">
            <div className="panel-title">
              <span className="panel-icon"><FileText size={16} /></span>
              <div>
                <h2>PDF report preview</h2>
                <p>{analysis.summary?.project_name} · {analysis.filename}</p>
              </div>
            </div>
            <button
              className="button button-quiet button-small"
              type="button"
              onClick={() => setPdfPreviewUrl('')}
              aria-label="Close PDF report preview"
            >
              <X size={15} /> Close preview
            </button>
          </div>
          <iframe
            className="pdf-preview-frame"
            src={pdfPreviewUrl}
            title={`PDF report preview for ${analysis.filename}`}
          />
        </section>
      )}

      {!analysis && (
        <div className="report-placeholder" id="reports">
          Run an analysis to generate downloadable JSON, Markdown, and PDF reports.
        </div>
      )}

      <section className="panel assistant-panel" id="assistant" aria-label="Secure coding assistant">
          <div className="panel-heading">
            <div className="panel-title">
              <span className="panel-icon"><MessageCircle size={16} /></span>
              <div>
                <h2>Ask the secure coding guide</h2>
                <p>Local keyword retrieval from the project knowledge base; no external model is used.</p>
              </div>
            </div>
          </div>
          <div className="assistant-content">
            <p className="assistant-context">
              {activeFinding
                ? `Question context: ${activeFinding.title}`
                : 'Ask about a secure coding topic, or analyze code to ask about a specific finding.'}
            </p>
            <div className="assistant-prompts" aria-label="Suggested questions">
              {[
                'How can I fix this finding?',
                'Why is SQL injection dangerous?',
                'Which secure coding guideline applies?',
              ].map((question) => (
                <button
                  className="assistant-prompt"
                  key={question}
                  type="button"
                  onClick={() => setAssistantQuestion(question)}
                  disabled={isAskingAssistant || (question.includes('this finding') && !activeFinding)}
                >
                  {question}
                </button>
              ))}
            </div>
            {assistantMessages.length > 0 && (
              <div className="assistant-messages" role="log" aria-label="Assistant responses">
                {assistantMessages.map((message, index) => (
                  <article className="assistant-message" key={`${index}-${message.question}`}>
                    <strong>{message.question}</strong>
                    <p>{message.answer}</p>
                    {message.sources?.length > 0 && (
                      <div className="assistant-sources">
                        <span>Sources</span>
                        {message.sources.map((source) => (
                          source.url
                            ? <a key={`${source.reference}-${source.title}`} href={source.url} target="_blank" rel="noreferrer">{source.title} · {source.reference}</a>
                            : <span key={`${source.reference}-${source.title}`}>{source.title} · {source.reference}</span>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}
            <form className="assistant-form" onSubmit={askAssistant}>
              <label className="visually-hidden" htmlFor="assistant-question">Ask a secure coding question</label>
              <input
                id="assistant-question"
                type="text"
                value={assistantQuestion}
                onChange={(event) => setAssistantQuestion(event.target.value)}
                maxLength={2000}
                placeholder="e.g. Why is SQL injection dangerous?"
                disabled={isAskingAssistant}
              />
              <button className="button button-primary" type="submit" disabled={isAskingAssistant || !assistantQuestion.trim()}>
                {isAskingAssistant ? <RefreshCw className="spin" size={15} /> : <Send size={15} />}
                {isAskingAssistant ? 'Searching...' : 'Ask'}
              </button>
            </form>
          </div>
      </section>

      {showDiff && analysis?.suggested_code !== code && (
        <section className="panel diff-panel" aria-label="Suggested code changes">
          <div className="panel-heading">
            <div className="panel-title">
              <span className="panel-icon"><Code2 size={16} /></span>
              <div>
                <h2>Suggested code changes</h2>
                <p>Review original and automatically corrected code side by side</p>
              </div>
            </div>
            <button className="icon-button" type="button" onClick={() => setShowDiff(false)} aria-label="Close diff"><X size={16} /></button>
          </div>
          <DiffEditor
            height="340px"
            language={language}
            theme="vs-dark"
            original={code}
            modified={analysis.suggested_code}
            options={{ automaticLayout: true, minimap: { enabled: false }, fontSize: 13, readOnly: true, renderSideBySide: true, scrollBeyondLastLine: false }}
          />
          <div className="diff-footer">
            <span>Review the suggested changes before applying them.</span>
            <button className="button button-primary button-small" type="button" onClick={() => { setCode(analysis.suggested_code); setShowDiff(false); setNotice('Suggested changes applied to the editor.'); }}>
              <Check size={14} /> Apply suggested code
            </button>
          </div>
        </section>
      )}

      <footer className="page-footer">
        <span>AI CODE <span>&amp; SECURITY</span></span>
        <span>Python AST · Ruff · Bandit · javac</span>
        <span>Checks run locally. Source is analyzed, never executed.</span>
      </footer>
    </main>
  );
}

export default App;
