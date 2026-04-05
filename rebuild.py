# -*- coding: utf-8 -*-
with open('frontend/src/App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''    if (!user) {
      return (
        <div style={{
          display: 'flex',
          height: '100vh',
          width: '100vw',
          background: "linear-gradient(180deg, rgba(15,15,18,0.75), rgba(15,15,18,0.95))",
          backgroundColor: '#0F0F12',
          color: '#E6E6E6',
          position: 'relative',
          overflow: 'hidden',
          fontFamily: "'Inter', sans-serif"
        }}>
          {/* Animated Background */}
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 0 }}>
            <Silk speed={5} scale={1} color="#8556ae" noiseIntensity={1.5} rotation={0} />
          </div>

          <div style={{
            position: 'relative',
            zIndex: 10,
            display: 'flex',
            flexDirection: 'row',
            width: '100%',
            height: '100%',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 8%',
            boxSizing: 'border-box'
          }}>
            {/* Left Info Panel */}
            <div style={{ 
              background: 'rgba(20, 20, 28, 0.55)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '16px',
              padding: '40px',
              width: '520px',
              display: 'flex',
              flexDirection: 'column',
              boxSizing: 'border-box'
            }}>
              <h1 style={{ 
                fontFamily: "'Space Grotesk', sans-serif",
                fontSize: '56px', 
                fontWeight: 700, 
                lineHeight: 1.1, 
                margin: '0 0 20px 0', 
                color: '#fff',
                letterSpacing: '-0.02em'
              }}>
                Optimize and Benchmark Your RAG Pipelines
              </h1>
              <p style={{ 
                fontSize: '18px', 
                color: '#9CA3AF', 
                lineHeight: 1.5, 
                margin: '0 0 32px 0',
                fontWeight: 400 
              }}>
                Compare retrieval strategies, measure latency, evaluate groundedness, and export performance reports.
              </p>
              <ul style={{ 
                listStyle: 'none', 
                padding: 0, 
                margin: 0, 
                display: 'flex', 
                flexDirection: 'column', 
                gap: '16px' 
              }}>
                {[
                  "Multi-Pipeline Benchmarking",
                  "Latency & Cost Analytics",
                  "Vector + Page Index Retrieval",
                  "Multi-Model Testing",
                  "Export Reports (PDF, CSV, JSON)",
                  "Pipeline Comparison Dashboard"
                ].map((ft, i) => (
                  <li key={i} style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '12px', 
                    fontSize: '15px', 
                    color: '#E6E6E6',
                    fontWeight: 500 
                  }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#FF7A59' }} />
                    {ft}
                  </li>
                ))}
              </ul>
            </div>

            {/* Login Card */}
            <div style={{ 
              background: 'rgba(26, 26, 31, 0.85)',
              backdropFilter: 'blur(10px)',
              WebkitBackdropFilter: 'blur(10px)',
              border: '1px solid #2A2A30',
              borderRadius: '16px',
              padding: '28px',
              width: '360px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              textAlign: 'center',
              boxSizing: 'border-box'
            }}>
              <img
                src="/logo.png"
                alt="RAG Pipeline Logo"
                style={{
                  width: "160px",
                  height: "auto",
                  display: "block",
                  objectFit: "contain",
                  marginBottom: "20px"
                }}
              />
              <p style={{ 
                margin: '0 0 32px 0', 
                color: '#9CA3AF', 
                fontSize: '14px',
                fontWeight: 400
              }}>RAG Pipeline Optimization Lab</p>
              
              <button 
                onClick={signInWithGoogle}
                style={{
                  width: '100%',
                  height: '44px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  background: '#FFFFFF',
                  color: '#000000',
                  border: 'none',
                  borderRadius: '10px',
                  fontSize: '14px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'transform 0.1s, box-shadow 0.1s'
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.transform = 'translateY(-1px)';
                  e.currentTarget.style.boxShadow = '0 4px 20px rgba(255,122,89,0.2)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
                onMouseDown={(e) => e.currentTarget.style.transform = 'translateY(1px)'}
                onMouseUp={(e) => e.currentTarget.style.transform = 'translateY(-1px)'}
              >
                <LogIn size={16} /> Sign in with Google
              </button>

              <p style={{ 
                marginTop: '24px', 
                fontSize: '12px', 
                color: '#6B7280',
                fontWeight: 400
              }}>
                By signing in, you agree to Terms and Privacy Policy
              </p>
              
              <div style={{ 
                marginTop: '24px', 
                display: 'flex', 
                gap: '20px', 
                fontSize: '12px',
                fontWeight: 500
              }}>
                <a href="#" style={{ color: '#9CA3AF', textDecoration: 'none' }}>GitHub</a>
                <a href="#" style={{ color: '#9CA3AF', textDecoration: 'none' }}>Documentation</a>
                <a href="#" style={{ color: '#9CA3AF', textDecoration: 'none' }}>About</a>
              </div>
            </div>
          </div>
          
          <Toaster
            position="top-right"
            toastOptions={{
              style: {
                borderRadius: 12,
                fontFamily: "'Inter', sans-serif",
                fontSize: 13,
                background: "#1A1A1F",
                color: "#fff",
                border: "1px solid #2A2A30"
              }
            }}
          />
        </div>
      );
    }'''

idx1 = text.find('if (!user) {')
idx2 = text.find('  return (\n    <div className={claudeShell', idx1)
if idx2 == -1: idx2 = text.find('  return (\n    <div className="claudeShell', idx1)

if idx1 != -1 and idx2 != -1:
    new_text = text[:idx1] + replacement + '\n\n' + text[idx2:]
    with open('frontend/src/App.jsx', 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_text)
    print("Restored JSON UI formatting WITH logo successfully!")
else:
    print(f"Fallback ranges not found. idx1: {idx1}, idx2: {idx2}")
