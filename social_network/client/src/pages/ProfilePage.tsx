import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import { Avatar } from '../components/Avatar';
import { AccountBadge } from '../components/AccountBadge';
import { AccountTypePicker } from '../components/AccountTypePicker';
import { FollowButton } from '../components/FollowButton';
import { Feed } from '../components/Feed';
import { useShell } from '../components/shellContext';
import { useAuth } from '../auth/AuthContext';
import type { AccountType, Post, UserWithCounts } from '../types';

export function ProfilePage() {
  const { id = '' } = useParams();
  const { onQuote, onAuthRequired } = useShell();
  const { user: me } = useAuth();
  const [user, setUser] = useState<UserWithCounts | null>(null);
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setUser(null);
    setPosts(null);
    setError(null);
    api
      .getUser(id)
      .then((u) => active && setUser(u))
      .catch((e) => active && setError((e as Error).message));
    api
      .getUserPosts(id)
      .then((p) => active && setPosts(p))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [id]);

  if (error) {
    return (
      <div className="empty">
        <span className="big">⚠️</span>
        {error}
      </div>
    );
  }
  if (!user) return <div className="loading">Loading…</div>;

  return (
    <>
      <header className="sticky-head">
        <h1 className="head-title">
          {user.name}
          <small>{user._count.posts} posts</small>
        </h1>
      </header>

      <div className="profile-head">
        <div className="profile-top">
          <Avatar avatar={user.avatar} accountType={user.accountType} size={64} />
          <FollowButton userId={user.id} onAuthRequired={onAuthRequired} />
        </div>
        <h2 className="profile-name">
          {user.name} <AccountBadge accountType={user.accountType} />
        </h2>
        <div className="profile-handle">@{user.name}</div>
        {user.bio && <p className="profile-bio">{user.bio}</p>}
        <div className="profile-stats">
          <span>
            <b>{user._count.following}</b> Following
          </span>
          <span>
            <b>{user._count.followers}</b> Followers
          </span>
        </div>
        {me?.id === user.id && (
          <AccountTypePicker
            value={user.accountType}
            onChanged={(next: AccountType) => setUser({ ...user, accountType: next })}
          />
        )}
      </div>

      <Feed posts={posts} emptyText="No posts yet." onQuote={onQuote} onAuthRequired={onAuthRequired} />
    </>
  );
}
