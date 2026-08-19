import { useState } from 'react';
import { Avatar } from './Avatar';
import { useAuth } from '../auth/AuthContext';
import { useMeta } from '../meta/MetaContext';
import { api } from '../api/client';
import type { Post } from '../types';

const MAX = 500;

export function ComposeBox({
  quoting,
  onPosted,
  onAuthRequired,
  autoFocus,
}: {
  quoting?: Post | null;
  onPosted: (post: Post) => void;
  onAuthRequired: () => void;
  autoFocus?: boolean;
}) {
  const { session } = useAuth();
  const { companyName } = useMeta();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const remaining = MAX - text.length;
  const over = remaining < 0;

  async function submit() {
    if (!session) {
      onAuthRequired();
      return;
    }
    if (!text.trim() || over) return;
    setBusy(true);
    setError(null);
    try {
      const post = await api.createPost(text.trim(), quoting?.id);
      setText('');
      onPosted(post);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="compose">
      <Avatar avatar={session?.user.avatar ?? null} accountType={session?.user.accountType} />
      <div>
        <textarea
          autoFocus={autoFocus}
          placeholder={quoting ? 'Add your take…' : `What's happening with ${companyName}?`}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {quoting && (
          <div className="quote">
            <div className="post-meta">
              <span className="name">{quoting.user.name}</span>
              <span className="handle">@{quoting.user.name}</span>
            </div>
            <p className="post-content">{quoting.content}</p>
          </div>
        )}
        {error && <p className="error-text">{error}</p>}
        <div className="row">
          <span className={`count ${over ? 'over' : ''}`}>{remaining}</span>
          <button className="btn-primary" disabled={busy || !text.trim() || over} onClick={submit}>
            Post
          </button>
        </div>
      </div>
    </div>
  );
}
