import type { InvestigationResponse } from '../types/api';

function number(value?: number | null) {
  return value === null || value === undefined ? '—' : value.toLocaleString();
}

export function UsageStrip({ result }: { result: InvestigationResponse | null }) {
  const model = result?.model && result.model !== 'muse-spark-1.3' ? result.model : 'Muse Spark 1.3';
  return <footer className="usage-strip"><div className="usage-model"><span className="model-glyph">M</span><span>{model}<small>MODEL TRANSPARENCY</small></span></div><div><span>Model requests</span><b>{number(result?.usage.request_count)}</b></div><div><span>Input tokens</span><b>{number(result?.usage.input_tokens)}</b></div><div><span>Output tokens</span><b>{number(result?.usage.output_tokens)}</b></div><div><span>Total tokens</span><b>{number(result?.usage.total_tokens)}</b></div><div className="usage-cost"><span>Estimated Muse API cost {result?.cost_is_partial ? '(partial)' : ''}</span><b>{result?.estimated_cost_usd !== null && result?.estimated_cost_usd !== undefined ? `$${result.estimated_cost_usd.toFixed(5)}` : '—'}</b></div>{result && result.usage.requests_with_usage !== result.usage.request_count && <p className="usage-warning">Token usage available for {result.usage.requests_with_usage} of {result.usage.request_count} requests.</p>}</footer>;
}
