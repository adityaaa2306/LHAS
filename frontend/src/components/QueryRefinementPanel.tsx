import React from 'react';
import { Loader, ChevronRight, AlertCircle } from 'lucide-react';

interface ClarificationQuestion {
  question: string;
  options: string[];
}

interface ClarificationResponse {
  question: string;
  selected_option: string;
  user_input: string | null;
}

interface QueryRefinementPanelProps {
  query: string;
  onRefinementComplete?: (refinedQuery: string, filters: Record<string, any>) => void;
}

interface RefinementResponse {
  status: 'needs_clarification' | 'final';
  clarification_questions?: ClarificationQuestion[];
  refined_query?: string;
  applied_filters?: Record<string, any>;
}

export const QueryRefinementPanel: React.FC<QueryRefinementPanelProps> = ({
  query,
  onRefinementComplete,
}) => {
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState<'initial' | 'clarification' | 'final'>('initial');
  const [clarificationQuestions, setClarificationQuestions] = React.useState<ClarificationQuestion[]>([]);
  const [answers, setAnswers] = React.useState<ClarificationResponse[]>([]);
  const [currentQuestionIndex, setCurrentQuestionIndex] = React.useState(0);
  const [refinedQuery, setRefinedQuery] = React.useState<string | null>(null);
  const [appliedFilters, setAppliedFilters] = React.useState<Record<string, any> | null>(null);

  const handleStartRefinement = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('http://localhost:8000/api/query/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_query: query }),
      });

      if (!response.ok) {
        throw new Error('Failed to refine query');
      }

      const data: RefinementResponse = await response.json();

      if (data.status === 'needs_clarification' && data.clarification_questions) {
        setClarificationQuestions(data.clarification_questions);
        setStatus('clarification');
        setCurrentQuestionIndex(0);
      } else if (data.status === 'final') {
        setRefinedQuery(data.refined_query || query);
        setAppliedFilters(data.applied_filters || {});
        setStatus('final');
        onRefinementComplete?.(data.refined_query || query, data.applied_filters || {});
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refinement failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectOption = (option: string) => {
    const question = clarificationQuestions[currentQuestionIndex];
    const newAnswer: ClarificationResponse = {
      question: question.question,
      selected_option: option,
      user_input: null,
    };

    const updatedAnswers = [...answers, newAnswer];
    setAnswers(updatedAnswers);

    if (currentQuestionIndex < clarificationQuestions.length - 1) {
      setCurrentQuestionIndex(currentQuestionIndex + 1);
    } else {
      // All questions answered, generate final query
      handleGenerateFinalQuery(updatedAnswers);
    }
  };

  const handleCustomInput = (input: string) => {
    const question = clarificationQuestions[currentQuestionIndex];
    const newAnswer: ClarificationResponse = {
      question: question.question,
      selected_option: 'Other',
      user_input: input,
    };

    const updatedAnswers = [...answers, newAnswer];
    setAnswers(updatedAnswers);

    if (currentQuestionIndex < clarificationQuestions.length - 1) {
      setCurrentQuestionIndex(currentQuestionIndex + 1);
    } else {
      handleGenerateFinalQuery(updatedAnswers);
    }
  };

  const handleGenerateFinalQuery = async (allAnswers: ClarificationResponse[]) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('http://localhost:8000/api/query/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_query: query,
          previous_clarifications: allAnswers,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to generate final query');
      }

      const data: RefinementResponse = await response.json();

      if (data.status === 'final') {
        setRefinedQuery(data.refined_query || query);
        setAppliedFilters(data.applied_filters || {});
        setStatus('final');
        onRefinementComplete?.(data.refined_query || query, data.applied_filters || {});
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate final query');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 p-6 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg border border-indigo-200">
      {/* Status Badge */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-neutral-900">Query Refinement (Module 2)</h3>
        <div className="text-xs font-semibold px-3 py-1 rounded-full bg-indigo-100 text-indigo-700">
          {status === 'initial' && 'Ready'}
          {status === 'clarification' && `Question ${currentQuestionIndex + 1} of ${clarificationQuestions.length}`}
          {status === 'final' && 'Complete'}
        </div>
      </div>

      {/* Original Query Display */}
      <div className="p-3 bg-white border border-indigo-200 rounded-lg">
        <p className="text-xs text-neutral-500 font-semibold mb-1">YOUR QUERY</p>
        <p className="text-sm text-neutral-700 italic">{query}</p>
      </div>

      {/* Initial State */}
      {status === 'initial' && (
        <div className="space-y-4">
          <p className="text-sm text-neutral-600">
            Let's refine your query to make it more specific and optimized for research retrieval. Click the button below to start the refinement process.
          </p>
          <button
            onClick={handleStartRefinement}
            disabled={loading}
            className="w-full px-4 py-3 rounded-lg bg-indigo-600 text-white font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader size={18} className="animate-spin" />
                Analyzing Query...
              </>
            ) : (
              <>
                <ChevronRight size={18} />
                Start Query Refinement
              </>
            )}
          </button>
        </div>
      )}

      {/* Clarification Questions State */}
      {status === 'clarification' && currentQuestionIndex < clarificationQuestions.length && (
        <div className="space-y-4">
          <div>
            <h4 className="font-medium text-neutral-900 mb-4">
              {clarificationQuestions[currentQuestionIndex].question}
            </h4>

            <div className="space-y-2">
              {clarificationQuestions[currentQuestionIndex].options.map((option, idx) => (
                <button
                  key={idx}
                  onClick={() =>
                    option === 'Other'
                      ? setCurrentQuestionIndex(currentQuestionIndex) // Will handle custom input below
                      : handleSelectOption(option)
                  }
                  className={`w-full p-3 rounded-lg border-2 text-left transition-all ${
                    option === 'Other'
                      ? 'border-neutral-300 hover:border-indigo-400'
                      : 'border-neutral-300 hover:border-indigo-400 cursor-pointer'
                  }`}
                >
                  <div className="font-medium text-neutral-900">{option}</div>
                </button>
              ))}
            </div>

            {clarificationQuestions[currentQuestionIndex].options.includes('Other') && (
              <div className="mt-4 pt-4 border-t border-neutral-300">
                <label className="text-xs font-semibold text-neutral-700 mb-2 block">
                  Or enter your own answer:
                </label>
                <input
                  type="text"
                  placeholder="Type your answer..."
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && (e.target as HTMLInputElement).value.trim()) {
                      handleCustomInput((e.target as HTMLInputElement).value);
                      (e.target as HTMLInputElement).value = '';
                    }
                  }}
                  className="w-full px-3 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
                />
              </div>
            )}
          </div>

          {/* Progress Bar */}
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1 bg-neutral-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-600 transition-all"
                style={{ width: `${((currentQuestionIndex + 1) / clarificationQuestions.length) * 100}%` }}
              />
            </div>
            <span className="text-xs text-neutral-600 font-medium">
              {currentQuestionIndex + 1}/{clarificationQuestions.length}
            </span>
          </div>
        </div>
      )}

      {/* Final State */}
      {status === 'final' && refinedQuery && (
        <div className="space-y-4">
          <div className="p-4 bg-white border-l-4 border-green-500 rounded-lg">
            <p className="text-xs text-neutral-500 font-semibold mb-2">REFINED QUERY</p>
            <p className="text-sm text-neutral-900 font-medium">{refinedQuery}</p>
          </div>

          {appliedFilters && Object.keys(appliedFilters).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-neutral-700 mb-2">Applied Refinements:</p>
              <div className="space-y-2">
                {Object.entries(appliedFilters).map(([key, value]) => {
                  if (value === null || value === undefined || Array.isArray(value)) return null;
                  return (
                    <div key={key} className="flex items-start gap-2 text-sm">
                      <span className="text-indigo-600 font-semibold min-w-fit">
                        {typeof value === 'object' ? key : value}:
                      </span>
                      <span className="text-neutral-600">
                        {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <p className="text-xs text-green-700 bg-green-50 p-3 rounded-lg">
            ✓ Your query has been refined and optimized for research retrieval!
          </p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
          <AlertCircle size={16} className="text-red-600 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}
    </div>
  );
};
