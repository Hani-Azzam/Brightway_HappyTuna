import { extractHashtags } from '../text';

describe('extractHashtags', () => {
  it('extracts unique, lowercased tags without the leading #', () => {
    expect(extractHashtags('Love #BrightWay and #brightway #DolphinSafe!')).toEqual(['brightway', 'dolphinsafe']);
  });

  it('returns an empty array when there are no hashtags', () => {
    expect(extractHashtags('no tags here, just text')).toEqual([]);
  });

  it('ignores a lone # with no word characters', () => {
    expect(extractHashtags('a # b #ok')).toEqual(['ok']);
  });
});
