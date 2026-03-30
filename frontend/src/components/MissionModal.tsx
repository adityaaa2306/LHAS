import React from 'react';
import { X, Loader, Zap, CheckCircle } from 'lucide-react';
import { ClarificationPanel } from './ClarificationPanel';
import type { IntentType } from '@/types';

interface MissionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (missionData: MissionFormData) => Promise<void>;
}

export interface MissionFormData {
  name: string;
  query: string;
  intent_type: IntentType;
  pico_population?: string;
  pico_intervention?: string;
  pico_comparator?: string;
  pico_outcome?: string;
  key_concepts?: string[];
}

interface QueryAnalysisResult {
  original_query: string;
  normalized_query: string;
  intent_type: string;
  pico: {
    population: string | null;
    intervention: string | null;
    comparator: string | null;
    outcome: string | null;
  };
  key_concepts: string[];
  search_queries: string[];
  ambiguity_flags: string[];
  interpretation_variants: string[];
  suggested_refinements: string[];
  confidence_score: number;
  decision: string;
  reasoning_steps: string[];
}

interface UIQuestion {
  question: string;
  options: string[];
}

const INTENT_TYPES: IntentType[] = ['Causal', 'Comparative', 'Exploratory', 'Descriptive'];

export const MissionModal: React.FC<MissionModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [loading, setLoading] = React.useState(false);
  const [analyzing, setAnalyzing] = React.useState(false);
  const [analyzed, setAnalyzed] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [usePico, setUsePico] = React.useState(false);
  const [useKeyConcepts, setUseKeyConcepts] = React.useState(false);

  // Clarification flow (Module 3)
  const [needsClarification, setNeedsClarification] = React.useState(false);
  const [clarificationQuestions, setClarificationQuestions] = React.useState<UIQuestion[]>([]);
  const [lastAnalysis, setLastAnalysis] = React.useState<QueryAnalysisResult | null>(null);

  const [formData, setFormData] = React.useState<MissionFormData>({
    name: '',
    query: '',
    intent_type: 'Exploratory',
  });

  const [keyConcepts, setKeyConcepts] = React.useState<string>('');

  const resetForm = () => {
    setFormData({
      name: '',
      query: '',
      intent_type: 'Exploratory',
    });
    setKeyConcepts('');
    setUsePico(false);
    setUseKeyConcepts(false);
    setAnalyzed(false);
    setError(null);
    setNeedsClarification(false);
    setClarificationQuestions([]);
    setLastAnalysis(null);
  };

  const handleAnalyzeQuery = async () => {
    if (!formData.query.trim()) {
      setError('Please enter a research question first');
      return;
    }

    setAnalyzing(true);
    setError(null);
    try {
      console.log('Starting query analysis for:', formData.query);
      const response = await fetch('http://localhost:8000/api/query/understand', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: formData.query.trim() }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API error: ${response.status} - ${errorText}`);
      }

      const analysis: QueryAnalysisResult = await response.json();
      console.log('Analysis successful:', analysis);

      // Step 1: Store analysis for later use
      setLastAnalysis(analysis);

      // Step 2: Check if clarification is needed
      if (analysis.decision === 'NEED_CLARIFICATION') {
        console.log('Query needs clarification, calling Module 3');
        try {
          const clarifResponse = await fetch('http://localhost:8000/api/query/clarification', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ analysis }),
          });

          if (!clarifResponse.ok) {
            throw new Error('Failed to generate clarification questions');
          }

          const clarificationData = await clarifResponse.json();
          console.log('Clarification data received:', clarificationData);

          if (clarificationData.requires_clarification && clarificationData.questions.length > 0) {
            setClarificationQuestions(clarificationData.questions);
            setNeedsClarification(true);
            setAnalyzed(true);
            setAnalyzing(false);
            return;
          }
        } catch (err) {
          console.error('Error generating clarification questions:', err);
          // Fall through to normal analysis population
        }
      }

      // Step 3: Populate form with analysis results (if no clarification needed)
      setFormData({
        ...formData,
        intent_type: analysis.intent_type as IntentType,
        pico_population: analysis.pico.population || formData.pico_population,
        pico_intervention: analysis.pico.intervention || formData.pico_intervention,
        pico_comparator: analysis.pico.comparator || formData.pico_comparator,
        pico_outcome: analysis.pico.outcome || formData.pico_outcome,
      });

      // Set key concepts if available
      if (analysis.key_concepts && analysis.key_concepts.length > 0) {
        console.log('Setting key concepts:', analysis.key_concepts);
        setKeyConcepts(analysis.key_concepts.join(', '));
      }

      // Auto-enable PICO and Key Concepts sections
      const hasPico = !!(analysis.pico.population || analysis.pico.intervention || 
                        analysis.pico.comparator || analysis.pico.outcome);
      if (hasPico) {
        console.log('Enabling PICO section');
        setUsePico(true);
      }

      if (analysis.key_concepts && analysis.key_concepts.length > 0) {
        console.log('Enabling Key Concepts section');
        setUseKeyConcepts(true);
      }

      setAnalyzed(true);
      setNeedsClarification(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to analyze query';
      console.error('Analysis error:', message, err);
      setError(message);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleClarificationAnswers = async (answers: string[]) => {
    if (!lastAnalysis) {
      setError('Internal error: analysis data missing');
      return;
    }

    try {
      console.log('User provided clarification answers:', answers);
      
      // In a full implementation, clarification answers would be passed to Module 2 (Query Refinement)
      // For now, we use the analysis results and proceed to form population

      // Update form with the analysis data but acknowledge user's clarification
      setFormData({
        ...formData,
        intent_type: lastAnalysis.intent_type as IntentType,
        pico_population: lastAnalysis.pico.population || formData.pico_population,
        pico_intervention: lastAnalysis.pico.intervention || formData.pico_intervention,
        pico_comparator: lastAnalysis.pico.comparator || formData.pico_comparator,
        pico_outcome: lastAnalysis.pico.outcome || formData.pico_outcome,
      });

      if (lastAnalysis.key_concepts && lastAnalysis.key_concepts.length > 0) {
        setKeyConcepts(lastAnalysis.key_concepts.join(', '));
        setUseKeyConcepts(true);
      }

      const hasPico = !!(lastAnalysis.pico.population || lastAnalysis.pico.intervention || 
                        lastAnalysis.pico.comparator || lastAnalysis.pico.outcome);
      if (hasPico) {
        setUsePico(true);
      }

      // Close clarification panel and show form
      setNeedsClarification(false);
      setAnalyzed(true);
      console.log('Clarification processed, form updated');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to process clarification';
      console.error('Clarification error:', message, err);
      setError(message);
    }
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (!formData.name.trim()) {
      setError('Mission name is required');
      return;
    }
    if (!formData.query.trim()) {
      setError('Research question is required');
      return;
    }

    setLoading(true);
    try {
      const submitData: MissionFormData = {
        ...formData,
      };

      // Add PICO if provided
      if (usePico && (formData.pico_population || formData.pico_intervention || formData.pico_comparator || formData.pico_outcome)) {
        submitData.pico_population = formData.pico_population;
        submitData.pico_intervention = formData.pico_intervention;
        submitData.pico_comparator = formData.pico_comparator;
        submitData.pico_outcome = formData.pico_outcome;
      }

      // Add key concepts if provided
      if (useKeyConcepts && keyConcepts.trim()) {
        submitData.key_concepts = keyConcepts
          .split(',')
          .map((c) => c.trim())
          .filter((c) => c.length > 0);
      }

      await onSubmit(submitData);
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create mission');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  // If clarification is needed, show clarification panel instead of form
  if (needsClarification && clarificationQuestions.length > 0) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="sticky top-0 flex items-center justify-between p-6 border-b border-neutral-200 bg-white">
            <h2 className="text-2xl font-bold text-neutral-900">Clarify Your Research Question</h2>
            <button
              onClick={handleClose}
              className="text-neutral-500 hover:text-neutral-700 transition-colors"
            >
              <X size={24} />
            </button>
          </div>

          {/* Clarification Content */}
          <div className="p-6">
            <ClarificationPanel
              query={formData.query}
              questions={clarificationQuestions}
              onAnswersSubmit={handleClarificationAnswers}
              error={error}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 flex items-center justify-between p-6 border-b border-neutral-200 bg-white">
          <h2 className="text-2xl font-bold text-neutral-900">Create New Mission</h2>
          <button
            onClick={handleClose}
            className="text-neutral-500 hover:text-neutral-700 transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Mission Name */}
          <div>
            <label className="block text-sm font-medium text-neutral-900 mb-2">
              Mission Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="e.g., Long COVID Effects on Cardiovascular System"
              className="w-full px-4 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          {/* Research Question */}
          <div>
            <label className="block text-sm font-medium text-neutral-900 mb-2">
              Research Question *
            </label>
            <textarea
              value={formData.query}
              onChange={(e) => setFormData({ ...formData, query: e.target.value })}
              placeholder="e.g., What are the long-term effects of COVID-19 infection on patient outcomes, particularly in organ systems beyond the respiratory tract?"
              rows={4}
              className="w-full px-4 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            {formData.query.trim() && (
              <button
                type="button"
                onClick={handleAnalyzeQuery}
                disabled={analyzing}
                className="mt-3 w-full px-4 py-2 rounded-lg border border-primary-300 bg-primary-50 text-primary-700 font-medium hover:bg-primary-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {analyzing ? (
                  <>
                    <Loader size={16} className="animate-spin" />
                    Analyzing Query...
                  </>
                ) : analyzed ? (
                  <>
                    <CheckCircle size={16} />
                    Analysis Complete - Review Below
                  </>
                ) : (
                  <>
                    <Zap size={16} />
                    Auto-Analyze with AI
                  </>
                )}
              </button>
            )}
          </div>

          {/* Intent Type */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <label className="block text-sm font-medium text-neutral-900">
                Research Intent Type
              </label>
              {analyzed && (
                <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                  Auto-selected from analysis
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              {INTENT_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setFormData({ ...formData, intent_type: type })}
                  className={`p-3 rounded-lg border-2 transition-all text-left ${
                    formData.intent_type === type
                      ? 'border-primary-500 bg-primary-50 ring-2 ring-primary-500 ring-offset-0'
                      : 'border-neutral-300 hover:border-primary-300'
                  }`}
                >
                  <div className="font-medium text-neutral-900">{type}</div>
                  <div className="text-sm text-neutral-600">
                    {type === 'Causal' && 'Establish cause-effect relationships'}
                    {type === 'Comparative' && 'Compare different approaches'}
                    {type === 'Exploratory' && 'Discover patterns and insights'}
                    {type === 'Descriptive' && 'Characterize phenomena'}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* PICO Framework (Optional) */}
          <div className="border-t border-neutral-200 pt-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={usePico}
                onChange={(e) => setUsePico(e.target.checked)}
                className="w-4 h-4 rounded border-neutral-300"
              />
              <span className="font-medium text-neutral-900">Add PICO Framework (optional)</span>
              {analyzed && usePico && (
                <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                  Auto-filled from analysis
                </span>
              )}
            </label>

            {usePico && (
              <div className="mt-4 space-y-4 p-4 bg-neutral-50 rounded-lg">
                <input
                  type="text"
                  placeholder="Population: Who is the target population?"
                  value={formData.pico_population || ''}
                  onChange={(e) => setFormData({ ...formData, pico_population: e.target.value })}
                  className="w-full px-4 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <input
                  type="text"
                  placeholder="Intervention: What intervention or exposure?"
                  value={formData.pico_intervention || ''}
                  onChange={(e) => setFormData({ ...formData, pico_intervention: e.target.value })}
                  className="w-full px-4 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <input
                  type="text"
                  placeholder="Comparator: What is the comparison?"
                  value={formData.pico_comparator || ''}
                  onChange={(e) => setFormData({ ...formData, pico_comparator: e.target.value })}
                  className="w-full px-4 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <input
                  type="text"
                  placeholder="Outcome: What outcomes are measured?"
                  value={formData.pico_outcome || ''}
                  onChange={(e) => setFormData({ ...formData, pico_outcome: e.target.value })}
                  className="w-full px-4 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            )}
          </div>

          {/* Key Concepts (Optional) */}
          <div className="border-t border-neutral-200 pt-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={useKeyConcepts}
                onChange={(e) => setUseKeyConcepts(e.target.checked)}
                className="w-4 h-4 rounded border-neutral-300"
              />
              <span className="font-medium text-neutral-900">Add Key Concepts (optional)</span>
              {analyzed && useKeyConcepts && (
                <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                  Auto-filled from analysis
                </span>
              )}
            </label>

            {useKeyConcepts && (
              <div className="mt-4 p-4 bg-neutral-50 rounded-lg">
                <textarea
                  placeholder="Enter concepts separated by commas. e.g., Long COVID, organ damage, cardiovascular"
                  value={keyConcepts}
                  onChange={(e) => setKeyConcepts(e.target.value)}
                  rows={3}
                  className="w-full px-4 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            )}
          </div>

          {/* Error Message */}
          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
              <div className="flex-1">
                <p className="text-sm font-medium text-red-900">{error}</p>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-3 pt-4 border-t border-neutral-200">
            <button
              type="button"
              onClick={handleClose}
              className="flex-1 px-4 py-2 rounded-lg border border-neutral-300 text-neutral-900 font-medium hover:bg-neutral-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 rounded-lg bg-primary-500 text-white font-medium hover:bg-primary-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading && <Loader size={16} className="animate-spin" />}
              {loading ? 'Creating...' : 'Create Mission'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
