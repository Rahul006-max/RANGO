import sys

with open('frontend/src/App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

import re

# Match the erroneous string
bad_pattern = r'              <div\s+<img\s+src="/logo\.png"'
fixed_text = re.sub(bad_pattern, '              <img\n                src="/logo.png"', text)

with open('frontend/src/App.jsx', 'w', encoding='utf-8', newline='\n') as f:
    f.write(fixed_text)

print("Fixed <div<img")
