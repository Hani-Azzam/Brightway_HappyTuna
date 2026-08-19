import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { Avatar } from '../components/Avatar';
import { AccountBadge } from '../components/AccountBadge';
import { Feed } from '../components/Feed';
import { useShell } from '../components/shellContext';
import { useMeta } from '../meta/MetaContext';
import type { SearchResults, TrendingTag } from '../types';

export function ExplorePage() {
  const [params] = useSearchParams();
  const query = params.get('q') ?? '';
  const { onQuote, onAuthRequired } = useShell();
  const { companyName } = useMeta();
  const [results, setResults] = useState<SearchResults | null>(null);
  const [trends, setTrends] = useState<TrendingTag[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (!query) {
      setResults(null);
      api.getTrending(15).then((t) => active && setTrends(t)).catch(() => undefined);
      return () => {
        active = false;
      };
    }
    setResults(null);
    setError(null);
    api
      .search(query)
      .then((r) => active && setResults(r))
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [query]);

  return (
    <>
      <header className="sticky-head">
        <h1 className="head-title">
          {query ? `Results for “${query}”` : 'Explore'}
          {!query && <small>What people are saying about {companyName}</small>}
        </h1>
      </header>

      {!query ? (
        trends.length === 0 ? (
          <div className="empty">
            <span className="big">🌊</span>
            No trends yet.
          </div>
        ) : (
          <div className="feed">
            {trends.map((t, i) => (
              <Link
                key={t.tag}
                className="row-item trend"
                to={`/hashtag/${t.tag}`}
                style={{ display: 'block', borderBottom: '1px solid var(--hairline)' }}
              >
                <div className="meta">{i + 1} · Trending</div>
                <div className="tag">#{t.tag}</div>
                <div className="meta">
                  {t.count} post{t.count !== 1 ? 's' : ''}
                </div>
              </Link>
            ))}
          </div>
        )
      ) : (
        <>
          {results && results.users.length > 0 && (
            <section>
              {results.users.map((u) => (
                <div key={u.id} className="row-item" style={{ borderBottom: '1px solid var(--hairline)' }}>
                  <Avatar avatar={u.avatar} accountType={u.accountType} />
                  <Link className="who" to={`/user/${u.id}`}>
                    <div className="name">
                      {u.name} <AccountBadge accountType={u.accountType} />
                    </div>
                    <div className="handle">@{u.name}</div>
                  </Link>
                </div>
              ))}
            </section>
          )}
          <Feed posts={results?.posts ?? null} error={error} emptyText="No posts found." onQuote={onQuote} onAuthRequired={onAuthRequired} />
        </>
      )}
    </>
  );
}
