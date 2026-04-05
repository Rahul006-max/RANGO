import React from "react";

/**
 * FastModeResults - Compact presentation of fast mode query results
 * Shows: Answer + single pipeline metadata (latency, docs retrieved, pipeline name)
 */
export const FastModeResults = ({ result, askLoading }) => {
  if (askLoading) {
    return (
      <div className="fast-mode-container loading">
        <div className="spinner"></div>
        <p>Finding best answer...</p>
      </div>
    );
  }

  if (!result || !result.final_answer) {
    return null;
  }

  const { best_pipeline, final_answer, metrics, retrieval_comparison } = result;

  // Get the best pipeline's info
  const bestPipelineData =
    retrieval_comparison && retrieval_comparison.length > 0
      ? retrieval_comparison[0]
      : null;

  const latency = metrics?.timings_ms?.total_ms || 0;
  const docsRetrieved = bestPipelineData?.sources?.length || 0;

  return (
    <div className="fast-mode-container">
      {/* Pipeline Badge */}
      <div className="fast-mode-header">
        <div className="pipeline-badge">
          <span className="badge-icon">⚡</span>
          <span className="badge-text">Best Match: {best_pipeline}</span>
        </div>
      </div>

      {/* Answer Section */}
      <div className="fast-mode-answer">
        <p>{final_answer}</p>
      </div>

      {/* Compact Metrics */}
      <div className="fast-mode-metrics">
        <div className="metric-item">
          <span className="metric-label">Pipeline</span>
          <span className="metric-value">{best_pipeline}</span>
        </div>
        <div className="metric-item">
          <span className="metric-label">Latency</span>
          <span className="metric-value">{latency.toFixed(0)}ms</span>
        </div>
        <div className="metric-item">
          <span className="metric-label">Sources</span>
          <span className="metric-value">{docsRetrieved} docs</span>
        </div>
        {metrics?.cost_usd > 0 && (
          <div className="metric-item">
            <span className="metric-label">Cost</span>
            <span className="metric-value">${metrics.cost_usd.toFixed(4)}</span>
          </div>
        )}
      </div>

      {/* Citations */}
      {result.citations && result.citations.length > 0 && (
        <div className="fast-mode-citations">
          <h4>Sources</h4>
          <ul>
            {result.citations.map((citation, idx) => (
              <li key={idx}>
                <strong>{citation.metadata?.title || `Doc ${idx + 1}`}</strong>
                {citation.metadata?.page && (
                  <span className="page-number">p. {citation.metadata.page}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
