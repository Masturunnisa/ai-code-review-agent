import json
import re
from pathlib import Path
from typing import Any

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge-base"
RULES_PATH = KNOWLEDGE_DIR / "security-rules.json"
STOP_WORDS = {
    "a", "about", "an", "and", "are", "can", "could", "do", "does", "for",
    "give", "how", "i", "in", "is", "it", "me", "my", "of", "on", "or",
    "please", "show", "the", "this", "to", "was", "what", "when", "which",
    "why", "with", "would",
}
MAX_DOCUMENT_CHUNK_WORDS = 180
DOCUMENT_CHUNK_OVERLAP_WORDS = 30
SEVERITY_DISPLAY_LEVELS = {
    "critical": "critical",
    "error": "critical",
    "high": "high",
    "medium": "medium",
    "warning": "medium",
    "low": "low",
    "info": "low",
}


def _tokens(value: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        if len(token) <= 1 or token in STOP_WORDS:
            continue
        if token.endswith("ies") and len(token) > 4:
            token = f"{token[:-3]}y"
        elif token.endswith("ing") and len(token) > 5:
            token = token[:-3]
            if len(token) > 2 and token[-1] == token[-2]:
                token = token[:-1]
        elif token.endswith("ed") and len(token) > 4:
            token = token[:-2]
        elif token.endswith("s") and len(token) > 4:
            token = token[:-1]
        tokens.add(token)
    return tokens


def _load_rules() -> list[dict[str, Any]]:
    try:
        catalog = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("The secure coding rule catalog could not be loaded.") from exc
    rules = catalog.get("rules") if isinstance(catalog, dict) else None
    if not isinstance(rules, list):
        raise RuntimeError("The secure coding rule catalog has an invalid format.")
    return rules


def _document_chunks() -> list[dict[str, str]]:
    chunks = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RuntimeError(f"Knowledge document {path.name} could not be read.") from exc

        heading_stack: list[tuple[int, str]] = []
        section_heading = path.stem.replace("-", " ")
        body: list[str] = []

        def append_chunks() -> None:
            text = "\n".join(body).strip()
            if not text:
                body.clear()
                return
            words = text.split()
            step = MAX_DOCUMENT_CHUNK_WORDS - DOCUMENT_CHUNK_OVERLAP_WORDS
            for start in range(0, len(words), step):
                content = " ".join(words[start:start + MAX_DOCUMENT_CHUNK_WORDS])
                if content:
                    chunks.append({
                        "source": path.name,
                        "heading": section_heading,
                        "content": content,
                    })
            body.clear()

        for line in lines:
            heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if heading_match:
                append_chunks()
                level = len(heading_match.group(1))
                heading_stack = [
                    item for item in heading_stack if item[0] < level
                ]
                heading_stack.append((level, heading_match.group(2).strip()))
                section_heading = " > ".join(title for _, title in heading_stack)
            elif line.strip() and not line.lstrip().startswith("```"):
                body.append(line.strip())
        append_chunks()
    return chunks


def _score(query_tokens: set[str], searchable: str, heading: str = "") -> float:
    searchable_tokens = _tokens(searchable)
    matched_tokens = query_tokens & searchable_tokens
    coverage = len(matched_tokens) / len(query_tokens) if query_tokens else 0
    if not matched_tokens or coverage < 0.2:
        return 0
    heading_matches = len(query_tokens & _tokens(heading))
    return round(len(matched_tokens) * coverage + heading_matches * 2, 3)


def retrieve_knowledge(
    query: str,
    language: str | None = None,
    limit: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return {"rules": [], "documents": []}

    ranked_rules = []
    for rule in _load_rules():
        languages = rule.get("languages", [])
        if language and language not in languages:
            continue
        searchable = " ".join([
            str(rule.get("title", "")),
            str(rule.get("rule_id", "")),
            str(rule.get("category", "")),
            str(rule.get("description", "")),
            " ".join(rule.get("tags", [])),
            str(rule.get("source", {}).get("name", "")),
            str(rule.get("recommended_fix", "")),
            str(rule.get("detection_guidance", "")),
        ])
        score = _score(query_tokens, searchable, str(rule.get("title", "")))
        if score:
            ranked_rules.append((score, rule))
    ranked_rules.sort(key=lambda item: (-item[0], item[1]["rule_id"]))

    ranked_docs = []
    for document in _document_chunks():
        searchable = f'{document["heading"]} {document["content"]}'
        score = _score(query_tokens, searchable, document["heading"])
        if score:
            ranked_docs.append((score, document))
    ranked_docs.sort(key=lambda item: (-item[0], item[1]["source"], item[1]["heading"]))

    return {
        "rules": [rule for _, rule in ranked_rules[:limit]],
        "documents": [document for _, document in ranked_docs[:limit]],
    }


def attach_rule_metadata(result: dict[str, Any]) -> dict[str, Any]:
    rules = _load_rules()
    for finding in result.get("findings", []):
        if finding.get("type") != "Security":
            continue
        title = str(finding.get("title", "")).lower()
        match = next(
            (
                rule for rule in rules
                if any(term in title for term in rule.get("finding_match", []))
            ),
            None,
        )
        if match:
            source = match["source"]
            finding["rule_id"] = match["rule_id"]
            guidance = dict(finding.get("guidance") or {})
            guidance.setdefault("standard", source["name"])
            guidance.setdefault("reference", source.get("cwe") or match["rule_id"])
            guidance["url"] = source["url"]
            guidance["source_name"] = source["name"]
            finding["guidance"] = guidance
    return result


def _retrieve_code_context(
    code: str | None,
    question: str,
    finding: dict[str, Any] | None,
) -> str | None:
    if not code:
        return None

    lines = code.splitlines()
    if not lines:
        return None

    selected_lines: set[int] = set()
    finding_line = finding.get("line") if finding else None
    if isinstance(finding_line, int) and 1 <= finding_line <= len(lines):
        selected_lines.update(
            range(max(1, finding_line - 2), min(len(lines), finding_line + 2) + 1)
        )
    else:
        query_tokens = _tokens(question)
        ranked_lines = sorted(
            (
                (len(query_tokens & _tokens(line)), line_number)
                for line_number, line in enumerate(lines, start=1)
            ),
            key=lambda item: (-item[0], item[1]),
        )
        matches = [(score, line_number) for score, line_number in ranked_lines if score]
        if matches:
            for _, line_number in matches[:4]:
                selected_lines.update(
                    range(max(1, line_number - 1), min(len(lines), line_number + 1) + 1)
                )
        elif _tokens(question) & {
            "code", "source", "snippet", "function", "method", "class", "variable", "line",
        }:
            selected_lines.update(range(1, min(len(lines), 8) + 1))
        else:
            return None

    excerpt = [
        f"{line_number}: {lines[line_number - 1][:300]}"
        for line_number in sorted(selected_lines)[:8]
    ]
    return "\n".join(excerpt)


def answer_question(
    question: str,
    language: str | None = None,
    finding: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    code_context = _retrieve_code_context(code, question, finding)
    finding_context = (
        " ".join(str(value) for value in finding.values()) if finding else ""
    )
    history_context = ""
    follow_up = re.search(
        r"\b(?:it|that|this|they|them|those|these)\b|"
        r"\b(?:what about|explain more|and then|the previous)\b",
        question.lower(),
    )
    if history and follow_up:
        history_context = " ".join(
            f"{turn.get('question', '')} {turn.get('answer', '')[:300]}"
            for turn in history[-3:]
        )
    matches = retrieve_knowledge(
        f"{question} {finding_context} {history_context}", language
    )
    rules = matches["rules"]
    documents = matches["documents"]

    if not rules and not documents:
        answer = (
            "I couldn't find a relevant passage in the local knowledge base. "
            "Try naming a topic such as SQL injection, secrets, authentication, or XSS."
        )
        if code_context:
            answer = (
                "I found relevant lines in the submitted code, shown below, but no "
                "matching passage in the local knowledge base. " + answer
            )
        return {
            "answer": answer,
            "sources": [],
            "retrieval": "local-keyword",
            "context_used": bool(finding or history_context or code_context),
            "code_context": code_context,
        }

    if rules:
        rule = rules[0]
        answer = (
            f"{rule['title']}: {rule['description']} "
            f"Review guidance: {rule['detection_guidance']} "
            f"Recommended practice: {rule['recommended_fix']}"
        )
        sources = [{
            "title": rule["source"]["name"],
            "reference": rule["source"].get("cwe") or rule["rule_id"],
            "url": rule["source"]["url"],
        }]
    else:
        document = documents[0]
        answer = document["content"]
        sources = [{
            "title": f'{document["source"]} — {document["heading"]}',
            "reference": document["source"],
            "url": None,
        }]

    if rules and documents:
        document = documents[0]
        excerpt = document["content"][:600].strip()
        answer = (
            f"{answer} Relevant knowledge-base guidance "
            f"({document['source']} — {document['heading']}): {excerpt}"
        )
        sources.append({
            "title": f"{document['source']} — {document['heading']}",
            "reference": document["source"],
            "url": None,
        })

    if finding and finding.get("explanation"):
        answer = f"{finding['explanation']} {answer}"
    if code_context:
        answer = (
            "Relevant submitted source lines are shown below; line numbers refer to "
            "the editor. " + answer
        )
        first_line = code_context.splitlines()[0].split(":", 1)[0]
        last_line = code_context.splitlines()[-1].split(":", 1)[0]
        sources.append({
            "title": "Submitted source",
            "reference": f"Lines {first_line}–{last_line}",
            "url": None,
        })

    return {
        "answer": answer,
        "sources": sources,
        "retrieval": "local-keyword",
        "context_used": bool(finding or history_context or code_context),
        "code_context": code_context,
    }


def determine_code_quality(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "high"

    severities = {str(item.get("severity", "")).lower() for item in findings}
    security_findings = sum(item.get("type") == "Security" for item in findings)
    quality_findings = sum(
        item.get("type") in {"Code quality", "Compilation", "Syntax"}
        for item in findings
    )

    if severities & {"critical", "error"} or quality_findings > 2 or security_findings > 0:
        return "low"
    if severities & {"high", "warning", "medium"}:
        return "medium"
    return "high"


def build_review_summary(
    findings: list[dict[str, Any]],
    filename: str = "source",
    language: str = "unknown",
    project_name: str | None = None,
    tools: dict[str, str] | None = None,
) -> dict[str, Any]:
    severity_order = ("critical", "error", "high", "medium", "warning", "low", "info")
    severity_counts = {
        severity: sum(
            str(item.get("severity", "")).lower() == severity for item in findings
        )
        for severity in severity_order
    }
    normalized_severity_counts = {
        "critical": severity_counts["critical"] + severity_counts["error"],
        "high": severity_counts["high"],
        "medium": severity_counts["medium"] + severity_counts["warning"],
        "low": severity_counts["low"] + severity_counts["info"],
    }
    security_findings = [item for item in findings if item.get("type") == "Security"]
    quality_findings = [
        item for item in findings
        if item.get("type") in {"Code quality", "Compilation", "Syntax"}
    ]
    penalty_weights = {
        "critical": 25,
        "error": 25,
        "high": 15,
        "medium": 8,
        "warning": 8,
        "low": 3,
        "info": 1,
    }
    def score_for(items: list[dict[str, Any]]) -> int:
        return max(
            0,
            100 - sum(
                penalty_weights.get(str(item.get("severity", "")).lower(), 2)
                for item in items
            ),
        )

    health_score = score_for(findings)
    security_score = score_for(security_findings)
    quality_only_findings = [
        item for item in findings if item.get("type") == "Code quality"
    ]
    build_findings = [
        item for item in findings if item.get("type") in {"Compilation", "Syntax"}
    ]
    active_tools = tools or {}
    expected_tools = (
        ("python_ast", "ruff", "bandit")
        if language == "python"
        else ("javac", "java_security")
        if language == "java"
        else ()
    )
    completed_tool_count = sum(
        active_tools.get(tool) == "available" for tool in expected_tools
    )
    coverage_score = (
        round(100 * completed_tool_count / len(expected_tools))
        if expected_tools
        else 0
    )
    health_dimensions = [
        {
            "key": "security",
            "label": "Security",
            "score": security_score,
            "detail": f"{len(security_findings)} security finding(s)",
        },
        {
            "key": "quality",
            "label": "Code quality",
            "score": score_for(quality_only_findings),
            "detail": f"{len(quality_only_findings)} code quality finding(s)",
        },
        {
            "key": "build",
            "label": "Syntax & build",
            "score": score_for(build_findings),
            "detail": f"{len(build_findings)} syntax or compilation finding(s)",
        },
        {
            "key": "overall",
            "label": "Overall health",
            "score": health_score,
            "detail": f"{len(findings)} total finding(s)",
        },
        {
            "key": "coverage",
            "label": "Check coverage",
            "score": coverage_score,
            "detail": (
                f"{completed_tool_count}/{len(expected_tools)} checks completed"
                if expected_tools
                else "Language not identified"
            ),
        },
    ]
    if normalized_severity_counts["critical"] or normalized_severity_counts["high"]:
        review_status = "Changes Requested"
    elif normalized_severity_counts["medium"] or normalized_severity_counts["low"]:
        review_status = "Needs Review"
    else:
        review_status = "Approved"
    if not findings:
        overview = (
            "No issues were reported by the available static checks. "
            "This is not a guarantee that the code is secure."
        )
    else:
        overview = (
            f"{len(findings)} finding(s) reported: {len(security_findings)} security "
            f"and {len(quality_findings)} quality, compilation, or syntax issue(s). "
            "Review each item and validate changes with tests."
        )
    priorities = sorted(
        findings,
        key=lambda item: (
            severity_order.index(str(item.get("severity", "info")).lower())
            if str(item.get("severity", "info")).lower() in severity_order
            else len(severity_order),
            item.get("line") or 0,
        ),
    )
    return {
        "overview": overview,
        "severity_counts": severity_counts,
        "severity_breakdown": normalized_severity_counts,
        "health_score": health_score,
        "health_dimensions": health_dimensions,
        "review_status": review_status,
        "project_name": project_name or filename.rsplit(".", 1)[0],
        "language": language,
        "security_summary": (
            f"{len(security_findings)} security finding(s) require review."
            if security_findings
            else "No security findings were reported by the available checks."
        ),
        "quality_summary": (
            f"{len(quality_findings)} code quality, compilation, or syntax finding(s) reported."
            if quality_findings
            else "No code quality, compilation, or syntax findings were reported."
        ),
        "recommended_corrections": [
            {
                "finding_id": item.get("finding_id"),
                "title": item.get("title"),
                "severity": item.get("severity"),
                "severity_level": item.get(
                    "severity_level",
                    SEVERITY_DISPLAY_LEVELS.get(
                        str(item.get("severity", "")).lower(), "low"
                    ),
                ),
                "line": item.get("line"),
                "recommended_fix": item.get("recommended_fix"),
            }
            for item in priorities
        ],
        "quality": determine_code_quality(findings),
        "priority_findings": [
            {
                "title": item.get("title"),
                "severity": item.get("severity"),
                "severity_level": item.get(
                    "severity_level",
                    SEVERITY_DISPLAY_LEVELS.get(
                        str(item.get("severity", "")).lower(), "low"
                    ),
                ),
                "line": item.get("line"),
                "recommended_fix": item.get("recommended_fix"),
            }
            for item in priorities[:5]
        ],
        "limitations": (
            "Static analysis checks only supported patterns and available tools; it does not "
            "execute submitted code or guarantee the absence of vulnerabilities."
        ),
    }
