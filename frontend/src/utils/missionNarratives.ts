export const isPlaceholderBeliefStatement = (value: string | null | undefined): boolean => {
  const normalized = String(value || '').trim().toLowerCase();
  return (
    normalized.length === 0 ||
    normalized.includes('no evidence-backed belief has been formed yet') ||
    normalized.includes('no belief statement has been formed yet')
  );
};

export const buildBeliefSummary = ({
  statement,
  direction,
  confidence,
  contradictionCount = 0,
}: {
  statement?: string | null;
  direction?: string | null;
  confidence?: number | null;
  contradictionCount?: number;
}): string => {
  if (!isPlaceholderBeliefStatement(statement)) {
    return String(statement).trim();
  }

  const safeDirection = String(direction || 'mixed').toLowerCase();
  const safeConfidence = typeof confidence === 'number' ? Math.max(0, Math.min(1, confidence)) : null;
  const confidenceText = safeConfidence == null ? null : `${Math.round(safeConfidence * 100)}% confidence`;

  if (safeDirection === 'positive') {
    return `The evidence currently leans positive${confidenceText ? `, with ${confidenceText}` : ''}.`;
  }
  if (safeDirection === 'negative') {
    return `The evidence currently leans negative${confidenceText ? `, with ${confidenceText}` : ''}.`;
  }
  if (safeDirection === 'null') {
    return `The evidence currently points toward little or no clear effect${confidenceText ? `, with ${confidenceText}` : ''}.`;
  }
  if (contradictionCount > 0) {
    return `The evidence is currently mixed${confidenceText ? `, with ${confidenceText}` : ''}, because unresolved contradictions are still active.`;
  }
  return `The evidence is currently mixed${confidenceText ? `, with ${confidenceText}` : ''}.`;
};

export const formatReasoningOutcome = (value: string | null | undefined): string => {
  const raw = String(value || '').trim();
  if (!raw) return 'The system recorded an outcome for this revision cycle.';

  const normalized = raw.toUpperCase();
  const confidenceMatch = raw.match(/confidence\s+([0-9.]+)/i);
  const directionMatch = raw.match(/direction\s+([a-z_]+)/i);
  const confidenceText = confidenceMatch ? `${Math.round(Number(confidenceMatch[1]) * 100)}% confidence` : null;
  const directionText = directionMatch ? directionMatch[1].replace(/_/g, ' ') : null;

  if (normalized.includes('CONTRADICTION_PENALTY')) {
    return `A contradiction penalty was applied${confidenceText ? `, leaving the mission at ${confidenceText}` : ''}${directionText ? ` with a ${directionText} direction` : ''}.`;
  }
  if (normalized.includes('NO_UPDATE')) {
    return `The system kept the belief state unchanged${confidenceText ? ` at ${confidenceText}` : ''}${directionText ? ` while staying ${directionText}` : ''}.`;
  }
  if (normalized.includes('REINFORCE')) {
    return `The system reinforced the current belief${confidenceText ? ` to ${confidenceText}` : ''}${directionText ? `, still leaning ${directionText}` : ''}.`;
  }
  if (normalized.includes('WEAKEN')) {
    return `The system weakened the current belief${confidenceText ? ` to ${confidenceText}` : ''}${directionText ? `, now reading as ${directionText}` : ''}.`;
  }
  if (normalized.includes('MATERIAL_UPDATE')) {
    return `The system made a material belief update${confidenceText ? `, moving to ${confidenceText}` : ''}${directionText ? ` with a ${directionText} direction` : ''}.`;
  }
  if (normalized.includes('REVERSAL')) {
    return `The system reversed the prior belief${confidenceText ? `, ending at ${confidenceText}` : ''}${directionText ? ` and now leaning ${directionText}` : ''}.`;
  }
  if (normalized.includes('ESCALATE')) {
    return 'The system escalated this belief change for operator review before applying it automatically.';
  }
  return raw;
};

export const describeContradictionTopic = ({
  intervention,
  outcome,
  pairCount,
  claimCount,
  directionSummary,
}: {
  intervention?: string | null;
  outcome?: string | null;
  pairCount: number;
  claimCount: number;
  directionSummary?: string | null;
}): string => {
  const safeIntervention = intervention || 'this intervention';
  const safeOutcome = outcome || 'this outcome';
  const direction = String(directionSummary || '').toLowerCase();

  if (direction.includes('positive') && direction.includes('negative')) {
    return `The system found directly opposing claims about whether ${safeIntervention} improves or worsens ${safeOutcome}.`;
  }
  if (direction.includes('negative') && direction.includes('null')) {
    return `The system found disagreement about whether ${safeIntervention} harms ${safeOutcome} or has little clear effect.`;
  }
  if (direction.includes('positive') && direction.includes('null')) {
    return `The system found disagreement about whether ${safeIntervention} helps ${safeOutcome} or has little clear effect.`;
  }
  return `This contradiction topic groups ${pairCount} conflicting pair${pairCount === 1 ? '' : 's'} across ${claimCount} claim${claimCount === 1 ? '' : 's'} about ${safeIntervention} and ${safeOutcome}.`;
};
