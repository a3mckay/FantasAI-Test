import os

with open("project_structure.txt", "w") as f:
    for root, dirs, files in os.walk("."):
        level = root.replace(".", "").count(os.sep)
        indent = "  " * level
        f.write(f"{indent}{os.path.basename(root)}/\n")
        subindent = "  " * (level + 1)
        for file in files:
            f.write(f"{subindent}{file}\n")
