import { Link } from 'react-router-dom';

export function NotFound() {
  return (
    <>
      <header className="sticky-head">
        <h1 className="head-title">Not found</h1>
      </header>
      <div className="empty">
        <span className="big">🪝</span>
        That page doesn’t exist.
        <div style={{ marginTop: 16 }}>
          <Link className="btn-primary" to="/" style={{ padding: '10px 18px', borderRadius: 999 }}>
            Back to feed
          </Link>
        </div>
      </div>
    </>
  );
}
