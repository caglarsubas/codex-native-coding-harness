"""Bounded, literal roadmap excerpts. Never infer acceptance from prose or tables."""
import re

MAX_TABLES = 32
MAX_ROWS = 100
MAX_HIGHLIGHTS = 8


def roadmap_content(text, spec):
    lines = text.splitlines()
    headings, visible, fence = [], {}, None
    for number, line in enumerate(lines, 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        visible[number] = line
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            headings.append({"line": number, "depth": len(heading[1]), "title": heading[2]})
    boundary = spec.get("historyBoundary")
    history_start = next((h["line"] for h in headings if h["title"] == boundary), None) if boundary else None
    issues = []
    if boundary and history_start is None:
        issues.append("Configured history boundary is missing. Current status is not classified; review the source mapping.")
    ranges = []
    prefixes = spec.get("currentSectionPrefixes", [])
    for index, h in enumerate(headings):
        if boundary and history_start is None:
            break
        if (history_start is None or h["line"] < history_start) and any(h["title"].startswith(p) for p in prefixes):
            end = next((n["line"] for n in headings[index + 1:] if n["depth"] <= h["depth"]), len(lines) + 1)
            ranges.append({**h, "end": min(end, history_start or end)})
    if prefixes and not ranges:
        issues.append("No current section matched the configured prefixes. Read the source; no current state was inferred.")

    def scope(number):
        if history_start and number >= history_start:
            return "historical"
        return "current" if any(h["line"] <= number < h["end"] for h in ranges) else "document"

    highlights = []
    for h in ranges[:MAX_HIGHLIGHTS]:
        excerpt = "\n".join(visible.get(n, "") for n in range(h["line"] + 1, h["end"])).strip()
        highlights.append({"heading": h["title"], "line": h["line"], "text": excerpt[:6000], "truncated": len(excerpt) > 6000})
    tables, omitted_tables = [], 0
    number = 1
    while number < len(lines):
        line, separator = visible.get(number, ""), visible.get(number + 1, "")
        if not line.strip().startswith("|") or not re.fullmatch(r"\s*\|[\s:|\-]+\|\s*", separator):
            number += 1
            continue
        headers = [c.strip() for c in line.strip().strip("|").split("|")]
        start = number
        number += 2
        rows, omitted_rows = [], 0
        while visible.get(number, "").strip().startswith("|"):
            cells = [c.strip() for c in visible[number].strip().strip("|").split("|")]
            if len(cells) == len(headers) and len(headers) <= 20:
                if len(rows) < MAX_ROWS:
                    rows.append([c[:1200] for c in cells])
                else:
                    omitted_rows += 1
            else:
                omitted_rows += 1
            number += 1
        if len(tables) >= MAX_TABLES or len(headers) > 20:
            omitted_tables += 1
            continue
        heading = next((h["title"] for h in reversed(headings) if h["line"] < start), "Document table")
        tables.append({"headers": [h[:200] for h in headers], "rows": rows, "line": start,
                       "heading": heading, "scope": scope(start), "omittedRows": omitted_rows})
    return {"version": 1, "historyStart": history_start, "currentRanges": ranges, "classificationComplete": not issues,
            "highlights": highlights, "tables": tables, "issues": issues,
            "omittedTables": omitted_tables, "omittedHighlights": max(0, len(ranges) - MAX_HIGHLIGHTS)}


def checklist_scope(item, content):
    number = item["line"]
    if content["historyStart"] and number >= content["historyStart"]:
        return "historical"
    return "current" if any(h["line"] <= number < h["end"] for h in content["currentRanges"]) else "document"
