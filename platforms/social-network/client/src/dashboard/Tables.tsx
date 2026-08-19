import { Link } from 'react-router-dom';
import type { Influencer, Spike, TopPost, TrendStat } from '../types';
import { fmtBucket, sentimentClass } from './colors';
import { InfoDot } from './InfoDot';

function signed(v: number): string {
  return `${v > 0 ? '+' : ''}${v}`;
}

export function TrendsTable({ data }: { data: TrendStat[] }) {
  return (
    <div className="card">
      <h3>
        Trending topics
        <InfoDot text="The most-used hashtags in the current window, with a rising multiplier (current count divided by the previous window's count) and the mean sentiment of their posts." />
      </h3>
      <div className="sub">Current window · rising = vs. previous window</div>
      {data.length === 0 ? (
        <div className="dempty">No hashtags yet</div>
      ) : (
        <table className="dtable">
          <thead>
            <tr>
              <th>Tag</th>
              <th className="num">Posts</th>
              <th className="num">Rising</th>
              <th className="num">Sentiment</th>
            </tr>
          </thead>
          <tbody>
            {data.map((t) => (
              <tr key={t.tag}>
                <td>
                  <Link className="chip-tag" to={`/hashtag/${t.tag}`}>
                    #{t.tag}
                  </Link>
                </td>
                <td className="num">{t.count}</td>
                <td className="num">{t.rising}×</td>
                <td className={`num stance ${sentimentClass(t.sentiment)}`}>{signed(t.sentiment)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const TYPE_ICON: Record<string, string> = { official: '✓', journalist: '📰', influencer: '★' };

export function InfluencerTable({ data }: { data: Influencer[] }) {
  return (
    <div className="card">
      <h3>
        Top influencers
        <InfoDot text="Accounts ranked by reach: ln(1 + followers) + 0.5 · ln(1 + reposts received) + an account-type weight. Stance is the account's own mean sentiment toward the company." />
      </h3>
      <div className="sub">Reach-weighted · stance = their company sentiment</div>
      <table className="dtable">
        <thead>
          <tr>
            <th>Account</th>
            <th className="num">Influence</th>
            <th className="num">Followers</th>
            <th className="num">Stance</th>
          </tr>
        </thead>
        <tbody>
          {data.map((u) => (
            <tr key={u.id}>
              <td>
                <Link to={`/user/${u.id}`}>{u.name}</Link>{' '}
                {TYPE_ICON[u.accountType] && <span title={u.accountType}>{TYPE_ICON[u.accountType]}</span>}
              </td>
              <td className="num">{u.influence}</td>
              <td className="num">{u.followers}</td>
              <td className={u.stance === null ? 'num stance neu' : `num stance ${sentimentClass(u.stance)}`}>
                {u.stance === null ? '—' : signed(u.stance)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SpikeList({ data }: { data: Spike[] }) {
  return (
    <div className="card">
      <h3>
        Detected events
        <InfoDot text="Company events are not announced to the platform, so they are inferred: any time bucket whose posting volume is at least two standard deviations above the mean is flagged, with its z-score and the sentiment recorded during it." />
      </h3>
      <div className="sub">Volume spikes inferred from the data</div>
      {data.length === 0 ? (
        <div className="dempty">No volume spikes in the window</div>
      ) : (
        <table className="dtable">
          <thead>
            <tr>
              <th>When</th>
              <th className="num">Posts</th>
              <th className="num">Z-score</th>
              <th className="num">Sentiment</th>
            </tr>
          </thead>
          <tbody>
            {data.map((s) => (
              <tr key={s.bucket}>
                <td>{fmtBucket(s.bucket)}</td>
                <td className="num">{s.volume}</td>
                <td className="num">{s.zScore}</td>
                <td className={`num stance ${sentimentClass(s.sentiment)}`}>{signed(s.sentiment)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function TopPostsList({ data }: { data: TopPost[] }) {
  return (
    <div className="card">
      <h3>
        Top posts
        <InfoDot text="The most-engaged posts, ranked by likes + reposts + replies." />
      </h3>
      <div className="sub">By engagement (likes + reposts + replies)</div>
      {data.length === 0 ? (
        <div className="dempty">No posts yet</div>
      ) : (
        <table className="dtable">
          <thead>
            <tr>
              <th>Post</th>
              <th className="num">Engagement</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(0, 6).map((t) => (
              <tr key={t.post.id}>
                <td>
                  <Link to={`/post/${t.post.id}`}>
                    <b>@{t.post.user.name}</b> {t.post.content.slice(0, 56)}
                    {t.post.content.length > 56 ? '…' : ''}
                  </Link>
                </td>
                <td className="num">{t.engagement}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
