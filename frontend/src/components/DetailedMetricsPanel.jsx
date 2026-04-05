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
    const stages = [
      { name: "Embedding", ms: timings.embedding_ms || 0 },
      { name: "Retrieval", ms: timings.retrieval_ms || 0 },
      { name: "Rerank", ms: timings.rerank_ms || 0 },
      { name: "LLM", ms: timings.llm_ms || 0 },
      { name: "Smart Extract", ms: timings.smart_extract_ms || 0 },
    ];

    const totalMs = timings.total_ms || 1;
    const maxMs = Math.max(...stages.map((s) => s.ms));

    return (
      <div className="performance-breakdown">
        <h4>Latency by Stage (Total: {totalMs.toFixed(0)}ms)</h4>
        <div className="stage-list">
          {stages.map((stage, idx) => {
            const percentage = (stage.ms / Math.max(maxMs, 1)) * 100;
            return (
              <div key={idx} className="stage-item">
                <div className="stage-label">
                  <span className="stage-name">{stage.name}</span>
                  <span className="stage-time">{stage.ms.toFixed(1)}ms</span>
                </div>
                <div className="stage-bar-container">
                  <div
                    className="stage-bar"
                    style={{
                      width: `${percentage}%`,
                      backgroundColor: `hsl(${Math.max(0, 120 - (stage.ms / totalMs) * 120)}, 70%, 50%)`,
                    }}
                  ></div>
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
        <h4>Retrieval Parameters</h4>
        <div className="parameter-table">
          <div className="param-header">
            <div className="param-col">Pipeline</div>
            <div className="param-col">Chunk Size</div>
            <div className="param-col">Overlap</div>
            <div className="param-col">Top K</div>
            <div className="param-col">Search Type</div>
          </div>

          {retrieval_comparison.map((pipeline, idx) => (
            <div key={idx} className="param-row">
              <div className="param-col">{pipeline.pipeline}</div>
              <div className="param-col">{pipeline.chunk_size || "–"}</div>
              <div className="param-col">{pipeline.overlap || "–"}</div>
              <div className="param-col">{pipeline.top_k || "–"}</div>
              <div className="param-col">{pipeline.search_type || "–"}</div>
            </div>
          ))}
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
    if (score >= 7) return "#4ade80"; // green
    if (score >= 5) return "#facc15"; // yellow
    return "#f87171"; // red
  };

  return (
    <div className="detailed-metrics-panel">
      {/* Tab Navigation */}
      <div className="metrics-tabs">
        <button
          className={`tab-button ${activeTab === "performance" ? "active" : ""}`}
          onClick={() => setActiveTab("performance")}
        >
          📊 Performance
        </button>

        <button
          className={`tab-button ${activeTab === "parameters" ? "active" : ""}`}
          onClick={() => setActiveTab("parameters")}
        >
          ⚙️ Parameters
        </button>
        <button
          className={`tab-button ${activeTab === "sources" ? "active" : ""}`}
          onClick={() => setActiveTab("sources")}
        >
          📚 Sources
        </button>
        <button
          className={`tab-button ${activeTab === "cost" ? "active" : ""}`}
          onClick={() => setActiveTab("cost")}
        >
          💰 Cost
        </button>
      </div>

      {/* Tab Content */}
      <div className="metrics-content">
        {activeTab === "performance" && <PerformanceBreakdown />}
        {activeTab === "parameters" && <ParameterDetails />}
        {activeTab === "sources" && <SourceComparison />}
        {activeTab === "cost" && <CostAnalysis />}
      </div>
    </div>
  );
};
