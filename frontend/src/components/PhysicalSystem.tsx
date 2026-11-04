import type { EvidenceRecord, ScenarioSummary, TelemetrySnapshot } from '../types/api';
import { VisualInspection } from './VisualInspection';
import { HistoryChart } from './HistoryChart';
import { Icon } from './Icon';

function PanelSchematic() {
  return <svg className="panel-schematic" viewBox="0 0 320 108" role="img" aria-label="Illustrative three-phase panel schematic, not inspection imagery">
    <rect x="38" y="8" width="244" height="87" rx="3" fill="#101923" stroke="#33424e" />
    <path d="M48 18h224M48 85h224" stroke="#25333f" />
    {[['#78a9f3', 96], ['#66d6c5', 160], ['#b7a0e9', 224]].map(([color, position], index) => {
      const x = Number(position);
      return <g key={x} stroke={String(color)} fill="none"><path d={`M${x} 0v27m0 19v60`} strokeWidth="2" /><rect x={x - 15} y="27" width="30" height="24" rx="2" stroke="#526371" fill="#17222c" /><path d={`M${x - 6} 39h12m-6-7v14`} /><circle cx={x} cy="73" r="4" fill="#101923" /><text x={x + 22} y="79" stroke="none" fill={String(color)} fontSize="9" fontFamily="monospace">{['L1', 'L2', 'L3'][index]}</text></g>;
    })}
    <circle cx="48" cy="18" r="1.5" fill="#657885" /><circle cx="272" cy="85" r="1.5" fill="#657885" />
  </svg>;
}

export function PhysicalSystem({ scenario, history, evidence }: { scenario?: ScenarioSummary; history: TelemetrySnapshot[]; evidence: EvidenceRecord[] }) {
  const snapshot = scenario?.initial_snapshot;
  const windowMinutes = snapshot && history.length
    ? Math.round((Date.parse(snapshot.timestamp) - Math.min(...history.map(point => Date.parse(point.timestamp)))) / 60000)
    : null;
  return <section className="panel physical-panel" aria-labelledby="physical-title">
    <header className="panel-heading"><div><span className="section-index">01</span><h2 id="physical-title">Physical System</h2></div><Icon name="activity" /></header>
    <div className="system-id"><div><span className="eyebrow">ELECTRICAL PANEL</span><strong>{scenario?.panel_id ?? '—'}</strong></div><span className="small-label">3-PHASE / AC</span></div>
    <PanelSchematic />
    <div className="telemetry-block"><div className="field-heading"><span>Voltage</span><span>V</span></div><div className="phase-values">{(['a', 'b', 'c'] as const).map(phase => <div key={phase}><span className={`phase-label phase-${phase}`}>PHASE {phase.toUpperCase()}</span><strong>{snapshot ? snapshot[`voltage_${phase}`].toFixed(1) : '—'}</strong></div>)}</div></div>
    <div className="telemetry-block"><div className="field-heading"><span>Current</span><span>A</span></div><div className="phase-values">{(['a', 'b', 'c'] as const).map(phase => <div key={phase}><span className={`phase-label phase-${phase}`}>PHASE {phase.toUpperCase()}</span><strong>{snapshot ? snapshot[`current_${phase}`].toFixed(1) : '—'}</strong></div>)}</div></div>
    <div className="temperature-reading"><div><span className="field-heading">Panel temperature</span><span className="subtle">Current snapshot</span></div><strong>{snapshot?.temperature.toFixed(1) ?? '—'}<small>°C</small></strong></div>
    <div className="history-section"><div className="subsection-heading"><span>TELEMETRY HISTORY</span><span>{windowMinutes === null ? 'AWAITING RUN' : `${windowMinutes} MIN WINDOW`}</span></div><HistoryChart history={history} snapshot={snapshot} kind="current" /><HistoryChart history={history} snapshot={snapshot} kind="temperature" /></div>
    {scenario && (scenario.case_id === 'CASE-001' || scenario.image_available) && <VisualInspection key={scenario.case_id} scenario={scenario} evidence={evidence} />}
    <div className="snapshot-time"><span className="status-dot" />{snapshot ? `Snapshot ${new Date(snapshot.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Loading scenario telemetry'}</div>
  </section>;
}
