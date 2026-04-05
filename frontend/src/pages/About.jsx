/**
 * About Page - Brutalist Design
 * Standalone page with raw, industrial aesthetic
 */

export const About = ({ onBack }) => {
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
        <div style={{ margibottom: "60px", paddingBottom: "40px", borderBottom: "3px solid #fff" }}>
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
            RANGO
          </h1>
          <h2
            style={{
              fontSize: "28px",
              fontWeight: 400,
              margin: "0",
              color: "#b0b0b0",
              letterSpacing: "0.03em",
              textTransform: "uppercase",
            }}
          >
            RAG Pipeline Optimizer
          </h2>
        </div>

        {/* Grid Layout */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "60px",
            marginTop: "60px",
          }}
        >
          {/* Left Column */}
          <div>
            <div style={{ marginBottom: "50px" }}>
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
                ABOUT
              </h3>
              <p
                style={{
                  fontSize: "14px",
                  lineHeight: 1.8,
                  margin: "0",
                  color: "#d0d0d0",
                  fontWeight: 400,
                }}
              >
                RANGO is a comprehensive RAG (Retrieval-Augmented Generation) pipeline optimization framework.
                Benchmark, evaluate, and optimize multiple RAG configurations to find the perfect balance
                between speed, cost, and quality for your use case.
              </p>
            </div>

            <div style={{ marginBottom: "50px" }}>
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
                FEATURES
              </h3>
              <ul
                style={{
                  margin: "0",
                  padding: "0",
                  listStyle: "none",
                  fontSize: "14px",
                  lineHeight: 2,
                  color: "#d0d0d0",
                }}
              >
                <li>• Multi-Pipeline Comparison</li>
                <li>• Performance Metrics Analysis</li>
                <li>• Cost Optimization Tracking</li>
                <li>• Quality Assessment & Scoring</li>
                <li>• Retrieval Strategy Benchmarking</li>
                <li>• Parameter Tuning Analysis</li>
                <li>• Document Source Comparison</li>
                <li>• Latency Breakdown by Stage</li>
              </ul>
            </div>
          </div>

          {/* Right Column */}
          <div>
            <div style={{ marginBottom: "50px" }}>
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
                CAPABILITIES
              </h3>
              <ul
                style={{
                  margin: "0",
                  padding: "0",
                  listStyle: "none",
                  fontSize: "14px",
                  lineHeight: 2,
                  color: "#d0d0d0",
                }}
              >
                <li>• Fast Mode: Quick Best-Match Answers</li>
                <li>• Compare Mode: Side-by-Side Analysis</li>
                <li>• Image Analysis Support</li>
                <li>• Real-Time Chat Interface</li>
                <li>• Batch Evaluation</li>
                <li>• Custom Pipeline Configuration</li>
                <li>• Token Cost Tracking</li>
                <li>• Performance Benchmarking</li>
              </ul>
            </div>

            <div>
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
                TECHNOLOGY
              </h3>
              <p
                style={{
                  fontSize: "14px",
                  lineHeight: 1.8,
                  margin: "0",
                  color: "#d0d0d0",
                  fontWeight: 400,
                }}
              >
                Built with Python (FastAPI, LLM integrations), React (Vite), PostgreSQL with pgvector,
                and modern ML/NLP libraries. Supports multiple LLM providers and retrieval strategies.
              </p>
            </div>
          </div>
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
          }}
        >
          <div>
            <h4
              style={{
                fontSize: "14px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                marginBottom: "15px",
                borderBottom: "1px solid #555",
                paddingBottom: "10px",
              }}
            >
              REPOSITORY
            </h4>
            <a
              href="https://github.com/Rahul006-max/RANGO"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: "#fff",
                textDecoration: "underline",
                fontSize: "13px",
                wordBreak: "break-all",
                fontWeight: 500,
              }}
            >
              github.com/Rahul006-max/RANGO
            </a>
          </div>

          <div>
            <h4
              style={{
                fontSize: "14px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                marginBottom: "15px",
                borderBottom: "1px solid #555",
                paddingBottom: "10px",
              }}
            >
              CONTACT & CONTRIBUTE
            </h4>
            <p
              style={{
                fontSize: "13px",
                margin: "0",
                lineHeight: 1.6,
                color: "#b0b0b0",
              }}
            >
              Contributions welcome. Fork the repository and submit pull requests.
              <br />
              Report issues on GitHub.
            </p>
          </div>
        </div>

        {/* Stats */}
        <div
          style={{
            marginTop: "80px",
            paddingTop: "40px",
            borderTop: "3px solid #fff",
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: "30px",
            textAlign: "center",
          }}
        >
          <div>
            <div
              style={{
                fontSize: "36px",
                fontWeight: 700,
                marginBottom: "8px",
              }}
            >
              4+
            </div>
            <div
              style={{
                fontSize: "12px",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                color: "#808080",
              }}
            >
              Retrieval Methods
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: "36px",
                fontWeight: 700,
                marginBottom: "8px",
              }}
            >
              5+
            </div>
            <div
              style={{
                fontSize: "12px",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                color: "#808080",
              }}
            >
              LLM Providers
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: "36px",
                fontWeight: 700,
                marginBottom: "8px",
              }}
            >
              10+
            </div>
            <div
              style={{
                fontSize: "12px",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                color: "#808080",
              }}
            >
              Metrics Tracked
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: "36px",
                fontWeight: 700,
                marginBottom: "8px",
              }}
            >
              ∞
            </div>
            <div
              style={{
                fontSize: "12px",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                color: "#808080",
              }}
            >
              Optimization Space
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
