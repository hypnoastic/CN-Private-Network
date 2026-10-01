#!/usr/bin/env python3
"""Static repository audit without starting services or changing system settings."""
import ast
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [p for p in ROOT.rglob("*") if p.is_file() and p.name != "network.env" and not any(part in (".git", "__pycache__", "runtime", "collected", "certs", "trusted") for part in p.relative_to(ROOT).parts)]
    python_files = [p for p in files if p.suffix == ".py"]
    shells = [p for p in files if p.suffix == ".sh"]
    documents = [p for p in files if p.suffix == ".md"]
    for path in python_files:
        ast.parse(path.read_text(), filename=str(path))
    for path in shells:
        subprocess.run(["/bin/bash", "-n", str(path)], check=True)
    references = set()
    for path in documents:
        content = path.read_text()
        for block in re.findall(r"```bash\n(.*?)```", content, re.S):
            subprocess.run(["/bin/bash", "-n"], input=block, text=True, check=True)
            subprocess.run(["/bin/zsh", "-n"], input=block, text=True, check=True)
        for relative in re.findall(r"(?:bash|python3|source)\s+(setup\.sh|(?:shared|mac\d_[a-z_]+)/[a-z_]+\.(?:sh|py))", content):
            assert (ROOT / relative).is_file(), f"Missing command target in {path}: {relative}"
            references.add(relative)
        for link in re.findall(r"\]\(([^)]+)\)", content):
            if not link.startswith(("https://", "http://", "#")):
                assert (path.parent / link.split("#", 1)[0]).exists(), f"Broken link: {path}: {link}"
    steps = re.findall(r"^## STEP (\d+)\b", (ROOT / "README.md").read_text(), re.M)
    assert steps == [str(i) for i in range(1, 26)], "README must have ordered Steps 1–25"
    examples = re.findall(r"^MAC\d_IP=(.+)$", (ROOT / "network.env.example").read_text(), re.M)
    for path in files:
        if path.name == "network.env.example":
            continue
        content = path.read_text()
        assert not any(value in content for value in examples), f"Example LAN IP hardcoded outside env: {path}"
    print(f"PASS: {len(python_files)} Python files, {len(shells)} shell files, all documentation shell blocks, {len(references)} command targets, local links, 25 ordered steps, example-IP isolation")


if __name__ == "__main__":
    main()
