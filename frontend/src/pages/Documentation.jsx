/**
 * Documentation Page - Brutalist Design
 * Standalone page with raw, industrial aesthetic
 */

export const Documentation = ({ onBack }) => {
  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        width: "100vw",
        background: "#0a0a0a",
        color: "#f0f0f0",
        fontFamily: "'Courier New', monospace",
        position: "relative",
        overflow: "auto",
      }}
    >
      {/* Back Button */}
      <button
        onClick={onBack}
        style={{
          position: "fixed",
          top: "20px",
          left: "20px",
          zIndex: 1000,
          padding: "10px 20px",
          background: "#1a1a1a",
          border: "2px solid #fff",
          color: "#fff",
          cursor: "pointer",
          fontSize: "14px",
          fontWeight: 700,
          fontFamily: "'Courier New', monospace",
          transition: "all 0.1s",
        }}
        onMouseOver={(e) => {
          e.currentTarget.style.background = "#fff";
          e.currentTarget.style.color = "#000";
        }}
        onMouseOut={(e) => {
          e.currentTarget.style.background = "#1a1a1a";
          e.currentTarget.style.color = "#fff";
        }}
      >
        ← BACK
      </button>

      {/* Main Content */}
      <div
        style={{
          width: "100%",
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "80px 40px 80px 40px",
          boxSizing: "border-box",
        }}
      >
        {/* Header */}
        <div style={{ marginBottom: "60px", paddingBottom: "40px", borderBottom: "3px solid #fff" }}>
          <h1
            style={{
              fontSize: "72px",
              fontWeight: 700,
              margin: "0 0 20px 0",
              letterSpacing: "0.05em",
              textTransform: "uppercase",
              lineHeight: 1.1,
            }}
          >
            DOCUMENTATION
          </h1>
          <h2
            style={{
              fontSize: "18px",
              fontWeight: 400,
              margin: "0",
              color: "#b0b0b0",
              letterSpacing: "0.03em",
              textTransform: "uppercase",
            }}
          >
            RAG Pipeline Optimizer Guide
          </h2>
        </div>

        {/* Table of Contents */}
        <div
          style={{
            marginBottom: "60px",
            padding: "30px",
            border: "1px solid #444",
            background: "#111",
          }}
        >
          <h3
            style={{
              fontSize: "16px",
              fontWeight: 700,
              margin: "0 0 20px 0",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
            }}
          >
            TABLE OF CONTENTS
          </h3>
          <ul
            style={{
              margin: "0",
              padding: "0",
              listStyle: "none",
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "10px",
              fontSize: "13px",
              lineHeight: 2,
            }}
          >
            <li>1. Getting Started</li>
            <li>2. Authentication</li>
            <li>3. Collections</li>
            <li>4. Chat Mode</li>
            <li>5. Fast Mode</li>
            <li>6. Compare Mode</li>
            <li>7. Image Analysis</li>
            <li>8. Configuration</li>
            <li>9. API Reference</li>
            <li>10. Performance Tips</li>
            <li>11. Troubleshooting</li>
            <li>12. FAQ</li>
          </ul>
        </div>

        {/* Content Sections */}
        <div style={{ marginTop: "60px", display: "grid", gridTemplateColumns: "1fr", gap: "60px" }}>
          {/* Getting Started */}
          <section>
            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                margin: "0 0 20px 0",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                borderBottom: "2px solid #fff",
                paddingBottom: "15px",
              }}
            >
              1. GETTING STARTED
            </h3>
            <div style={{ fontSize: "14px", lineHeight: 1.8, color: "#d0d0d0" }}>
              <p style={{ margin: "0 0 15px 0" }}>
                Sign in with your Google account to access RANGO. Once authenticated, you'll see the main dashboard with collections and mode options.
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>First Steps:</strong>
              </p>
              <ul style={{ margin: "0 0 15px 0", paddingLeft: "20px" }}>
                <li>Create a new collection by clicking "New collection"</li>
                <li>Upload documents or PDF files</li>
                <li>Select a retrieval method and search index type</li>
                <li>Begin querying your documents</li>
              </ul>
            </div>
          </section>

          {/* Authentication */}
          <section>
            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                margin: "0 0 20px 0",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                borderBottom: "2px solid #fff",
                paddingBottom: "15px",
              }}
            >
              2. AUTHENTICATION
            </h3>
            <div style={{ fontSize: "14px", lineHeight: 1.8, color: "#d0d0d0" }}>
              <p style={{ margin: "0 0 15px 0" }}>
                RANGO uses OAuth 2.0 with Google Sign-In for authentication. Your session is automatically managed and refreshed.
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                Sessions expire after 60 minutes of inactivity. The system automatically refreshes your token if it's about to expire.
              </p>
            </div>
          </section>

          {/* Chat Mode */}
          <section>
            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                margin: "0 0 20px 0",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                borderBottom: "2px solid #fff",
                paddingBottom: "15px",
              }}
            >
              4. CHAT MODE
            </h3>
            <div style={{ fontSize: "14px", lineHeight: 1.8, color: "#d0d0d0" }}>
              <p style={{ margin: "0 0 15px 0" }}>
                Chat with your documents using natural language. The system retrieves relevant context and generates answers.
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>Features:</strong>
              </p>
              <ul style={{ margin: "0 0 15px 0", paddingLeft: "20px" }}>
                <li>Multi-turn conversations with history</li>
                <li>Automatic context retrieval</li>
                <li>Citation tracking</li>
                <li>File uploads within chat</li>
                <li>Real-time response streaming</li>
              </ul>
            </div>
          </section>

          {/* Fast Mode */}
          <section>
            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                margin: "0 0 20px 0",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                borderBottom: "2px solid #fff",
                paddingBottom: "15px",
              }}
            >
              5. FAST MODE
            </h3>
            <div style={{ fontSize: "14px", lineHeight: 1.8, color: "#d0d0d0" }}>
              <p style={{ margin: "0 0 15px 0" }}>
                Get quick, single-pipeline answers optimized for speed. Fast Mode executes your query across a single best-performing pipeline.
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                Useful for production scenarios where you need consistent, fast responses. Displays answer, latency, sources, and cost metrics.
              </p>
            </div>
          </section>

          {/* Compare Mode */}
          <section>
            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                margin: "0 0 20px 0",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                borderBottom: "2px solid #fff",
                paddingBottom: "15px",
              }}
            >
              6. COMPARE MODE
            </h3>
            <div style={{ fontSize: "14px", lineHeight: 1.8, color: "#d0d0d0" }}>
              <p style={{ margin: "0 0 15px 0" }}>
                Compare side-by-side results from multiple RAG pipelines. See how different retrieval strategies, chunk sizes, and models perform.
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>Compare Mode Shows:</strong>
              </p>
              <ul style={{ margin: "0 0 15px 0", paddingLeft: "20px" }}>
                <li>Winner analysis with trade-off recommendations</li>
                <li>2x2 grid of pipeline results</li>
                <li>Detailed metrics by pipeline</li>
                <li>Performance breakdown by stage</li>
                <li>Parameter comparison table</li>
                <li>Document source analysis</li>
                <li>Cost comparison</li>
              </ul>
            </div>
          </section>

          {/* Image Analysis */}
          <section>
            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                margin: "0 0 20px 0",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                borderBottom: "2px solid #fff",
                paddingBottom: "15px",
              }}
            >
              7. IMAGE ANALYSIS
            </h3>
            <div style={{ fontSize: "14px", lineHeight: 1.8, color: "#d0d0d0" }}>
              <p style={{ margin: "0 0 15px 0" }}>
                Upload images and ask questions about their content. RANGO supports vision models for comprehensive image understanding.
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                Displays confidence scores, extracted descriptions, and detailed analysis of image content.
              </p>
            </div>
          </section>

          {/* Metrics Explanation */}
          <section>
            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                margin: "0 0 20px 0",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                borderBottom: "2px solid #fff",
                paddingBottom: "15px",
              }}
            >
              9. KEY METRICS
            </h3>
            <div style={{ fontSize: "14px", lineHeight: 1.8, color: "#d0d0d0" }}>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>Latency:</strong> Total time from query to answer (includes embedding, retrieval, reranking, LLM, extraction)
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>Quality Score:</strong> LLM-judged measure of answer quality (0-10 scale)
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>Cost:</strong> USD cost for LLM tokens (prompt + completion tokens)
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>Retrieval Score:</strong> Relevance of retrieved documents to query (0-10 scale)
              </p>
              <p style={{ margin: "0" }}>
                <strong>Sources:</strong> Number of documents retrieved and used for context
              </p>
            </div>
          </section>

          {/* Performance Tips */}
          <section>
            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                margin: "0 0 20px 0",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                borderBottom: "2px solid #fff",
                paddingBottom: "15px",
              }}
            >
              10. PERFORMANCE TIPS
            </h3>
            <div style={{ fontSize: "14px", lineHeight: 1.8, color: "#d0d0d0" }}>
              <ul style={{ margin: "0", paddingLeft: "20px" }}>
                <li>Smaller chunk sizes (256-512) for focused answers</li>
                <li>Larger chunk sizes (1024-2048) for context retention</li>
                <li>Use reranking for better relevance at the cost of latency</li>
                <li>Adjust top-k (typically 5-20) based on document quality</li>
                <li>Batch evaluate multiple queries to compare pipelines statistically</li>
                <li>Monitor cost vs quality trade-offs for your use case</li>
              </ul>
            </div>
          </section>

          {/* FAQ */}
          <section>
            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                margin: "0 0 20px 0",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                borderBottom: "2px solid #fff",
                paddingBottom: "15px",
              }}
            >
              12. FAQ
            </h3>
            <div style={{ fontSize: "14px", lineHeight: 1.8, color: "#d0d0d0" }}>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>Q: What file formats are supported?</strong>
                <br />A: PDF, TXT, DOCX, XLSX, JSON, and other text-based formats.
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>Q: How many documents can I upload?</strong>
                <br />A: No hard limit. Performance depends on collection size and retrieval method.
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>Q: Can I export results?</strong>
                <br />A: Yes. Use the Download button to export chat history and metrics as PDF.
              </p>
              <p style={{ margin: "0 0 15px 0" }}>
                <strong>Q: How do I compare two pipelines?</strong>
                <br />A: Use Compare Mode to run the same query across multiple pipelines side-by-side.
              </p>
              <p style={{ margin: "0" }}>
                <strong>Q: What is vector reranking?</strong>
                <br />A: A secondary ranking pass that scores retrieved documents for relevance, improving quality at the cost of latency.
              </p>
            </div>
          </section>
        </div>

        {/* Footer */}
        <div
          style={{
            marginTop: "80px",
            paddingTop: "40px",
            borderTop: "3px solid #fff",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "60px",
            fontSize: "13px",
            color: "#b0b0b0",
          }}
        >
          <div>
            <h4
              style={{
                fontSize: "12px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                marginBottom: "10px",
                borderBottom: "1px solid #555",
                paddingBottom: "8px",
              }}
            >
              NEED HELP?
            </h4>
            <p style={{ margin: "10px 0" }}>Check the GitHub repository issues section for common problems.</p>
            <p style={{ margin: "0" }}>Community support available through discussions.</p>
          </div>

          <div>
            <h4
              style={{
                fontSize: "12px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                marginBottom: "10px",
                borderBottom: "1px solid #555",
                paddingBottom: "8px",
              }}
            >
              RESOURCES
            </h4>
            <p style={{ margin: "10px 0" }}>
              GitHub: <a href="https://github.com/Rahul006-max/RANGO" target="_blank" rel="noopener noreferrer" style={{ color: "#fff", textDecoration: "underline" }}>github.com/Rahul006-max/RANGO</a>
            </p>
            <p style={{ margin: "0" }}>API docs available in repository /docs folder.</p>
          </div>
        </div>
      </div>
    </div>
  );
};
