import { useState } from 'react';
import type { TelemetrySnapshot } from '../types/api';

const PHASES = ['A', 'B', 'C'] as const;
const COLORS = ['#78a9f3', '#66d6c5', '#b7a0e9'];

function time(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function HistoryChart({ history, snapshot, kind }: {
  history: TelemetrySnapshot[]; snapshot?: TelemetrySnapshot; kind: 'current' | 'temperature';
}) {
  const [hidden, setHidden] = useState<string[]>([]);
  const series = kind === 'current'
    ? PHASES.map((phase, index) => ({ label: phase, key: `current_${phase.toLowerCase()}` as 'current_a' | 'current_b' | 'current_c', color: COLORS[index] }))
    : [{ label: 'TEMP', key: 'temperature' as const, color: '#d7ad7e' }];
  const points = history.length && snapshot
    ? [...history, snapshot].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp)) : [];
  const allValues = points.flatMap(point => series.map(line => point[line.key]));
  const min = Math.min(...allValues), max = Math.max(...allValues);
  const pad = (max - min) * 0.15 || 1;
  const y = (value: number) => 82 - ((value - min + pad) / (max - min + 2 * pad)) * 70;
  const start = points[0] ? Date.parse(points[0].timestamp) : 0;
  const span = points.length ? Date.parse(points[points.length - 1].timestamp) - start || 1 : 1;
  const x = (timestamp: string) => 8 + ((Date.parse(timestamp) - start) / span) * 268;
  const unit = kind === 'current' ? 'A' : '°C';

  return <div className="history-chart">
    <div className="chart-title"><span>{kind === 'current' ? 'Phase current' : 'Temperature'} <small>/ {unit}</small></span><span className="chart-legend">{series.map(line => <button type="button" key={line.label} className={hidden.includes(line.label) ? 'muted-line' : ''} style={{ color: line.color }} aria-label={`Toggle ${line.label} series`} aria-pressed={!hidden.includes(line.label)} onClick={() => setHidden(previous => previous.includes(line.label) ? previous.filter(item => item !== line.label) : [...previous, line.label])}><i style={{ background: line.color }} />{line.label}</button>)}</span></div>
    <div className="chart-canvas">
      <svg viewBox="0 0 320 106" role="img" aria-label={`${kind} history${points.length ? `, ${points.length} measurements including current snapshot` : ', awaiting investigation'}`}>
        {[16, 47, 78].map(level => <line key={level} x1="8" y1={level} x2="276" y2={level} className="chart-grid" />)}
        {points.length > 0 && <>
          <text x="287" y="20" className="chart-axis">{max.toFixed(1)}</text><text x="287" y="81" className="chart-axis">{min.toFixed(1)}</text>
          <text x="8" y="102" className="chart-axis">{time(points[0].timestamp)}</text><text x="276" y="102" textAnchor="end" className="chart-axis">{time(points[points.length - 1].timestamp)}</text>
          {series.filter(line => !hidden.includes(line.label)).map(line => <g key={line.label}>
            <polyline points={points.map(point => `${x(point.timestamp)},${y(point[line.key])}`).join(' ')} fill="none" stroke={line.color} strokeWidth="1.7" strokeLinejoin="round" />
            {points.map((point, index) => <circle key={`${point.timestamp}-${index}`} cx={x(point.timestamp)} cy={y(point[line.key])} r={index === points.length - 1 ? 3 : 2} fill={line.color}><title>{line.label} · {time(point.timestamp)} · {point[line.key].toFixed(2)} {unit}</title></circle>)}
          </g>)}
        </>}
      </svg>
      {!points.length && <div className="chart-empty">History available after investigation</div>}
    </div>
  </div>;
}
