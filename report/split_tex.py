import re
import os

with open("report.tex", "r", encoding="utf-8") as f:
    content = f.read()

# Find the start of document
doc_match = re.search(r'\\begin\{document\}.*?\\tableofcontents.*?\\newpage', content, re.DOTALL)
preamble_end = doc_match.end()

preamble = content[:preamble_end]
body = content[preamble_end:]

# Split the body by \section
sections_split = re.split(r'(?=\\section\{)', body)

os.makedirs("sections", exist_ok=True)

new_body = ""
chap_idx = 1

for sec in sections_split:
    sec = sec.strip()
    if not sec:
        continue
    if sec == "\\end{document}":
        new_body += "\n\\end{document}\n"
        continue
        
    if sec.startswith("\\section"):
        # write to file
        filename = f"sections/chap{chap_idx}.tex"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(sec + "\n")
        
        new_body += f"\n\\newpage\n\\input{{{filename}}}\n"
        chap_idx += 1
    else:
        # Just in case there is text before the first section
        new_body += sec + "\n"

# Replace original file
with open("report.tex", "w", encoding="utf-8") as f:
    f.write(preamble + "\n" + new_body)
