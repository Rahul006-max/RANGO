import re

def count_divs():
    with open('frontend/src/App.jsx', encoding='utf-8') as f:
        text = f.read()

    # Isolate ChatThreadView
    start_str = "const ChatThreadView = () => ("
    end_str = "const PipelineConfigPanel = () => ("
    start_idx = text.find(start_str)
    end_idx = text.find(end_str)
    
    if start_idx == -1 or end_idx == -1:
        print("Could not find start or end bounds.")
        return

    chat_thread_text = text[start_idx:end_idx]
    
    # We can remove all self-closing divs with regex
    # e.g., <div [^>]*? />
    cleaned_text = re.sub(r'<div[^>]*?/>', '', chat_thread_text)
    
    lines = cleaned_text.splitlines()
    count = 0
    with open('balance_report.txt', 'w', encoding='utf-8') as f:
        for i, line in enumerate(lines):
            # count <div that are not self closing
            # Wait, there could be multiline self-closing divs!
            # The regex re.sub worked on the full string, so they are gone.
            opening = len(re.findall(r'<div\b', line))
            closing = len(re.findall(r'</div\b', line))
            count += (opening - closing)
            f.write(f"Line {i}: +{opening} -{closing} | Balance: {count} | {line}\n")
            
    print(f"Net balance at end: {count}")

if __name__ == '__main__':
    count_divs()