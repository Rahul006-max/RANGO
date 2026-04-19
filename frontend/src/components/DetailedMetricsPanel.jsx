import React, { useState } from "react";

/**
 * DetailedMetricsPanel - Tabbed metrics display for Compare Mode
 * Shows: Performance Breakdown, Quality Scores, Parameter Details, Source Comparison, Cost Analysis
 */
export const DetailedMetricsPanel = ({ result, retrieval_comparison }) => {
  const [activeTab, setActiveTab] = useState("performance");

  if (!result || !retrieval_comparison || retrieval_comparison.length === 0) {
    return null;
  }

  const metrics = result.metrics || {};
  const timings = metrics.timings_ms || {};

  // ═══════════════════════════════════════════════════════════
  // Tab 1: Performance Breakdown (Latency by Stage)
  // ═══════════════════════════════════════════════════════════
  const PerformanceBreakdown = () => {
    const latencies = metrics.pipeline_latencies || [];

    if (latencies.length === 0) {
      return (
        <div className="performance-breakdown">
          No detailed pipeline latencies available.
        </div>
      );
    }

    return (
      <div className="performance-breakdown multi-pipeline">
        <h4>Latency Comparison</h4>
        <div className="pipeline-latencies-list">
          {latencies.map((p, idx) => {
            const stages = [
              { name: "Retrieval", ms: p.retrieval_ms || 0 },
              { name: "Context Build", ms: p.context_build_ms || 0 },
              { name: "Scoring", ms: p.scoring_ms || 0 },
              { name: "LLM", ms: timings?.llm_ms || 0 },
            ].filter((s) => s.ms > 0);

            const maxMs = Math.max(...latencies.map((x) => x.total_ms || 1));
            const percentage = ((p.total_ms || 0) / maxMs) * 100;

            return (
              <div
                key={idx}
                className="pipeline-latency-card"
                style={{
                  marginBottom: "15px",
                  padding: "10px",
                  border: "1px solid var(--c-border)",
                  borderRadius: "6px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginBottom: "5px",
                  }}
                >
                  <strong>{p.pipeline}</strong>
                  <span>{(p.total_ms || 0).toFixed(0)} ms</span>
                </div>
                <div
                  className="stage-bar-container"
                  style={{
                    height: "8px",
                    width: "100%",
                    backgroundColor: "var(--c-bg-mute)",
                    borderRadius: "4px",
                    overflow: "hidden",
                    display: "flex",
                  }}
                >
                  {stages.map((st, i) => (
                    <div
                      key={i}
                      title={`${st.name}: ${st.ms.toFixed(1)}ms`}
                      style={{
                        height: "100%",
                        width: `${(st.ms / (p.total_ms || 1)) * 100}%`,
                        backgroundColor:
                          i === 0
                            ? "var(--c-text)"
                            : i === 1
                              ? "var(--c-text-2)"
                              : i === 2
                                ? "var(--c-muted)"
                                : "var(--c-border)",
                      }}
                    />
                  ))}
                </div>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "10px",
                    fontSize: "0.8em",
                    marginTop: "5px",
                    color: "var(--c-text-muted)",
                  }}
                >
                  {stages.map((st, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                      }}
                    >
                      <div
                        style={{
                          width: "8px",
                          height: "8px",
                          borderRadius: "50%",
                          backgroundColor:
                            i === 0
                              ? "var(--c-text)"
                              : i === 1
                                ? "var(--c-text-2)"
                                : i === 2
                                  ? "var(--c-muted)"
                                  : "var(--c-border)",
                        }}
                      ></div>
                      <span>
                        {st.name}: {st.ms.toFixed(0)}ms
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // ═══════════════════════════════════════════════════════════
  // Tab 2: Quality Scores (New)
  // ═══════════════════════════════════════════════════════════
  const QualityScores = () => {
    return (
      <div className="quality-scores multi-pipeline">
        <h4>Quality Scores Comparison</h4>
        <div
          className="pipeline-quality-list"
          style={{ display: "grid", gap: "15px" }}
        >
          {retrieval_comparison.map((p, idx) => {
            const scores = p.scores || {};
            return (
              <div
                key={idx}
                className="pipeline-quality-card"
                style={{
                  padding: "12px",
                  border: "1px solid var(--c-border)",
                  borderRadius: "6px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginBottom: "8px",
                  }}
                >
                  <strong>{p.pipeline}</strong>
                  <span
                    style={{
                      fontWeight: "bold",
                      color: getScoreColor(scores.final || 0),
                    }}
                  >
                    Final: {(scores.final || 0).toFixed(1)}
                  </span>
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: "8px",
                    fontSize: "0.9em",
                  }}
                >
                  <div>Relevance: {(scores.relevance || 0).toFixed(1)}</div>
                  <div>
                    Groundedness: {(scores.groundedness || 0).toFixed(1)}
                  </div>
                  <div>Efficiency: {(scores.efficiency || 0).toFixed(1)}</div>
                  <div>Quality: {(scores.quality || 0).toFixed(1)}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // ═══════════════════════════════════════════════════════════
  // Tab 3: Parameter Details
  // ═══════════════════════════════════════════════════════════
  const ParameterDetails = () => {
    return (
      <div className="parameter-details">
        <h4>Retrieval Parameters & System Metrics</h4>
        <div className="table-responsive">
          <table className="semantic-parameter-table">
            <thead>
              <tr>
                <th>Pipeline Configuration</th>
                <th>Relevance / 10</th>
                <th>Token Usage</th>
                <th>Chunks</th>
                <th>Overlap</th>
                <th>Top K</th>
                <th>Search Algo</th>
              </tr>
            </thead>
            <tbody>
              {retrieval_comparison.map((p, idx) => (
                <tr key={idx}>
                  <td className="pipeline-name-cell" title={p.pipeline}>
                    {p.pipeline}
                  </td>
                  <td>
                    <span className="score-badge">
                      {(p.scores?.relevance || 0).toFixed(2)}
                    </span>
                  </td>
                  <td
                    title={
                      p.tokens?.total_tokens
                        ? "Total tokens consumed"
                        : "Token count not available"
                    }
                  >
                    {p.tokens?.total_tokens ? (
                      p.tokens.total_tokens.toLocaleString()
                    ) : (
                      <span className="value-badge na-badge">N/A</span>
                    )}
                  </td>
                  <td title="Chunk size for document splitting">
                    <span
                      className={p.chunk_size ? "" : "value-badge auto-badge"}
                    >
                      {p.chunk_size || "Auto"}
                    </span>
                  </td>
                  <td title="Overlap between chunks for context">
                    <span className={p.overlap ? "" : "value-badge auto-badge"}>
                      {p.overlap || "Auto"}
                    </span>
                  </td>
                  <td title="Number of top results retrieved">
                    <span
                      className={p.top_k ? "" : "value-badge default-badge"}
                    >
                      {p.top_k || "Default"}
                    </span>
                  </td>
                  <td
                    title={`Search algorithm: ${p.search_type || "Similarity search (default)"}`}
                  >
                    <span
                      className={
                        p.search_type ? "" : "value-badge default-badge"
                      }
                    >
                      {p.search_type || "Similarity"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div
          style={{
            marginTop: "12px",
            padding: "8px 12px",
            fontSize: "11px",
            color: "var(--c-muted)",
            backgroundColor: "var(--c-secondary-bg)",
            borderRadius: "6px",
            borderLeft: "3px solid var(--c-accent)",
          }}
        >
          <div
            style={{
              fontWeight: 600,
              marginBottom: "6px",
              color: "var(--c-text)",
            }}
          >
            Legend:
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "8px",
            }}
          >
            <div>
              ⚠ <strong>N/A</strong> = Data not available for this pipeline
            </div>
            <div>
              ⚙ <strong>Auto</strong> = Automatically determined setting
            </div>
            <div>
              ◆ <strong>Default</strong> = System default value used
            </div>
          </div>
        </div>
      </div>
    );
  };

  // ═══════════════════════════════════════════════════════════
  // Tab 4: Source/Evidence Comparison
  // ═══════════════════════════════════════════════════════════
  const SourceComparison = () => {
    // Build a set of all unique documents retrieved
    const allDocs = new Map(); // docId -> { doc, pipelines: Set([pipeline names]) }

    retrieval_comparison.forEach((pipeline) => {
      (pipeline.sources || []).forEach((source) => {
        const docId =
          source.doc_id || source.metadata?.doc_id || source.page_content;
        if (!allDocs.has(docId)) {
          allDocs.set(docId, { doc: source, pipelines: new Set() });
        }
        allDocs.get(docId).pipelines.add(pipeline.pipeline);
      });
    });

    // Group docs into shared vs. unique
    const uniqueDocs = {};
    const sharedDocs = [];

    retrieval_comparison.forEach((pipeline) => {
      uniqueDocs[pipeline.pipeline] = [];
    });

    allDocs.forEach(({ doc, pipelines }) => {
      if (pipelines.size === 1) {
        const pipelineName = Array.from(pipelines)[0];
        uniqueDocs[pipelineName].push(doc);
      } else {
        sharedDocs.push({ doc, pipelines: Array.from(pipelines) });
      }
    });

    return (
      <div className="source-comparison">
        <h4>Document Retrieval Comparison</h4>

        {/* Shared Documents */}
        {sharedDocs.length > 0 && (
          <div className="source-section">
            <h5>Shared Documents ({sharedDocs.length})</h5>
            <div className="source-list">
              {sharedDocs.map((item, idx) => (
                <div key={idx} className="source-item shared">
                  <div className="source-title">
                    {item.doc.metadata?.title || "Document"}
                  </div>
                  {item.doc.page_content && (
                    <div
                      className="source-chunk"
                      style={{
                        fontSize: "1em",
                        color: "var(--c-text-muted)",
                        marginTop: "8px",
                        maxHeight: "150px",
                        overflowY: "auto",
                        padding: "8px",
                        backgroundColor: "var(--c-bg)",
                        border: "1px solid var(--c-border)",
                        borderRadius: "4px",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {item.doc.page_content}
                    </div>
                  )}
                  <div className="source-pipelines">
                    {item.pipelines.map((p, pidx) => (
                      <span key={pidx} className="pipeline-tag">
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Unique Documents per Pipeline */}
        {Object.entries(uniqueDocs).map(([pipelineName, docs]) => {
          if (docs.length === 0) return null;
          return (
            <div key={pipelineName} className="source-section">
              <h5>
                Unique to {pipelineName} ({docs.length})
              </h5>
              <div className="source-list">
                {docs.map((doc, idx) => (
                  <div key={idx} className="source-item unique">
                    <div className="source-title">
                      {doc.metadata?.title || "Document"}
                    </div>
                    {doc.page_content && (
                      <div
                        className="source-chunk"
                        style={{
                          fontSize: "1em",
                          color: "var(--c-text-muted)",
                          marginTop: "8px",
                          maxHeight: "150px",
                          overflowY: "auto",
                          padding: "8px",
                          backgroundColor: "var(--c-bg)",
                          border: "1px solid var(--c-border)",
                          borderRadius: "4px",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {doc.page_content}
                      </div>
                    )}
                    <div className="source-unique-badge">Unique</div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // ═══════════════════════════════════════════════════════════
  // Tab 5: Cost Analysis
  // ═══════════════════════════════════════════════════════════
  const CostAnalysis = () => {
    const tokens = metrics.tokens || {};

    return (
      <div className="cost-analysis">
        <h4>Cost Analysis</h4>

        <div className="cost-summary">
          <div className="cost-item">
            <span className="cost-label">Total Cost</span>
            <span className="cost-value">
              ${metrics.cost_usd?.toFixed(4) || "0.0000"}
            </span>
          </div>
          <div className="cost-item">
            <span className="cost-label">Total Tokens</span>
            <span className="cost-value">{tokens.total_tokens || 0}</span>
          </div>
          <div className="cost-item">
            <span className="cost-label">Cache Hit</span>
            <span className="cost-value">
              {metrics.cache_hit ? "Yes" : "No"}
            </span>
          </div>
          <div className="cost-item">
            <span className="cost-label">Model</span>
            <span className="cost-value">{tokens.model || "Unknown"}</span>
          </div>
        </div>

        <div className="token-breakdown">
          <h5>Token Usage</h5>
          <div className="token-item">
            <span className="token-label">Input Tokens</span>
            <span className="token-value">{tokens.prompt_tokens || 0}</span>
          </div>
          <div className="token-item">
            <span className="token-label">Output Tokens</span>
            <span className="token-value">{tokens.completion_tokens || 0}</span>
          </div>
        </div>
      </div>
    );
  };

  // Helper function for score color
  const getScoreColor = (score) => {
    if (score >= 7) return "var(--c-text)"; // green
    if (score >= 5) return "var(--c-text-2)"; // yellow
    return "var(--c-danger)"; // red
  };

  return (
    <div className="detailed-metrics-panel">
      {/* Tab Navigation */}
      <div className="metrics-tabs">
        <button
          className={`tab-button ${activeTab === "performance" ? "active" : ""}`}
          onClick={() => setActiveTab("performance")}
        >
          Performance
        </button>
        <button
          className={`tab-button ${activeTab === "quality" ? "active" : ""}`}
          onClick={() => setActiveTab("quality")}
        >
          Quality
        </button>
        <button
          className={`tab-button ${activeTab === "parameters" ? "active" : ""}`}
          onClick={() => setActiveTab("parameters")}
        >
          Parameters
        </button>
        <button
          className={`tab-button ${activeTab === "sources" ? "active" : ""}`}
          onClick={() => setActiveTab("sources")}
        >
          Sources
        </button>
        <button
          className={`tab-button ${activeTab === "cost" ? "active" : ""}`}
          onClick={() => setActiveTab("cost")}
        >
          Cost
        </button>
      </div>

      {/* Tab Content */}
      <div className="metrics-content">
        {activeTab === "performance" && <PerformanceBreakdown />}
        {activeTab === "quality" && <QualityScores />}
        {activeTab === "parameters" && <ParameterDetails />}
        {activeTab === "sources" && <SourceComparison />}
        {activeTab === "cost" && <CostAnalysis />}
      </div>
    </div>
  );
};
