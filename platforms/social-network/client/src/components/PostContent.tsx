import { Link } from 'react-router-dom';

/** Renders post text, turning #hashtags into links to their hashtag page. */
export function PostContent({ text }: { text: string }) {
  const parts = text.split(/(#[\w]+)/g);
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith('#') && part.length > 1 ? (
          <Link key={i} className="tag" to={`/hashtag/${part.slice(1).toLowerCase()}`} onClick={(e) => e.stopPropagation()}>
            {part}
          </Link>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}
