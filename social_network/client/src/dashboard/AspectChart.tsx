import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine, CartesianGrid } from 'recharts';
import type { AspectStat } from '../types';
import { C, sentimentColor } from './colors';
import { InfoDot } from './InfoDot';

interface Row extends AspectStat {
  short: string;
}

export function AspectChart({ data }: { data: AspectStat[] }) {
  const rows: Row[] = data.map((a) => ({ ...a, short: a.label.split(' / ')[0]! }));
  const hasData = rows.some((r) => r.volume > 0);

  return (
    <div className="card">
      <h3>
        Aspect sentiment
        <InfoDot text="Mean sentiment for each of the six product aspects (sustainability, health, price, taste, ethics, safety), with the number of posts addressing each (n). Identifies which issue is driving sentiment; bar length shows how strongly positive or negative." />
      </h3>
      <div className="sub">Which issue drives the mood</div>
      {!hasData ? (
        <div className="dempty">No analyzed posts yet</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart layout="vertical" data={rows} margin={{ top: 4, right: 12, bottom: 0, left: 8 }}>
            <CartesianGrid stroke={C.hairline} horizontal={false} />
            <XAxis type="number" domain={[-100, 100]} tick={{ fontSize: 12, fill: C.slate }} tickLine={false} axisLine={{ stroke: C.hairline }} />
            <YAxis type="category" dataKey="short" width={86} tick={{ fontSize: 12, fill: C.ink }} tickLine={false} axisLine={false} />
            <ReferenceLine x={0} stroke={C.slate} />
            <Tooltip
              formatter={(value, _name, item) => {
                const row = item?.payload as Row | undefined;
                return [`${value} (n=${row?.volume ?? 0})`, 'Sentiment'];
              }}
            />
            <Bar dataKey="sentiment" radius={[0, 4, 4, 0]} barSize={16}>
              {rows.map((r, i) => (
                <Cell key={i} fill={r.volume === 0 ? C.hairline : sentimentColor(r.sentiment)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
