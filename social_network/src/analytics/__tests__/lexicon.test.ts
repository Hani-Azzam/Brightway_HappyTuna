import { lexiconAnalyze, lexiconScore, detectCompany, detectAspects, labelFor } from '../lexicon';

describe('lexicon', () => {
  it('scores positive content above zero and labels it positive', () => {
    const a = lexiconAnalyze('Absolutely love this fresh delicious BrightWay tuna!');
    expect(a.sentimentScore).toBeGreaterThan(0);
    expect(a.sentimentLabel).toBe('positive');
    expect(a.mentionsCompany).toBe(true);
  });

  it('scores negative content below zero and labels it negative', () => {
    const a = lexiconAnalyze('This BrightWay tuna is gross and saltier, total scam.');
    expect(a.sentimentScore).toBeLessThan(0);
    expect(a.sentimentLabel).toBe('negative');
  });

  it('handles negation', () => {
    expect(lexiconScore('not good')).toBeLessThan(0);
  });

  it('detects tuna aspects', () => {
    expect(detectAspects('worried about the mercury and the price')).toEqual(
      expect.arrayContaining(['health', 'price']),
    );
  });

  it('is neutral when there are no sentiment words', () => {
    expect(labelFor(lexiconScore('the tuna aisle is over there'))).toBe('neutral');
  });

  it('does not flag unrelated posts as company mentions', () => {
    expect(detectCompany('I just really like sushi')).toBe(false);
  });
});
