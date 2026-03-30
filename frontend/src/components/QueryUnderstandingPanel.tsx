import React from 'react';
import { Send, AlertCircle, CheckCircle, Loader } from 'lucide-react';

interface QueryAnalysisResult {
  original_query: string;
  normalized_query: string;
  intent_type: 'Causal' | 'Comparative' | 'Exploratory' | 'Descriptive';
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
  decision: 'PROCEED' | 'PROCEED_WITH_CAUTION' | 'NEED_CLARIFICATION';
  reasoning_steps: string[];
}

interface QueryUnderstandingPanelProps {
  onAnalysisComplete?: (result: QueryAnalysisResult) => void;
}

export const QueryUnderstandingPanel: React.FC<QueryUnderstandingPanelProps> = ({
  onAnalysisComplete,
}) => {
  const [query, setQuery] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<QueryAnalysisResult | null>(null);

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!query.trim()) {
      setError('Please enter a research query');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/query/understand', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim() }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to analyze query');
      }

      const data = await response.json();
      setResult(data);
      onAnalysisComplete?.(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const getDecisionColor = (decision: string) => {
    switch (decision) {
      case 'PROCEED':
        return 'text-green-700 bg-green-50';
      case 'PROCEED_WITH_CAUTION':
        return 'text-amber-700 bg-amber-50';
      case 'NEED_CLARIFICATION':
        return 'text-red-700 bg-red-50';
      default:
        return 'text-neutral-700 bg-neutral-50';
    }
  };

  const getDecisionIcon = (decision: string) => {
    switch (decision) {
      case 'PROCEED':
        return <CheckCircle size={16} />;
      case 'NEED_CLARIFICATION':
        return <AlertCircle size={16} />;
      default:
        return <AlertCircle size={16} />;
    }
  };

  const getIntentTypeColor = (intent: string) => {
    const colors: Record<string, string> = {
      Causal: 'bg-blue-100 text-blue-700',
      Comparative: 'bg-purple-100 text-purple-700',
      Exploratory: 'bg-indigo-100 text-indigo-700',
      Descriptive: 'bg-green-100 text-green-700',
    };
    return colors[intent] || 'bg-neutral-100 text-neutral-700';
  };

  return (
    <div className="space-y-6">
      {/* Query Input */}
      <form onSubmit={handleAnalyze} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-neutral-900 mb-2">
            Research Query / Question
          </label>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g., What are the long-term effects of COVID-19 on cardiovascular health in post-infected patients?"
            rows={4}
            className="w-full px-4 py-3 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
          />
          <p className="text-xs text-neutral-500 mt-1">
            Enter your research question for Module 1 analysis (Query Understanding)
          </p>
        </div>

        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
            <AlertCircle size={16} className="text-red-600 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white font-medium py-3 rounded-lg transition-colors flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader size={18} className="animate-spin" />
              Analyzing Query...
            </>
          ) : (
            <>
              <Send size={18} />
              Analyze Query
            </>
          )}
        </button>
      </form>

      {/* Results */}
      {result && (
        <div className="space-y-6 p-6 bg-neutral-50 rounded-lg border border-neutral-200">
          {/* Decision Badge */}
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 mb-3 flex items-center gap-2">
              {getDecisionIcon(result.decision)}
              Analysis Decision
            </h3>
            <div className={`p-4 rounded-lg ${getDecisionColor(result.decision)} flex items-center justify-between`}>
              <div>
                <p className="font-medium">{result.decision.replace(/_/g, ' ')}</p>
              </div>
              {result.confidence_score && (
                <div className="flex items-center gap-2">
                  <div className="text-xs font-semibold text-neutral-600">Confidence:</div>
                  <div className="flex items-center gap-1">
                    <div className="w-24 h-2 bg-white/30 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-current rounded-full"
                        style={{ width: `${(result.confidence_score || 0) * 100}%` }}
                      />
                    </div>
                    <span className="text-sm font-bold w-12">{((result.confidence_score || 0) * 100).toFixed(0)}%</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Intent Type */}
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 mb-3">Research Intent Type</h3>
            <div className={`inline-block px-4 py-2 rounded-lg font-medium ${getIntentTypeColor(result.intent_type)}`}>
              {result.intent_type}
            </div>
          </div>

          {/* Confidence Score Indicator */}
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 mb-3">Analysis Confidence</h3>
            <div className="flex items-center gap-3">
              <div className="flex-1 h-4 bg-neutral-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-red-500 via-yellow-500 to-green-500 rounded-full transition-all"
                  style={{ width: `${(result.confidence_score || 0) * 100}%` }}
                />
              </div>
              <span className="text-lg font-bold text-neutral-700 w-16 text-right">
                {((result.confidence_score || 0) * 100).toFixed(0)}%
              </span>
            </div>
          </div>

          {/* Original Query */}
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 mb-3">Your Query</h3>
            <p className="text-sm text-neutral-700 p-3 bg-white border border-neutral-200 rounded italic">
              {result.original_query}
            </p>
          </div>

          {/* Normalized Query */}
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 mb-3">Normalized Query</h3>
            <p className="text-sm text-neutral-700 p-3 bg-white border border-neutral-200 rounded">
              {result.normalized_query}
            </p>
          </div>

          {/* PICO Framework */}
          {Object.values(result.pico).some((v) => v) && (
            <div>
              <h3 className="text-sm font-semibold text-neutral-900 mb-3">PICO Framework</h3>
              <div className="grid grid-cols-2 gap-3">
                {result.pico.population && (
                  <div className="p-3 bg-white border border-neutral-200 rounded">
                    <p className="text-xs font-semibold text-neutral-500 uppercase mb-1">Population</p>
                    <p className="text-sm text-neutral-700">{result.pico.population}</p>
                  </div>
                )}
                {result.pico.intervention && (
                  <div className="p-3 bg-white border border-neutral-200 rounded">
                    <p className="text-xs font-semibold text-neutral-500 uppercase mb-1">Intervention</p>
                    <p className="text-sm text-neutral-700">{result.pico.intervention}</p>
                  </div>
                )}
                {result.pico.comparator && (
                  <div className="p-3 bg-white border border-neutral-200 rounded">
                    <p className="text-xs font-semibold text-neutral-500 uppercase mb-1">Comparator</p>
                    <p className="text-sm text-neutral-700">{result.pico.comparator}</p>
                  </div>
                )}
                {result.pico.outcome && (
                  <div className="p-3 bg-white border border-neutral-200 rounded">
                    <p className="text-xs font-semibold text-neutral-500 uppercase mb-1">Outcome</p>
                    <p className="text-sm text-neutral-700">{result.pico.outcome}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Key Concepts */}
          {result.key_concepts.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-neutral-900 mb-3">Key Concepts</h3>
              <div className="flex flex-wrap gap-2">
                {result.key_concepts.map((concept, i) => (
                  <span
                    key={i}
                    className="px-3 py-1 bg-white border border-primary-200 text-primary-700 rounded-full text-sm font-medium"
                  >
                    {concept}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Search Queries */}
          {result.search_queries && result.search_queries.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-neutral-900 mb-3">Optimized Search Queries</h3>
              <div className="space-y-2">
                {result.search_queries.map((query, i) => (
                  <div key={i} className="p-3 bg-blue-50 border border-blue-200 rounded">
                    <p className="text-sm text-blue-900 font-mono">{query}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Ambiguity Flags */}
          {result.ambiguity_flags.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-neutral-900 mb-3 flex items-center gap-2">
                <AlertCircle size={16} className="text-amber-600" />
                Ambiguity Flags
              </h3>
              <ul className="space-y-2">
                {result.ambiguity_flags.map((flag, i) => (
                  <li key={i} className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded">
                    <span className="text-amber-600 font-bold mt-0.5">•</span>
                    <span className="text-sm text-amber-800">{flag}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Interpretation Variants */}
          {result.interpretation_variants && result.interpretation_variants.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-neutral-900 mb-3">Alternative Interpretations</h3>
              <ul className="space-y-2">
                {result.interpretation_variants.map((variant, i) => (
                  <li key={i} className="flex items-start gap-2 p-3 bg-indigo-50 border border-indigo-200 rounded">
                    <span className="text-indigo-600 font-bold mt-0.5">{i + 1}.</span>
                    <span className="text-sm text-indigo-800">{variant}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggested Refinements */}
          {result.suggested_refinements && result.suggested_refinements.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-neutral-900 mb-3">Suggested Refinements</h3>
              <ul className="space-y-2">
                {result.suggested_refinements.map((refinement, i) => (
                  <li key={i} className="flex items-start gap-2 p-3 bg-green-50 border border-green-200 rounded">
                    <span className="text-green-600 font-bold mt-0.5">→</span>
                    <span className="text-sm text-green-800">{refinement}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Reasoning Steps */}
          {result.reasoning_steps && result.reasoning_steps.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-neutral-900 mb-3">Analysis Reasoning</h3>
              <div className="space-y-2">
                {result.reasoning_steps.map((step, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 bg-white border border-neutral-200 rounded">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-xs font-bold">
                      {i + 1}
                    </div>
                    <p className="text-sm text-neutral-700 pt-0.5">{step}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
