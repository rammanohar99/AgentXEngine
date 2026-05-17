import os
import re

for root, dirs, files in os.walk("docs"):
    for file in files:
        if file.endswith(".md"):
            filepath = os.path.join(root, file)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            new_content = re.sub(r"last_reviewed: 2025-01-01", "last_reviewed: 2026-05-18", content)
            if content != new_content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
print("done")
