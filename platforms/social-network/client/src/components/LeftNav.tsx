import { NavLink, useNavigate } from 'react-router-dom';
import { Avatar } from './Avatar';
import { useAuth } from '../auth/AuthContext';

export function LeftNav({ onCompose, onLogin }: { onCompose: () => void; onLogin: () => void }) {
  const { session, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <nav className="leftnav">
      <div className="brand">
        <span className="fish" aria-hidden="true">
          🐟
        </span>
        <span className="label">BrightTweets</span>
      </div>

      <NavLink to="/" end className={({ isActive }) => `navlink ${isActive ? 'active' : ''}`}>
        <span className="ico" aria-hidden="true">
          🏠
        </span>
        <span className="label">Home</span>
      </NavLink>
      <NavLink to="/explore" className={({ isActive }) => `navlink ${isActive ? 'active' : ''}`}>
        <span className="ico" aria-hidden="true">
          🔎
        </span>
        <span className="label">Explore</span>
      </NavLink>
      {session && (
        <NavLink to={`/user/${session.user.id}`} className={({ isActive }) => `navlink ${isActive ? 'active' : ''}`}>
          <span className="ico" aria-hidden="true">
            👤
          </span>
          <span className="label">Profile</span>
        </NavLink>
      )}

      <button className="post-btn" onClick={() => (session ? onCompose() : onLogin())}>
        Post
      </button>

      {session ? (
        <div className="account-chip" role="button" tabIndex={0} onClick={() => navigate(`/user/${session.user.id}`)}>
          <Avatar avatar={session.user.avatar} accountType={session.user.accountType} />
          <div className="who">
            <div className="name">{session.user.name}</div>
            <div className="handle">@{session.user.name}</div>
          </div>
          <button
            className="signout"
            onClick={(e) => {
              e.stopPropagation();
              logout();
            }}
          >
            Sign out
          </button>
        </div>
      ) : (
        <div className="login-cta">
          <p>You’re browsing as a guest.</p>
          <button className="btn-primary" style={{ width: '100%' }} onClick={onLogin}>
            Log in
          </button>
        </div>
      )}
    </nav>
  );
}
