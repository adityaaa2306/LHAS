import React from 'react';

interface ExpandableTextProps {
  text: string | null | undefined;
  collapsedLines?: number;
  className?: string;
  textClassName?: string;
  buttonClassName?: string;
  expandLabel?: string;
  collapseLabel?: string;
  minCharactersToCollapse?: number;
  stopPropagation?: boolean;
}

export const ExpandableText: React.FC<ExpandableTextProps> = ({
  text,
  collapsedLines = 2,
  className = '',
  textClassName = '',
  buttonClassName = '',
  expandLabel = 'Show more',
  collapseLabel = 'Show less',
  minCharactersToCollapse = 140,
  stopPropagation = false,
}) => {
  const [expanded, setExpanded] = React.useState(false);

  const content = String(text || '').trim();
  if (!content) return null;

  const canCollapse = content.length > minCharactersToCollapse;
  const lineClampClass =
    !expanded && canCollapse
      ? collapsedLines === 1
        ? 'line-clamp-1'
        : collapsedLines === 2
          ? 'line-clamp-2'
          : collapsedLines === 3
            ? 'line-clamp-3'
            : collapsedLines === 4
              ? 'line-clamp-4'
              : 'line-clamp-5'
      : '';

  return (
    <div className={className}>
      <div className={`${textClassName} ${lineClampClass}`.trim()}>{content}</div>
      {canCollapse && (
        <button
          type="button"
          onClick={(event) => {
            if (stopPropagation) event.stopPropagation();
            setExpanded((value) => !value);
          }}
          className={`mt-2 text-xs font-semibold text-blue-700 transition hover:text-blue-900 ${buttonClassName}`.trim()}
        >
          {expanded ? collapseLabel : expandLabel}
        </button>
      )}
    </div>
  );
};
