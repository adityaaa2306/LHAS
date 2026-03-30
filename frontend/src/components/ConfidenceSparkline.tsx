import React from 'react';

interface ConfidenceSparklineProps {
  data: number[]; // 8 health snapshot values (0-100)
}

export const ConfidenceSparkline: React.FC<ConfidenceSparklineProps> = ({ data }) => {
  const getHealthColor = (value: number): string => {
    if (value >= 80) return '#10b981'; // HEALTHY - green
    if (value >= 60) return '#f59e0b'; // WATCH - amber
    if (value >= 40) return '#ef4444'; // DEGRADED - red
    return '#991b1b'; // CRITICAL - dark red
  };

  const dotRadius = 3;
  const spacing = 8;

  return (
    <svg
      width={data.length * spacing + 4}
      height={20}
      viewBox={`0 0 ${data.length * spacing + 4} 20`}
      className="inline-block"
    >
      {data.map((value, index) => (
        <circle
          key={index}
          cx={index * spacing + 4}
          cy={10}
          r={dotRadius}
          fill={getHealthColor(value)}
          opacity={0.8}
        />
      ))}
    </svg>
  );
};
