import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import { Feed } from '../components/Feed';
import { useShell } from '../components/shellContext';
import type { Post } from '../types';

export function HashtagPage() {
  const { tag = '' } = useParams();
  const { onQuote, onAuthRequired } = useShell();
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setPosts(null);
    setError(null);
    api
      .getHashtag(tag)
      .then((d) => active && setPosts(d.posts))
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [tag]);

  return (
    <>
      <header className="sticky-head">
        <h1 className="head-title">
          #{tag}
          <small>Posts mentioning this tag</small>
        </h1>
      </header>
      <Feed posts={posts} error={error} emptyText="No posts with this tag yet." onQuote={onQuote} onAuthRequired={onAuthRequired} />
    </>
  );
}
