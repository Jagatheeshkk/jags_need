"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, BackendUnavailableError } from "./api";

export interface ApiState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  sleeping: boolean;
  reload: () => Promise<void>;
  setData: (d: T) => void;
}

/** Load a GET endpoint; retries with backoff while the free-tier backend is waking up. */
export function useApi<T>(path: string | null, maxRetries = 6): ApiState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError>();
  const [loading, setLoading] = useState(path !== null);
  const [sleeping, setSleeping] = useState(false);

  const load = useCallback(async () => {
    if (path === null) return;
    setLoading(true);
    setError(undefined);
    for (let attempt = 0; ; attempt++) {
      try {
        setData(await api<T>(path));
        setSleeping(false);
        break;
      } catch (e) {
        if (e instanceof BackendUnavailableError && attempt < maxRetries) {
          setSleeping(true);
          await new Promise((r) => setTimeout(r, Math.min(2000 * 2 ** attempt, 15000)));
          continue;
        }
        setSleeping(e instanceof BackendUnavailableError);
        setError(e instanceof ApiError ? e : new ApiError(String(e), 0));
        break;
      }
    }
    setLoading(false);
  }, [path, maxRetries]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetching on mount is the intent
    void load();
  }, [load]);

  return { data, error, loading, sleeping, reload: load, setData };
}
