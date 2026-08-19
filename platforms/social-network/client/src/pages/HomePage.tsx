import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { ComposeBox } from '../components/ComposeBox';
import { Feed } from '../components/Feed';
import { useShell } from '../components/shellContext';
import type { Post } from '../types';

type Tab = 'latest' | 'following';

export function HomePage() {
  const { session } = useAuth();
  const { onAuthRequired, onQuote } = useShell();
  const [tab, setTab] = useState<Tab>('latest');
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setPosts(null);
    setError(null);
    const load = tab === 'following' && session ? api.getMyFeed(session.user.id) : api.getGlobalFeed();
    load
      .then((data) => active && setPosts(data))
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [tab, session]);

  return (
    <>
      <header className="sticky-head">
        <h1 className="head-title">Home</h1>
      </header>

      {session && (
        <div className="tabs">
          <button className={`tab ${tab === 'latest' ? 'active' : ''}`} onClick={() => setTab('latest')}>
            Latest
          </button>
          <button className={`tab ${tab === 'following' ? 'active' : ''}`} onClick={() => setTab('following')}>
            Following
          </button>
        </div>
      )}

      {session ? (
        <ComposeBox onPosted={(post) => setPosts((prev) => (prev ? [post, ...prev] : [post]))} onAuthRequired={onAuthRequired} />
      ) : (
        <div className="login-cta" style={{ margin: 16 }}>
          <p>You’re watching the conversation as a guest. Log in to post, like, and follow.</p>
          <button className="btn-primary" onClick={onAuthRequired}>
            Log in
          </button>
        </div>
      )}

      <Feed
        posts={posts}
        error={error}
        emptyText={tab === 'following' ? 'Follow some accounts to fill this feed.' : 'No posts yet.'}
        onQuote={onQuote}
        onAuthRequired={onAuthRequired}
      />
    </>
  );
}
