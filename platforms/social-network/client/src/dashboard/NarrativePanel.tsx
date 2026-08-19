import { Link } from 'react-router-dom';
import type { Narrative } from '../types';
import { C, sentimentClass } from './colors';
import { InfoDot } from './InfoDot';

const ORIGIN_TIP: Record<Narrative['origin'], string> = {
  shaper: 'Originated by a journalist or influencer',
  official: 'Originated by the official company account',
  grassroots: 'Originated by a regular member of the public',
};

function signed(v: number): string {
  return `${v > 0 ? '+' : ''}${v}`;
}

const ORIGIN_LABEL: Record<Narrative['origin'], string> = {
  shaper: 'Shaper-led',
  official: 'Company',
  grassroots: 'Grassroots',
};

const SEGMENTS: Array<{ key: keyof Narrative['byType']; color: string; label: string }> = [
  { key: 'journalist', color: C.slate, label: 'Journalists' },
  { key: 'influencer', color: C.sand, label: 'Influencers' },
  { key: 'official', color: C.tide, label: 'Official' },
  { key: 'regular', color: C.kelp, label: 'Public' },
];

/** Stacked bar showing how a hashtag's posts break down across account types (its propagation). */
function PropagationBar({ byType, total }: { byType: Narrative['byType']; total: number }) {
  return (
    <div className="prop-bar" role="img" aria-label="Propagation by account type">
      {SEGMENTS.map((s) => {
        const n = byType[s.key];
        if (!n) return null;
        return <span key={s.key} title={`${s.label}: ${n}`} style={{ width: `${(n / total) * 100}%`, background: s.color }} />;
      })}
    </div>
  );
}

export function NarrativePanel({ data }: { data: Narrative[] }) {
  return (
    <div className="card">
      <h3>
        Narrative origins
        <InfoDot text="For each hashtag: the account that posted it first (the originator) and whether the origin was a shaper, the official company account, or the grassroots public, together with the distribution of posts across author types — its propagation footprint." />
      </h3>
      <div className="sub">Who started each topic, and how it spread</div>

      {data.length === 0 ? (
        <div className="dempty">No narratives yet</div>
      ) : (
        <ul className="narr-list">
          {data.map((n) => (
            <li className="narr" key={n.tag}>
              <div className="narr-top">
                <Link className="chip-tag" to={`/hashtag/${n.tag}`}>
                  #{n.tag}
                </Link>
                <span className={`origin-badge ${n.origin}`} title={ORIGIN_TIP[n.origin]}>{ORIGIN_LABEL[n.origin]}</span>
                <span className={`narr-sent stance ${sentimentClass(n.sentiment)}`}>{signed(n.sentiment)}</span>
              </div>
              <div className="narr-meta">
                {n.originator ? (
                  <>
                    started by <Link to={`/user/${n.originator.id}`}>@{n.originator.name}</Link>
                  </>
                ) : (
                  'unknown origin'
                )}{' '}
                · {n.posts} posts · {n.authors} voices
              </div>
              <PropagationBar byType={n.byType} total={n.posts} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
