import React from 'react';
import { ChevronRight, Loader, AlertCircle } from 'lucide-react';

interface UIQuestion {
  question: string;
  options: string[];
}

interface ClarificationPanelProps {
  query: string;
  questions: UIQuestion[];
  onAnswersSubmit: (answers: string[]) => Promise<void>;
  isLoading?: boolean;
  error?: string | null;
}

export const ClarificationPanel: React.FC<ClarificationPanelProps> = ({
  query,
  questions,
  onAnswersSubmit,
  isLoading = false,
  error = null,
}) => {
  const [answers, setAnswers] = React.useState<string[]>(
    questions.map(() => '')
  );
  const [customInputs, setCustomInputs] = React.useState<string[]>(
    questions.map(() => '')
  );
  const [submitting, setSubmitting] = React.useState(false);

  const handleOptionSelect = (questionIndex: number, option: string) => {
    const newAnswers = [...answers];
    newAnswers[questionIndex] = option;
    setAnswers(newAnswers);

    // Clear custom input if they selected a predefined option
    if (option !== 'Other') {
      const newCustom = [...customInputs];
      newCustom[questionIndex] = '';
      setCustomInputs(newCustom);
    }
  };

  const handleCustomInput = (questionIndex: number, value: string) => {
    const newCustom = [...customInputs];
    newCustom[questionIndex] = value;
    setCustomInputs(newCustom);

    // Update answer to the custom input
    const newAnswers = [...answers];
    newAnswers[questionIndex] = value || 'Other';
    setAnswers(newAnswers);
  };

  const handleSubmit = async () => {
    // Validate that all questions are answered
    const allAnswered = answers.every((answer, idx) => {
      if (answer === 'Other') {
        return customInputs[idx].trim().length > 0;
      }
      return answer.length > 0;
    });

    if (!allAnswered) {
      return;
    }

    // Replace "Other" with actual custom input value
    const finalAnswers = answers.map((answer, idx) => {
      if (answer === 'Other') {
        return customInputs[idx];
      }
      return answer;
    });

    setSubmitting(true);
    try {
      await onAnswersSubmit(finalAnswers);
    } finally {
      setSubmitting(false);
    }
  };

  if (!questions || questions.length === 0) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-neutral-200 pb-4">
        <p className="text-sm text-neutral-600">
          Original query:{' '}
          <span className="font-medium text-neutral-900">"{query}"</span>
        </p>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="text-red-600 flex-shrink-0 mt-0.5" size={20} />
          <div>
            <p className="font-medium text-red-900">Error</p>
            <p className="text-sm text-red-700">{error}</p>
          </div>
        </div>
      )}

      {/* Questions */}
      <div className="space-y-6">
        {questions.map((q, qIdx) => (
          <div key={qIdx} className="space-y-3">
            {/* Question Text */}
            <div className="flex items-start gap-2">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary-500 text-white flex items-center justify-center text-xs font-semibold">
                {qIdx + 1}
              </div>
              <h3 className="font-medium text-neutral-900 pt-0.5">{q.question}</h3>
            </div>

            {/* Options - Chips/Buttons */}
            <div className="pl-8 space-y-2">
              {q.options.map((option, oIdx) => {
                const isSelected = answers[qIdx] === option;
                const isOther = option === 'Other';

                return (
                  <div key={oIdx} className="space-y-2">
                    <button
                      onClick={() => handleOptionSelect(qIdx, option)}
                      disabled={isLoading || submitting}
                      className={`w-full text-left px-4 py-3 rounded-lg border-2 transition-all ${
                        isSelected
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-neutral-200 hover:border-primary-300 hover:bg-neutral-50'
                      } ${
                        isLoading || submitting ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${
                            isSelected
                              ? 'border-primary-500 bg-primary-500'
                              : 'border-neutral-300'
                          }`}
                        >
                          {isSelected && (
                            <div className="w-2 h-2 rounded-full bg-white" />
                          )}
                        </div>
                        <span className="font-medium text-neutral-900">
                          {option}
                        </span>
                      </div>
                    </button>

                    {/* Custom Input for "Other" */}
                    {isOther && isSelected && (
                      <div className="pl-7 pt-2">
                        <input
                          type="text"
                          value={customInputs[qIdx]}
                          onChange={(e) =>
                            handleCustomInput(qIdx, e.target.value)
                          }
                          placeholder="Enter your own answer..."
                          disabled={isLoading || submitting}
                          className="w-full px-3 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm"
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3 pt-4 border-t border-neutral-200">
        <button
          onClick={handleSubmit}
          disabled={
            isLoading ||
            submitting ||
            !answers.every((answer, idx) => {
              if (answer === 'Other') {
                return customInputs[idx].trim().length > 0;
              }
              return answer.length > 0;
            })
          }
          className="flex-1 px-4 py-3 rounded-lg bg-primary-500 text-white font-medium hover:bg-primary-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {submitting ? (
            <>
              <Loader size={16} className="animate-spin" />
              Processing...
            </>
          ) : (
            <>
              Continue
              <ChevronRight size={16} />
            </>
          )}
        </button>
      </div>

      {/* Helper Text */}
      <p className="text-xs text-neutral-500 text-center">
        Your answers will help refine the search results
      </p>
    </div>
  );
};

export default ClarificationPanel;
