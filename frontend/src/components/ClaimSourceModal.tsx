import React from 'react';
import { ExternalLink, FileText, Link2, X } from 'lucide-react';

import { apiClient } from '@/services/api';
import { ExpandableText } from '@/components/ExpandableText';

interface ClaimSourceModalProps {
  claimId: string | null;
  open: boolean;
  onClose: () => void;
}

interface ClaimDetailResponse {
  id: string;
  statement_raw?: string | null;
  statement_normalized?: string | null;
  paper_title?: string | null;
  doi_or_url?: string | null;
  section_source?: string | null;
  study_design?: string | null;
  provenance?: Record<string, any>;
  direction?: string | null;
  composite_confidence?: number | null;
}

interface ClaimMemoryDetailResponse {
  claim_id: string;
  graph_edges?: any[];
  provenance?: {
    events?: any[];
    count?: number;
  };
}

const readEvidenceExcerpt = (detail: ClaimDetailResponse | null): string | null => {
  if (!detail?.provenance) return null;
  return (
    detail.provenance.evidence_span ||
    detail.provenance.supporting_evidence?.[0]?.evidence_span ||
    detail.provenance.supporting_evidence?.[0]?.excerpt ||
    null
  );
};

const readChunkIds = (detail: ClaimDetailResponse | null): string => {
  const chunkIds =
    detail?.provenance?.resolved_source_chunk_ids ||
    detail?.provenance?.source_chunk_ids ||
    [];
  if (!Array.isArray(chunkIds) || chunkIds.length === 0) return 'Not recorded';
  return chunkIds.map(String).join(', ');
};

const readSections = (detail: ClaimDetailResponse | null): string => {
  const ordered = detail?.provenance?.document_frame?.ordered_sections;
  if (Array.isArray(ordered) && ordered.length > 0) {
    return ordered.join(', ');
  }
  return detail?.section_source || 'unknown';
};

export const ClaimSourceModal: React.FC<ClaimSourceModalProps> = ({ claimId, open, onClose }) => {
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [claimDetail, setClaimDetail] = React.useState<ClaimDetailResponse | null>(null);
  const [memoryDetail, setMemoryDetail] = React.useState<ClaimMemoryDetailResponse | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    const load = async () => {
      if (!open || !claimId) return;
      try {
        setLoading(true);
        setError(null);
        const [claim, memory] = await Promise.all([
          apiClient.getClaim(claimId),
          apiClient.getClaimMemoryDetail(claimId).catch(() => null),
        ]);
        if (cancelled) return;
        setClaimDetail(claim as ClaimDetailResponse);
        setMemoryDetail((memory as ClaimMemoryDetailResponse | null) ?? null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load claim source');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [claimId, open]);

  if (!open || !claimId) return null;

  const statement = claimDetail?.statement_normalized || claimDetail?.statement_raw || 'Claim text unavailable.';
  const evidenceExcerpt = readEvidenceExcerpt(claimDetail);
  const sourceUrl = claimDetail?.doi_or_url || null;
  const relatedEdgeCount = memoryDetail?.graph_edges?.length || 0;
  const provenanceCount = memoryDetail?.provenance?.count || 0;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/55" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="max-h-[88vh] w-full max-w-3xl overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.22)]">
          <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-4">
            <div>
              <h3 className="text-lg font-semibold text-neutral-950">Claim Source</h3>
              <p className="text-sm text-neutral-500">Where this claim came from and how the system grounded it.</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-neutral-200 p-2 text-neutral-600 transition hover:bg-neutral-50 hover:text-neutral-900"
            >
              <X size={18} />
            </button>
          </div>

          <div className="max-h-[78vh] overflow-y-auto p-5">
            {loading ? (
              <div className="rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-8 text-center text-sm text-neutral-600">
                Loading claim source details...
              </div>
            ) : error ? (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-700">
                {error}
              </div>
            ) : (
              <div className="space-y-5">
                <section className="rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-4">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">Claim statement</div>
                  <ExpandableText
                    text={statement}
                    collapsedLines={5}
                    minCharactersToCollapse={220}
                    textClassName="text-sm leading-7 text-neutral-900"
                  />
                </section>

                <section className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-xl border border-neutral-200 bg-white px-4 py-4 shadow-sm">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">Source paper</div>
                    <p className="mt-2 text-sm font-medium text-neutral-900">{claimDetail?.paper_title || 'Unknown paper'}</p>
                    <div className="mt-3 space-y-2 text-sm text-neutral-600">
                      <p>Section: {claimDetail?.section_source || 'unknown'}</p>
                      <p>Study design: {claimDetail?.study_design || 'unknown'}</p>
                      <p>Direction: {claimDetail?.direction || 'unclear'}</p>
                      {claimDetail?.composite_confidence != null && (
                        <p>Confidence: {Math.round(claimDetail.composite_confidence * 100)}%</p>
                      )}
                    </div>
                    {sourceUrl && (
                      <a
                        href={sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-4 inline-flex items-center gap-2 rounded-full border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs font-semibold text-neutral-700 transition hover:bg-neutral-100"
                      >
                        <ExternalLink size={14} />
                        Open source link
                      </a>
                    )}
                  </div>

                  <div className="rounded-xl border border-neutral-200 bg-white px-4 py-4 shadow-sm">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">Grounding details</div>
                    <div className="mt-3 space-y-2 text-sm text-neutral-600">
                      <p>Evidence sections: {readSections(claimDetail)}</p>
                      <p>Chunk IDs: {readChunkIds(claimDetail)}</p>
                      <p>Related memory links: {relatedEdgeCount}</p>
                      <p>Provenance events: {provenanceCount}</p>
                    </div>
                  </div>
                </section>

                <section className="rounded-xl border border-blue-200 bg-blue-50/70 px-4 py-4">
                  <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-blue-700">
                    <FileText size={14} />
                    Evidence excerpt
                  </div>
                  {evidenceExcerpt ? (
                    <ExpandableText
                      text={evidenceExcerpt}
                      collapsedLines={6}
                      minCharactersToCollapse={220}
                      textClassName="text-sm leading-7 text-blue-950"
                    />
                  ) : (
                    <p className="text-sm text-blue-900">No explicit excerpt was recorded for this claim.</p>
                  )}
                </section>

                <section className="rounded-xl border border-neutral-200 bg-white px-4 py-4 shadow-sm">
                  <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">
                    <Link2 size={14} />
                    Why this claim appears in memory
                  </div>
                  <p className="text-sm leading-7 text-neutral-700">
                    LHAS stores the claim text, its evidence span, the paper it came from, and the graph links it participates in. This lets
                    the UI show not just the conclusion, but the path back to the paper and the evidence chunk that produced it.
                  </p>
                </section>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
};
