import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { Avatar } from './Avatar';
import { AccountBadge } from './AccountBadge';
import { FollowButton } from './FollowButton';
import type { TrendingTag, UserWithCounts } from '../types';

export function RightRail({ onAuthRequired }: { onAuthRequired: () => void }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [trends, setTrends] = useState<TrendingTag[]>([]);
  const [people, setPeople] = useState<UserWithCounts[]>([]);

  useEffect(() => {
    api.getTrending(6).then(setTrends).catch(() => undefined);
    api
      .getUsers(1)
      .then((users) => setPeople(users.slice(0, 4)))
      .catch(() => undefined);
  }, []);

  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) navigate(`/explore?q=${encodeURIComponent(query.trim())}`);
  }

  return (
    <aside className="rightrail">
      <form className="sticky-search" onSubmit={submitSearch}>
        <div className="search-box">
          <span aria-hidden="true">🔎</span>
          <input
            placeholder="Search BrightTweets"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search"
          />
        </div>
      </form>

      <section className="panel">
        <h2>Trends</h2>
        {trends.length === 0 ? (
          <div className="row-item">
            <span className="meta">No trends yet.</span>
          </div>
        ) : (
          trends.map((t) => (
            <Link key={t.tag} className="row-item trend" to={`/hashtag/${t.tag}`}>
              <div>
                <div className="tag">#{t.tag}</div>
                <div className="meta">
                  {t.count} post{t.count !== 1 ? 's' : ''}
                </div>
              </div>
            </Link>
          ))
        )}
      </section>

      <section className="panel">
        <h2>Who to follow</h2>
        {people.map((p) => (
          <div key={p.id} className="row-item">
            <Avatar avatar={p.avatar} accountType={p.accountType} />
            <Link className="who" to={`/user/${p.id}`}>
              <div className="name">
                {p.name} <AccountBadge accountType={p.accountType} />
              </div>
              <div className="handle">@{p.name}</div>
            </Link>
            <FollowButton userId={p.id} onAuthRequired={onAuthRequired} />
          </div>
        ))}
      </section>

      <Link className="research-link" to="/dashboard">
        📊 Research dashboard →
      </Link>
    </aside>
  );
}
