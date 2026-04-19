import React from "react";

/**
 * CompareModeResults - Full comparison view with 2x2 grid of pipeline answers
 * Shows: Grid of answers, Winner Analysis, Detailed Metrics Panel
 */
export const CompareModeResults = ({ result, askLoading }) => {
  if (askLoading) {
    return (
      <div className="compare-mode-container loading">
        <div className="spinner"></div>
        <p>Comparing all pipelines...</p>
      </div>
    );
  }

  if (!result || !result.retrieval_comparison) {
    return null;
  }

  const { retrieval_comparison, best_pipeline, metrics } = result;
  const bestData = retrieval_comparison[0]; // First one is the winner (sorted by final score)

  // ═══════════════════════════════════════════════════════════
  // Winner Analysis Section
  // ═══════════════════════════════════════════════════════════
  const WinnerAnalysis = () => {
    if (!bestData) return null;

    const bestScores = bestData.scores || {};
    const bestLatency = bestData.retrieval_time_sec
      ? bestData.retrieval_time_sec * 1000
      : metrics?.timings_ms?.total_ms || 0;

    // Compare with runners-up
    const runner2 = retrieval_comparison[1];
    const runner2Scores = runner2?.scores || {};

    const scoreRecommendations = [];

    // Accuracy vs Speed trade-off
    if (bestScores.quality > 7) {
      scoreRecommendations.push(
        "Excellent quality scores. Recommended for accuracy-critical applications.",
      );
    }

    if (bestLatency < 500) {
      scoreRecommendations.push(
        "Very fast retrieval and response. Good for real-time use cases.",
      );
    } else if (bestLatency > 2000) {
      scoreRecommendations.push(
        "Slower but more thorough analysis. Use when latency is less critical.",
      );
    }

    // Uniqueness comparison
    const uniqueDocCount = (bestData.sources || []).length;
    const runner2UniqueDocs = (runner2?.sources || []).length;
    const docDiff = uniqueDocCount - runner2UniqueDocs;

    if (Math.abs(docDiff) > 2) {
      if (docDiff > 0) {
        scoreRecommendations.push(
          `Retrieved ${docDiff} more documents than the runner-up (${runner2?.pipeline || "second best"}). More comprehensive retrieval.`,
        );
      } else {
        scoreRecommendations.push(
          `Retrieved fewer documents than runner-up but with higher quality marks.`,
        );
      }
    }

    return (
      <div className="winner-analysis">
        <div className="winner-header">
          <h3>Winner: {bestData.pipeline}</h3>
          <div className="winner-score">
            <span className="score-number">
              {bestScores.final?.toFixed(1) || "0"}
            </span>
            <span className="score-label">Final Score</span>
          </div>
        </div>

        {scoreRecommendations.length > 0 && (
          <div className="recommendations">
            <h4>Trade-off Analysis & Recommendations</h4>
            <ul>
              {scoreRecommendations.map((rec, idx) => (
                <li key={idx}>{rec}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  };

  // ═══════════════════════════════════════════════════════════
  // Pipeline Comparison Grid (2x2)
  // ═══════════════════════════════════════════════════════════
  const PipelineGrid = () => {
    // Show first 4 pipelines in a 2x2 grid
    const displayPipelines = retrieval_comparison.slice(0, 4);

    return (
      <div className="compare-grid">
        {displayPipelines.map((pipeline, idx) => {
          const isWinner = idx === 0;
          const scores = pipeline.scores || {};

          return (
            <div
              key={idx}
              className={`compare-card ${isWinner ? "winner" : ""}`}
            >
              <div className="card-header">
                <h4>{pipeline.pipeline}</h4>
                <div className="card-score">
                  {scores.final?.toFixed(1) || "0"}
                </div>
              </div>

              <div className="card-answer">
                <p>{pipeline.answer || "(No answer generated)"}</p>
              </div>

              <div className="card-meta">
                <div className="meta-item">
                  <span className="meta-label">Docs</span>
                  <span className="meta-value">
                    {pipeline.sources?.length || 0}
                  </span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Time</span>
                  <span className="meta-value">
                    {(pipeline.retrieval_time_sec * 1000).toFixed(0)}ms
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="compare-mode-container">
      {/* Winner Analysis Section */}
      <WinnerAnalysis />

      {/* 2x2 Pipeline Comparison Grid */}
      <div className="grid-section">
        <h3>Pipeline Comparison</h3>
        <PipelineGrid />
      </div>

      {/* Detailed Metrics Panel with Tabs moved to side panel */}
    </div>
  );
};
