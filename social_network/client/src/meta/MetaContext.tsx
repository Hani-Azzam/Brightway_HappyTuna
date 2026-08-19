import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type { Meta } from '../types';

// Until /api/meta resolves we show neutral placeholders — never a hardcoded company name.
const FALLBACK: Meta = { platformName: 'BrightTweets', companyName: 'the company' };

const MetaContext = createContext<Meta>(FALLBACK);

/**
 * Fetches the platform/company branding once and provides it to the whole app, so no component
 * ever hardcodes the company name. The name comes entirely from the API (driven by COMPANY_NAME).
 */
export function MetaProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta>(FALLBACK);

  useEffect(() => {
    let active = true;
    api
      .getMeta()
      .then((m) => active && setMeta(m))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  return <MetaContext.Provider value={meta}>{children}</MetaContext.Provider>;
}

/** Branding for the platform + the company under study. */
export function useMeta(): Meta {
  return useContext(MetaContext);
}
