import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, checkHealth, investigate, listScenarios } from './api/client';
import { Icon } from './components/Icon';
import { PhysicalSystem } from './components/PhysicalSystem';
import { UsageStrip } from './components/UsageStrip';
import { DiagnosisOverview, DiagnosisPanel } from './features/diagnosis/DiagnosisPanel';
import { EvidenceLedger } from './features/evidence/EvidenceLedger';
import { InvestigationTimeline } from './features/investigation/InvestigationTimeline';
import type { InvestigationResponse, ScenarioSummary } from './types/api';

const LABELS: Record<string, string> = {
  'CASE-001': 'Connection Heating', 'CASE-002': 'Phase Imbalance', 'CASE-003': 'Overload', 'CASE-004': 'Insufficient Evidence',
};

function toError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError('REQUEST_FAILED', 'The request could not be completed. Please retry.');
}

export default function App() {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selected, setSelected] = useState('');
  const [result, setResult] = useState<InvestigationResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [catalogError, setCatalogError] = useState<ApiError | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [connected, setConnected] = useState<boolean | null>(null);
  const inFlight = useRef(false);

  const refreshScenarios = useCallback(async (signal?: AbortSignal) => {
    setCatalogLoading(true);
    try {
      const data = await listScenarios(signal);
      if (!Array.isArray(data) || !data.length) throw new ApiError('SCENARIOS_UNAVAILABLE', 'No demo scenarios are available from the backend.');
      if (signal?.aborted) return;
      setScenarios(data);
      setConnected(true);
      setSelected(previous => data.some(item => item.case_id === previous) ? previous : data[0].case_id);
      setCatalogError(null);
    } catch (caught) {
      if (!signal?.aborted) setCatalogError(toError(caught));
    } finally {
      if (!signal?.aborted) setCatalogLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refreshScenarios(controller.signal);
    let disposed = false;
    const refreshConnection = () => { void checkHealth().then(ok => { if (!disposed) setConnected(ok); }); };
    refreshConnection();
    const timer = window.setInterval(refreshConnection, 30000);
    return () => { controller.abort(); disposed = true; window.clearInterval(timer); };
  }, [refreshScenarios]);

  async function run() {
    if (!selected || inFlight.current) return;
    inFlight.current = true;
    setRunning(true);
    setStartedAt(Date.now());
    setResult(null);
    setError(null);
    try {
      const response = await investigate(selected);
      setResult(response);
      setConnected(true);
    } catch (caught) {
      const failure = toError(caught);
      setError(failure);
      if (failure.code === 'BACKEND_UNREACHABLE') setConnected(false);
    } finally {
      inFlight.current = false;
      setRunning(false);
    }
  }

  const scenario = result?.case ?? scenarios.find(item => item.case_id === selected);
  const failure = error ?? catalogError;
  const connectionLabel = connected === null ? 'CONNECTING' : connected ? 'BACKEND CONNECTED' : 'BACKEND OFFLINE';

  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="/" aria-label="GridProbe home"><img src="/favicon.svg" alt="" width="34" height="34" /><div><strong>GridProbe<span className="brand-period">.</span></strong><span>Evidence-Seeking AI Diagnostic Agent</span></div></a><div className="topbar-right"><span className="console-label">INVESTIGATION CONSOLE <b>01</b></span><span className={`connection ${connected ? 'online' : connected === false ? 'offline' : ''}`}><i className="status-dot" />{connectionLabel}</span></div></header>
    <main>
      <div className="page-heading"><div><div className="breadcrumb">OPERATIONS <span>/</span> PHYSICAL INFRASTRUCTURE</div><h1>Panel investigation<span className="heading-dot" /></h1><p>Active investigation. Traceable evidence. Qualified decisions.</p></div><div className="mode-label"><span className="mode-mark" />DETERMINISTIC DEMO<span className="mode-separator" />LIVE MUSE MODEL</div></div>
      <section className="command-bar" aria-label="Investigation controls"><div className="scenario-control"><label htmlFor="scenario">SELECT INCIDENT</label><div className="select-wrap"><select id="scenario" value={selected} disabled={running || catalogLoading || !scenarios.length} onChange={event => { setSelected(event.target.value); setResult(null); setError(null); }}>{!scenarios.length && <option value="">{catalogLoading ? 'Loading scenarios…' : 'Scenarios unavailable'}</option>}{scenarios.map(item => <option value={item.case_id} key={item.case_id}>{item.case_id} {LABELS[item.case_id] ?? item.case_id}</option>)}</select><span aria-hidden="true">⌄</span></div></div><div className="incident-fact"><span>ACTIVE PANEL</span><strong>{scenario?.panel_id ?? '—'}</strong></div><div className="incident-fact"><span>INCIDENT ID</span><strong>{scenario?.case_id ?? '—'}</strong></div><div className="incident-fact model-fact"><span>REASONING MODEL</span><strong>Muse Spark 1.3</strong></div><button className="run-button" type="button" disabled={running || !scenario || catalogLoading} onClick={() => void run()}>{running ? <span className="spinner" /> : <Icon name="play" size={15} />}<span>{running ? 'INVESTIGATING' : 'RUN INVESTIGATION'}</span>{!running && <Icon name="arrow" size={17} />}</button></section>
      {failure && <div className="error-banner" role="alert"><Icon name="alert" size={21} /><div><strong>{failure.code === 'MODEL_NOT_CONFIGURED' ? 'Model access needs configuration' : failure.code === 'PROVIDER_UNAVAILABLE' ? 'Model provider unavailable' : failure.code === 'INVALID_DIAGNOSIS' ? 'Diagnosis could not be validated' : failure.code === 'BACKEND_UNREACHABLE' ? 'Backend unavailable' : 'Unable to complete this request'}</strong><p>{failure.message}</p></div><button type="button" className="secondary-button" disabled={running} onClick={() => { if (catalogError) void refreshScenarios(); else void run(); }}><Icon name="refresh" size={15} />Retry</button></div>}
      {result && <DiagnosisOverview diagnosis={result.diagnosis} />}
      <div className="workspace"><PhysicalSystem scenario={scenario} history={result?.case.history ?? []} /><InvestigationTimeline trace={result?.trace ?? []} running={running} startedAt={startedAt} hasScenario={!!scenario} /><EvidenceLedger evidence={result?.evidence ?? []} cited={result?.diagnosis.evidence_ids ?? []} /></div>
      <DiagnosisPanel diagnosis={result?.diagnosis} running={running} limited={result?.termination_reason === 'MAX_AGENT_STEPS'} />
      <UsageStrip result={result} />
      <div className="page-footnote"><span>GRIDPROBE <b>/</b> EVIDENCE-SEEKING DIAGNOSTICS</span><span>Decision-support prototype for qualified maintenance personnel.</span></div>
    </main>
  </div>;
}
