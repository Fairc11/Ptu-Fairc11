from __future__ import annotations

import ast
from pathlib import Path


def test_js_api_does_not_spawn_powershell_for_get_clipboard():
    path = Path("backend/app/js_api.py")
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "get_clipboard":
            source = ast.get_source_segment(text, node) or ""
            assert "powershell" not in source.lower()
            assert "Get-Clipboard -Raw" not in source
            return

    raise AssertionError("get_clipboard not found")
