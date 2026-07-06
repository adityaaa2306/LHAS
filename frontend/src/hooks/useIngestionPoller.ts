import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '@/services/api';
import type { IngestionStatusResponse } from '@/types/ingestion';

const BASE_INTERVAL_MS = 2500;
const MAX_INTERVAL_MS = 15000;
const HARD_TIMEOUT_MS = 15 * 60 * 1000;

interface UseIngestionPollerOptions {
  missionId: string | undefined;
  enabled: boolean;
  onComplete?: (status: IngestionStatusResponse) => void;
  onFailed?: (status: IngestionStatusResponse) => void;
  onProgress?: (status: IngestionStatusResponse) => void;
}

export function useIngestionPoller({
  missionId,
  enabled,
  onComplete,
  onFailed,
  onProgress,
}: UseIngestionPollerOptions) {
  const [status, setStatus] = useState<IngestionStatusResponse | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const pollInFlight = useRef(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hardTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intervalMs = useRef(BASE_INTERVAL_MS);
  const consecutiveErrors = useRef(0);
  const stoppedRef = useRef(false);
  const callbacksRef = useRef({ onComplete, onFailed, onProgress });
  callbacksRef.current = { onComplete, onFailed, onProgress };

  const stopPolling = useCallback(() => {
    stoppedRef.current = true;
    setIsPolling(false);
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (hardTimeoutRef.current) {
      clearTimeout(hardTimeoutRef.current);
      hardTimeoutRef.current = null;
    }
  }, []);

  const pollOnceRef = useRef<() => Promise<void>>(async () => {});

  const scheduleNext = useCallback((delay: number) => {
    if (stoppedRef.current || !missionId) return;
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => void pollOnceRef.current(), delay);
  }, [missionId]);

  const pollOnce = useCallback(async () => {
    if (!missionId || stoppedRef.current || pollInFlight.current) return;

    pollInFlight.current = true;
    setIsPolling(true);

    try {
      const data = await apiClient.getIngestionStatus(missionId, { silentTimeout: true });
      consecutiveErrors.current = 0;
      intervalMs.current = BASE_INTERVAL_MS;
      setStatus(data);
      callbacksRef.current.onProgress?.(data);

      if (data.status === 'completed') {
        stopPolling();
        callbacksRef.current.onComplete?.(data);
        return;
      }
      if (data.status === 'failed') {
        stopPolling();
        callbacksRef.current.onFailed?.(data);
        return;
      }

      scheduleNext(intervalMs.current);
    } catch (err) {
      consecutiveErrors.current += 1;
      const isTimeout =
        err instanceof Error && err.message.includes('timeout');

      // Ignore isolated timeouts — don't spam console
      if (!isTimeout || consecutiveErrors.current > 2) {
        if (consecutiveErrors.current > 2) {
          console.warn('[ingestion-poll] repeated failures, backing off', err);
        }
      }

      intervalMs.current = Math.min(
        BASE_INTERVAL_MS * 2 ** consecutiveErrors.current,
        MAX_INTERVAL_MS,
      );
      scheduleNext(intervalMs.current);
    } finally {
      pollInFlight.current = false;
      if (!stoppedRef.current) {
        setIsPolling(true);
      } else {
        setIsPolling(false);
      }
    }
  }, [missionId, scheduleNext, stopPolling]);

  pollOnceRef.current = pollOnce;

  useEffect(() => {
    if (!enabled || !missionId) {
      stopPolling();
      return;
    }

    stoppedRef.current = false;
    consecutiveErrors.current = 0;
    intervalMs.current = BASE_INTERVAL_MS;

    hardTimeoutRef.current = setTimeout(() => {
      stopPolling();
    }, HARD_TIMEOUT_MS);

    void pollOnce();

    return () => {
      stopPolling();
    };
  }, [enabled, missionId, pollOnce, stopPolling]);

  return { status, isPolling, stopPolling };
}
