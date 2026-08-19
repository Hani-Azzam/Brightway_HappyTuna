import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts';
import type { TimelineBucket } from '../types';
import { C, fmtBucket } from './colors';
import { InfoDot } from './InfoDot';

export function TimelineChart({ data }: { data: TimelineBucket[] }) {
  const rows = data.map((d) => ({ ...d, label: fmtBucket(d.bucket) }));

  return (
    <div className="card">
      <h3>
        Opinion over time
        <InfoDot text="The Opinion Index recalculated for each time bucket, over posts that mention the company." />
      </h3>
      <div className="sub">Opinion Index per hour · company mentions</div>
      {rows.length === 0 ? (
        <div className="dempty">No analyzed posts in the window</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
            <defs>
              <linearGradient id="oiFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={C.tide} stopOpacity={0.4} />
                <stop offset="100%" stopColor={C.tide} stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={C.hairline} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 12, fill: C.slate }} tickLine={false} axisLine={{ stroke: C.hairline }} />
            <YAxis domain={[-100, 100]} tick={{ fontSize: 12, fill: C.slate }} tickLine={false} axisLine={false} width={42} />
            <ReferenceLine y={0} stroke={C.hairline} />
            <Tooltip formatter={(value) => [`${value}`, 'Opinion']} />
            <Area type="monotone" dataKey="opinionIndex" stroke={C.tide} strokeWidth={2.5} fill="url(#oiFill)" dot={{ r: 3, fill: C.tide }} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
