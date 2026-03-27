from __future__ import annotations

import ast
from typing import Any, List, Tuple


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text == "":
        return ""
    if text in {"true", "True"}:
        return True
    if text in {"false", "False"}:
        return False
    if text in {"null", "None", "~"}:
        return None
    if text.startswith(("'", '"')) and text.endswith(("'", '"')):
        return ast.literal_eval(text)
    try:
        if text.startswith("0") and text != "0" and not text.startswith("0."):
            raise ValueError
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    if text.startswith("[") or text.startswith("{"):
        return ast.literal_eval(text)
    return text


def _strip_comment(line: str) -> str:
    out = []
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out).rstrip()


def loads(text: str):
    lines: List[Tuple[int, str]] = []
    for raw in text.splitlines():
        clean = _strip_comment(raw)
        if not clean.strip():
            continue
        indent = len(clean) - len(clean.lstrip(" "))
        lines.append((indent, clean.strip()))

    index = 0

    def parse_block(expected_indent: int):
        nonlocal index
        if index >= len(lines):
            return None
        indent, content = lines[index]
        if indent < expected_indent:
            return None

        if content.startswith("- "):
            items = []
            while index < len(lines):
                indent, content = lines[index]
                if indent != expected_indent or not content.startswith("- "):
                    break
                item_content = content[2:].strip()
                index += 1
                if item_content == "":
                    items.append(parse_block(expected_indent + 2))
                    continue
                if ":" in item_content:
                    key, value = item_content.split(":", 1)
                    mapping = {key.strip(): _parse_scalar(value.strip()) if value.strip() else None}
                    if mapping[key.strip()] is None:
                        mapping[key.strip()] = parse_block(expected_indent + 2)
                    while index < len(lines) and lines[index][0] >= expected_indent + 2 and not lines[index][1].startswith("- "):
                        child_indent, child = lines[index]
                        if child_indent != expected_indent + 2:
                            break
                        ckey, cvalue = child.split(":", 1)
                        index += 1
                        if cvalue.strip():
                            mapping[ckey.strip()] = _parse_scalar(cvalue.strip())
                        else:
                            mapping[ckey.strip()] = parse_block(child_indent + 2)
                    items.append(mapping)
                else:
                    items.append(_parse_scalar(item_content))
            return items

        mapping = {}
        while index < len(lines):
            indent, content = lines[index]
            if indent < expected_indent:
                break
            if indent > expected_indent:
                break
            if content.startswith("- "):
                break
            key, value = content.split(":", 1)
            index += 1
            key = key.strip()
            if value.strip():
                mapping[key] = _parse_scalar(value.strip())
            else:
                mapping[key] = parse_block(expected_indent + 2)
        return mapping

    return parse_block(0) or {}
