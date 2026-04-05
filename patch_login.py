import sys
with open('frontend/src/App.jsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out_lines = []
skip = False
for i, line in enumerate(lines):
    if '<Sparkles size={32}' in line:
        # Step back a bit to remove the div
        out_lines = out_lines[:-7]
        out_lines.append('              <img\n')
        out_lines.append('                src=\"/logo.png\"\n')
        out_lines.append('                alt=\"RAG Pipeline Logo\"\n')
        out_lines.append('                style={{\n')
        out_lines.append('                  width: \"180px\",\n')
        out_lines.append('                  height: \"auto\",\n')
        out_lines.append('                  display: \"block\",\n')
        out_lines.append('                  objectFit: \"contain\",\n')
        out_lines.append('                  marginBottom: \"10px\",\n')
        out_lines.append('                }}\n')
        out_lines.append('              />\n')
        skip = True
        continue
    
    if skip and '>RANGO</h2>' in line.replace(' ', ''):
        skip = False
        continue
        
    if not skip:
        out_lines.append(line)

with open('frontend/src/App.jsx', 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(out_lines)

print('Patched successfully')
