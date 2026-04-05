import sys
with open('frontend/src/components/DetailedMetricsPanel.jsx', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Remove Quality Scores component definition
start_str = '  // ═══════════════════════════════════════════════════════════\n  // Tab 2: Quality Scores'
end_str = '  // ═══════════════════════════════════════════════════════════\n  // Tab 3: Parameter Details'

start_idx = code.find(start_str)
end_idx = code.find(end_str, start_idx)

if start_idx != -1 and end_idx != -1:
    code = code[:start_idx] + code[end_idx:]
    print('REMOVED Tab 2 Definition')

# 2. Remove Tab Button for quality (Wait, let's just regex this out)
import re
code = re.sub(r'<button\s+className={`tab-button \${activeTab === "quality" \? "active" : ""}`}\s+onClick=\{.*\}\s*>\s*🎯 Quality\s*</button>\n', '', code, flags=re.MULTILINE)

# 3. Remove conditional render
code = code.replace('{activeTab === "quality" && <QualityScores />}\n', '')

with open('frontend/src/components/DetailedMetricsPanel.jsx', 'w', encoding='utf-8') as fw:
    fw.write(code)

