import type { CohortReport, CohortStat } from '../types';
import { sentimentClass } from './colors';
import { InfoDot } from './InfoDot';

function signed(v: number): string {
  return `${v > 0 ? '+' : ''}${v}`;
}

/** A −100…+100 opinion bar centred on zero, coloured by sentiment. */
function OpinionBar({ value }: { value: number }) {
  const cls = sentimentClass(value);
  const half = Math.min(50, (Math.abs(value) / 100) * 50);
  return (
    <div className="obar">
      <div className="obar-track">
        <div className="obar-zero" />
        <div className={`obar-fill ${cls}`} style={value >= 0 ? { left: '50%', width: `${half}%` } : { right: '50%', width: `${half}%` }} />
      </div>
    </div>
  );
}

const TYPE_ICON: Record<string, string> = { official: '✓', journalist: '📰', influencer: '★', regular: '' };

export function CohortPanel({ data }: { data: CohortReport | null }) {
  if (!data) return null;
  const { shapers, publicVoice, gap } = data;
  const gapCls = sentimentClass(gap);
  const louder = gap < 0 ? 'more negative than' : gap > 0 ? 'more positive than' : 'in line with';
  const byKey = (k: string) => data.byType.find((c) => c.key === k);

  const headline: Array<{ stat: CohortStat; tag: string }> = [
    { stat: byKey('journalist')!, tag: '📰 Journalists' },
    { stat: byKey('influencer')!, tag: '★ Influencers' },
    { stat: publicVoice, tag: '👥 The public' },
  ];

  return (
    <div className="card">
      <h3>
        Who's shaping opinion
        <InfoDot text="Company sentiment grouped by author type. Journalists and influencers form the shapers; regular accounts form the public. The gap measures how far the shapers diverge from the public. The official company account is reported separately and excluded from both groups." />
      </h3>
      <div className="sub">Journalists &amp; influencers vs. the public · the narrative gap</div>

      {shapers.posts === 0 && publicVoice.posts === 0 ? (
        <div className="dempty">No analyzed posts yet</div>
      ) : (
        <>
          <div className="cohort-compare">
            {headline.map(({ stat, tag }) => (
              <div className="cohort-row" key={stat.key}>
                <div className="cohort-head">
                  <span className="cohort-name">{tag}</span>
                  <span className={`cohort-oi ${sentimentClass(stat.opinionIndex)}`}>{signed(stat.opinionIndex)}</span>
                </div>
                <OpinionBar value={stat.opinionIndex} />
                <div className="cohort-meta">
                  {stat.posts} posts · {stat.authors} voices
                </div>
              </div>
            ))}
          </div>

          <div className={`cohort-gap ${gapCls}`}>
            Press &amp; creators are <b>{signed(gap)}</b> {louder} the public
          </div>

          <table className="dtable cohort-table">
            <thead>
              <tr>
                <th>Cohort</th>
                <th className="num">Posts</th>
                <th className="num">Opinion</th>
              </tr>
            </thead>
            <tbody>
              {data.byType
                .filter((c) => c.posts > 0)
                .map((c) => (
                  <tr key={c.key}>
                    <td>
                      {TYPE_ICON[c.key] && <span className="t-icon">{TYPE_ICON[c.key]}</span>} {c.label}
                    </td>
                    <td className="num">{c.posts}</td>
                    <td className={`num stance ${sentimentClass(c.opinionIndex)}`}>{signed(c.opinionIndex)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
