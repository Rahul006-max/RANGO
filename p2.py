import sys
import re

with open('frontend/src/App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Pattern to find the exact block for the Sparkles and RANGO <h2>.
pattern = r'<div\s+style={{\s*background:\s*["\']rgba\(255,\s*122,\s*89,\s*0\.1\)["\'],\s*padding:\s*["\']16px["\'],\s*borderRadius:\s*["\']50%["\'],\s*marginBottom:\s*["\']20px["\'],?\s*}}\s*>\s*<Sparkles[^>]*>\s*</div>\s*<h2\s+style={{[^}]*}}\s*>\s*RANGO\s*</h2>'

replacement = '''<img
                src="/logo.png"
                alt="RAG Pipeline Logo"
                style={{
                  width: "180px",
                  height: "auto",
                  display: "block",
                  objectFit: "contain",
                  marginBottom: "20px",
                }}
              />'''

new_text, count = re.subn(pattern, replacement, text, count=1)

if count > 0:
    with open('frontend/src/App.jsx', 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_text)
    print("Replaced successfully")
else:
    print("Pattern not found!")
