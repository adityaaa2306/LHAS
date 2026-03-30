/**
 * useClaimEvents - Hook for listening to claim extraction events
 * Consumes events from the backend claim extraction pipeline
 */

import { useCallback } from 'react';

interface ClaimsExtractedEvent {
  mission_id: string;
  paper_id: string;
  claim_count: number;
  claim_ids: string[];
  timestamp: string;
}

interface PipelineDegradedEvent {
  mission_id: string;
  paper_id: string;
  reason: string;
  pass1_candidates: number;
  errors: string[];
  timestamp: string;
}

type EventCallback<T> = (data: T) => void;

export const useClaimEvents = () => {
  const onClaimsExtracted = useCallback((missionId: string, callback: EventCallback<ClaimsExtractedEvent>) => {
    // In a real implementation, this would connect to a WebSocket or event bus
    // For now, we can emit custom events that components can listen to
    const listener = (event: any) => {
      if (event.detail?.mission_id === missionId) {
        callback(event.detail);
      }
    };

    window.addEventListener('claims:extracted', listener);
    return () => window.removeEventListener('claims:extracted', listener);
  }, []);

  const onPipelineDegraded = useCallback((missionId: string, callback: EventCallback<PipelineDegradedEvent>) => {
    const listener = (event: any) => {
      if (event.detail?.mission_id === missionId) {
        callback(event.detail);
      }
    };

    window.addEventListener('pipeline:degraded', listener);
    return () => window.removeEventListener('pipeline:degraded', listener);
  }, []);

  // Emit events (for testing/development)
  const emitClaimsExtracted = useCallback((data: ClaimsExtractedEvent) => {
    window.dispatchEvent(new CustomEvent('claims:extracted', { detail: data }));
  }, []);

  const emitPipelineDegraded = useCallback((data: PipelineDegradedEvent) => {
    window.dispatchEvent(new CustomEvent('pipeline:degraded', { detail: data }));
  }, []);

  return {
    onClaimsExtracted,
    onPipelineDegraded,
    emitClaimsExtracted,
    emitPipelineDegraded,
  };
};
