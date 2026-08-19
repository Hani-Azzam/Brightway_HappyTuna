import { ACCOUNT_TYPES, isAccountType, isShaper, typeBoost } from '../accountTypes';

describe('accountTypes', () => {
  it('recognises every allowed account type', () => {
    for (const t of ACCOUNT_TYPES) expect(isAccountType(t)).toBe(true);
  });

  it('rejects unknown values and non-strings', () => {
    expect(isAccountType('wizard')).toBe(false);
    expect(isAccountType(42)).toBe(false);
    expect(isAccountType(undefined)).toBe(false);
  });

  it('treats journalists and influencers as shapers, others not', () => {
    expect(isShaper('journalist')).toBe(true);
    expect(isShaper('influencer')).toBe(true);
    expect(isShaper('official')).toBe(false);
    expect(isShaper('regular')).toBe(false);
  });

  it('weights shapers above regular and defaults unknown types to 1', () => {
    expect(typeBoost('influencer')).toBe(1.5);
    expect(typeBoost('journalist')).toBe(1.5);
    expect(typeBoost('regular')).toBe(1);
    expect(typeBoost('official')).toBe(1);
    expect(typeBoost('mystery')).toBe(1);
  });
});
