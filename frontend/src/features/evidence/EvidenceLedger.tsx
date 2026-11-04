import type { EvidenceRecord } from '../../types/api';
import { Icon } from '../../components/Icon';

function evidenceValue(record: EvidenceRecord) {
  if (record.value === null) {
    const count = record.metadata.number_of_points;
    return typeof count === 'number' ? `${count} measurements` : null;
  }
  if (typeof record.value === 'number') {
    const units: Record<string, string> = { percent: '%', celsius: '°C', amperes: 'A', volts: 'V' };
    const unit = record.unit ? units[record.unit] ?? record.unit : '';
    const sign = record.type === 'TEMPERATURE_TREND' && record.value > 0 ? '+' : '';
    return `${sign}${Number(record.value.toFixed(3))}${unit ? ` ${unit}` : ''}`;
  }
  return String(record.value);
}

export function EvidenceLedger({ evidence, cited }: { evidence: EvidenceRecord[]; cited: string[] }) {
  return <section className="panel evidence-panel" aria-labelledby="evidence-title"><header className="panel-heading"><div><span className="section-index">03</span><h2 id="evidence-title">Evidence Ledger</h2></div><span className="count-badge">{evidence.length.toString().padStart(2, '0')}</span></header><div className="ledger-caption"><span className="status-dot" />TRACEABLE OBSERVATIONS</div><div className="evidence-content">{!evidence.length ? <div className="ledger-empty"><div className="ledger-placeholder"><span /><span /><span /></div><h3>No evidence collected yet</h3><p>Tool observations become numbered records. The final diagnosis cites the records it uses.</p><span className="empty-footnote">OBSERVATIONS BEFORE CONCLUSIONS</span></div> : evidence.map(record => {
    const isCited = cited.includes(record.id);
    const value = evidenceValue(record);
    return <article key={record.id} id={`evidence-${record.id}`} className={`evidence-card ${isCited ? 'is-cited' : ''}`}><div className="evidence-card-top"><span className="evidence-id">{record.id}</span>{isCited && <span className="cited-label"><Icon name="check" size={12} />CITED</span>}</div><h3>{record.type.replaceAll('_', ' ')}</h3><span className="source-label">{record.source.replaceAll('_', ' ')}</span><p>{record.summary}</p>{value !== null && <div className={`evidence-value ${typeof record.value === 'string' ? 'text-value' : ''}`}>{value}</div>}{typeof record.metadata.sensor === 'string' && <span className="sensor-label">{record.metadata.sensor} · {String(record.metadata.requested_minutes)} min</span>}<div className="evidence-card-bottom"><span title="Producer-supplied reliability, separate from diagnosis confidence">RELIABILITY <b>{record.reliability.toFixed(2)}</b></span><span className="reliability-meter" aria-hidden="true"><i style={{ width: `${record.reliability * 100}%` }} /></span></div>{record.tool_name && <div className="tool-provenance">↳ {record.tool_name}</div>}</article>;
  })}</div></section>;
}
