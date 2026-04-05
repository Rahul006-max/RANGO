import sys
with open('frontend/src/App.jsx', 'r', encoding='utf-8') as f:
    code = f.read()
    
start_str = '{/* Fast/Compare Mode Analysis — show all analytics in side panel */}'
end_str = "{/* This Chat's Ranking"

start_idx = code.find(start_str)
end_idx = code.find(end_str, start_idx)

if start_idx != -1 and end_idx != -1:
    new_str = """{/* Fast/Compare Mode Analysis — show all analytics in side panel */}
            {(mode === "fast" || mode === "compare") &&
              askRes && (
                <div style={{ marginTop: 16 }}>
                  {mode === "compare" ? (
                    <DetailedMetricsPanel
                      result={askRes}
                      retrieval_comparison={askRes.retrieval_comparison}
                    />
                  ) : (
                    <div style={{ padding: "0 10px" }}>
                      <ResultsDashboard />
                    </div>
                  )}
                </div>
              )}

            """
    code = code[:start_idx] + new_str + code[end_idx:]
    with open('frontend/src/App.jsx', 'w', encoding='utf-8') as fw:
        fw.write(code)
    print('SUCCESS')
else:
    print('FAILED TO FIND')