import { useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import type { Overview } from '../types';
import { useMeta } from '../meta/MetaContext';
import { C, crisisBand, sentimentClass } from './colors';
import { InfoDot } from './InfoDot';

function signed(v: number): string {
  return `${v > 0 ? '+' : ''}${v}`;
}

export function Kpis({ overview }: { overview: Overview }) {
  const { companyName } = useMeta();
  const oi = overview.opinionIndex;
  const woi = overview.weightedOpinionIndex;
  const [oiMode, setOiMode] = useState<'raw' | 'weighted'>('raw');
  const oiValue = oiMode === 'raw' ? oi : woi;
  const band = crisisBand(overview.crisisMeter);
  const { positive, neutral, negative } = overview.sentiment;
  const total = positive + neutral + negative;
  const donut = [
    { name: 'Positive', value: positive, fill: C.kelp },
    { name: 'Neutral', value: neutral, fill: C.neutral },
    { name: 'Negative', value: negative, fill: C.coral },
  ];

  return (
    <div className="kpi-row">
      <div className="card kpi">
        <h3>
          Opinion Index
          <InfoDot
            text={`Net sentiment toward ${companyName} on a −100 to +100 scale: 100 × the mean sentiment of all posts mentioning the company. Use the toggle to switch to the influence-weighted index, which gives greater weight to high-reach authors and widely-shared posts.`}
          />
        </h3>
        <div className="oi-toggle" role="tablist" aria-label="Opinion Index mode">
          <button role="tab" aria-selected={oiMode === 'raw'} className={oiMode === 'raw' ? 'active' : ''} onClick={() => setOiMode('raw')}>
            Raw
          </button>
          <button role="tab" aria-selected={oiMode === 'weighted'} className={oiMode === 'weighted' ? 'active' : ''} onClick={() => setOiMode('weighted')}>
            Influence-weighted
          </button>
        </div>
        <div className={`value ${sentimentClass(oiValue)}`}>{signed(oiValue)}</div>
        <div className="meter">
          <div className="track opinion-track">
            <div className="marker" style={{ left: `${(oiValue + 100) / 2}%` }} />
          </div>
          <div className="scale">
            <span>−100</span>
            <span>0</span>
            <span>+100</span>
          </div>
        </div>
        <div className="sub" style={{ marginTop: 10, marginBottom: 0 }}>
          {oiMode === 'raw' ? 'Every voice weighted equally' : 'High-reach, amplified voices weighted more'}
        </div>
      </div>

      <div className="card kpi">
        <h3>
          Crisis Meter
          <InfoDot text="An early-warning gauge combining the share of recent posts that are negative with the rate at which posting volume is rising. Bands: 0–30 Calm · 30–60 Watch · 60–80 Elevated · 80–100 Crisis." />
        </h3>
        <div className="sub">Negativity × volume velocity</div>
        <div className="value" style={{ color: band.color }}>
          {overview.crisisMeter}
        </div>
        <div className="crisis-band" style={{ color: band.color }}>
          {band.label}
        </div>
        <div className="meter">
          <div className="track crisis-track">
            <div className="crisis-fill" style={{ width: `${overview.crisisMeter}%`, background: band.color }} />
          </div>
        </div>
      </div>

      <div className="card kpi">
        <h3>
          Share of Voice
          <InfoDot text={`The proportion of analysed posts that mention ${companyName}: company posts divided by all analysed posts.`} />
        </h3>
        <div className="sub">Analysed posts about {companyName}</div>
        <div className="value">{Math.round(overview.shareOfVoice * 100)}%</div>
        <div className="sub" style={{ marginTop: 10, marginBottom: 0 }}>
          {overview.totals.companyMentions} of {overview.totals.analyzed} posts
        </div>
      </div>

      <div className="card">
        <h3>
          Sentiment mix
          <InfoDot text="The distribution of company posts across positive, neutral and negative — the spread that underlies the average." />
        </h3>
        <div className="sub">Company-mention posts</div>
        {total === 0 ? (
          <div className="dempty">No analyzed posts yet</div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={120}>
              <PieChart>
                <Pie data={donut} dataKey="value" nameKey="name" innerRadius={34} outerRadius={54} paddingAngle={2} stroke="none">
                  {donut.map((d, i) => (
                    <Cell key={i} fill={d.fill} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="legend">
              <span>
                <span className="dot" style={{ background: C.kelp }} />
                Pos <b>{positive}</b>
              </span>
              <span>
                <span className="dot" style={{ background: C.neutral }} />
                Neu <b>{neutral}</b>
              </span>
              <span>
                <span className="dot" style={{ background: C.coral }} />
                Neg <b>{negative}</b>
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
