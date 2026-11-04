import { useState } from 'react';
import { scenarioImageUrl } from '../api/client';
import type { EvidenceRecord, JsonValue, ScenarioSummary } from '../types/api';
import { Icon } from './Icon';

function isBox(value: JsonValue): value is { object_id: string; left: number; top: number; right: number; bottom: number } {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  return typeof value.object_id === 'string' && ['left', 'top', 'right', 'bottom'].every(key => typeof value[key] === 'number' && Number.isFinite(value[key]));
}

export function VisualInspection({ scenario, evidence }: { scenario: ScenarioSummary; evidence: EvidenceRecord[] }) {
  const [failed, setFailed] = useState(false);
  const visualRecords = evidence.filter(record => record.source === 'VISION' && record.type === 'VISUAL_COMPONENT_OBSERVATION');
  const observations = visualRecords.filter(record => record.tool_name === 'inspect_component_image');
  const conditions = visualRecords.filter(record => record.tool_name === 'inspect_visual_condition');
  return <div className="visual-placeholder"><span className="eyebrow">VISUAL INSPECTION</span>
    {scenario.image_available && !failed ? <>
      <div className="inspection-image"><img src={scenarioImageUrl(scenario.case_id)} alt="Panel component inspection source" onError={() => setFailed(true)} />
        {observations.map(record => {
          const { image_width: width, image_height: height, boxes } = record.metadata;
          if (typeof width !== 'number' || typeof height !== 'number' || width <= 0 || height <= 0 || !Array.isArray(boxes)) return null;
          return <svg key={record.id} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`SAM component boxes for ${record.id}`}>{boxes.filter(isBox).map((box, index) => <rect key={index} x={box.left} y={box.top} width={box.right - box.left} height={box.bottom - box.top} />)}</svg>;
        })}
      </div>
      {!visualRecords.length && <p className="subtle">Visual evidence pending investigation</p>}
    </> : <div className="scan-frame"><Icon name="scan" size={26} /><strong>Visual evidence pending investigation</strong><span>Inspection image unavailable</span></div>}
    {observations.length > 0 && <div className="segmentation-label"><strong>SAM 3.1 segmentation</strong>{observations.map(record => <a href={`#evidence-${record.id}`} key={record.id}>{record.id} · {String(record.metadata.concept)} · {String(record.value)} objects · {String(record.metadata.mask_count)} masks</a>)}<span>Component localization only. Segmentation does not establish the cause of a fault.</span></div>}
    {conditions.length > 0 && <div className="segmentation-label"><strong>Muse Spark 1.3 · visible observations</strong>{conditions.map(record => <div key={record.id}><a href={`#evidence-${record.id}`}>{record.id} · {String(record.metadata.component)}</a><p>{record.summary}</p><span>Image quality: {String(record.metadata.image_quality)}</span></div>)}<span>Visible appearance only. Causal interpretation belongs to the investigation.</span></div>}
  </div>;
}
