import { useEffect, useState } from 'react';
import type { TraceStep } from '../../types/api';
import { Icon } from '../../components/Icon';

function ToolResult({ step }: { step: TraceStep }) {
  if (!step.tool_result) return null;
  const entries = Object.entries(step.tool_result);
  return <div className="result-grid">{entries.map(([key, value]) => {
    if (Array.isArray(value)) return <span key={key}><small>{key.replaceAll('_', ' ')}</small><b>{value.length} {key === 'points' ? 'measurements' : 'entries'}</b></span>;
    if (typeof value === 'object' && value !== null) return null;
    return <span key={key}><small>{key.replaceAll('_', ' ')}</small><b>{typeof value === 'number' ? Number(value.toFixed(3)).toString() : value === null ? 'Not recorded' : String(value)}</b></span>;
  })}</div>;
}

export function InvestigationTimeline({ trace, running, startedAt, hasScenario }: {
  trace: TraceStep[]; running: boolean; startedAt: number | null; hasScenario: boolean;
}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!running || startedAt === null) return;
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [running, startedAt]);
  return <section className="panel timeline-panel" aria-labelledby="timeline-title" aria-busy={running}>
    <header className="panel-heading"><div><span className="section-index">02</span><h2 id="timeline-title">Agent Investigation</h2></div><span className={`panel-tag ${running ? 'is-active' : ''}`}>{running ? 'LIVE RUN' : trace.length ? 'COMPLETE' : 'READY'}</span></header>
    <div className="investigation-intro"><span className="micro-label">EVIDENCE-SEEKING WORKFLOW</span><p>Every conclusion starts with a question.</p><div className="workflow"><span>Observe</span><i>→</i><span>Investigate</span><i>→</i><span>Verify</span></div></div>
    <div className="timeline-content">
      <div className="timeline-entry observation"><div className="timeline-marker"><Icon name="activity" size={14} /></div><div className="timeline-card"><span className="event-kind">INITIAL OBSERVATION</span><h3>{hasScenario ? 'Current telemetry received' : 'Waiting for a demo scenario'}</h3><p>The investigation begins with the panel snapshot. Additional observations are collected through tools.</p></div></div>
      {running && <div className="running-state" role="status"><div className="running-visual"><span /><span /><span /><span /><span /></div><h3>Investigation in progress</h3><p>Awaiting the live investigation response.<br />Verified tool activity will appear when the run completes.</p><span className="elapsed"><i className="status-dot pulse" />{elapsed.toString().padStart(2, '0')}s elapsed</span></div>}
      {!running && !trace.length && <div className="timeline-empty"><div className="empty-icon"><Icon name="layers" size={26} /></div><h3>Ready to investigate</h3><p>Run an investigation to see Muse select tools, gather observations, and build a traceable diagnosis.</p><span className="empty-footnote">LIVE MODEL · DETERMINISTIC SCENARIO</span></div>}
      {trace.map(step => {
        const final = step.phase === 'FINALIZATION';
        const label = final ? 'FINALIZATION' : step.kind === 'TOOL_CALL' ? 'TOOL REQUEST' : step.kind === 'TOOL_RESULT' ? 'TOOL RESULT' : step.kind === 'MAX_STEP_TERMINATION' ? 'INVESTIGATION LIMIT' : 'MODEL REVIEW';
        return <div key={step.step_number} className={`timeline-entry event-${step.kind.toLowerCase()} ${final ? 'event-final' : ''}`}><div className="timeline-marker">{step.step_number.toString().padStart(2, '0')}</div><div className="timeline-card"><span className="event-kind">{label}</span><h3>{step.tool_name ? step.tool_name.replaceAll('_', ' ') : step.summary}</h3>{step.kind === 'TOOL_CALL' && step.tool_arguments && <div className="argument-tags">{Object.entries(step.tool_arguments).map(([key, value]) => <span key={key}>{key.replaceAll('_', ' ')} <b>{String(value)}{key === 'minutes' ? ' min' : ''}</b></span>)}</div>}{step.kind === 'TOOL_RESULT' && <ToolResult step={step} />}{step.evidence_ids_added.length > 0 && <div className="evidence-created"><Icon name="check" size={13} /><span>EVIDENCE CREATED</span>{step.evidence_ids_added.map(id => <a href={`#evidence-${id}`} key={id}>{id}</a>)}</div>}</div></div>;
      })}
    </div>
  </section>;
}
