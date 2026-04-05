import sys
with open('frontend/src/components/CompareModeResults.jsx', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Remove winner-metrics block
wm_start = code.find('<div className="winner-metrics">')
if wm_start != -1:
    wm_end = code.find('{scoreRecommendations.length > 0 &&', wm_start)
    if wm_end != -1:
        code = code[:wm_start] + code[wm_end:]
        print('REMOVED winner-metrics')
        
# 2. Remove card-scores nested block inside card
while True:
    cs_start = code.find('<div className="card-scores">')
    if cs_start == -1:
        break
    cs_end = code.find('<div className="card-meta">', cs_start)
    if cs_end != -1:
        code = code[:cs_start] + code[cs_end:]
        print('REMOVED card-scores block')
    else:
        break

with open('frontend/src/components/CompareModeResults.jsx', 'w', encoding='utf-8') as f:
    f.write(code)
