import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

MAX_SOURCE_BYTES = 100_000
SEVERITY_LEVELS = {
    "critical": "critical",
    "error": "critical",
    "high": "high",
    "medium": "medium",
    "warning": "medium",
    "low": "low",
    "info": "low",
}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SECRET_PATTERN = re.compile(
    r"(?:password|passwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token)",
    re.IGNORECASE,
)


def detect_language(code: str, filename: str | None = None) -> str:
    extension = Path(filename).suffix.lower() if filename else ""
    if extension == ".py":
        return "python"
    if extension == ".java":
        return "java"

    python_patterns = (
        (r"(?m)^\s*(?:async\s+)?def\s+\w+\b", 4),
        (r"(?m)^\s*class\s+\w+(?:\([^)]*\))?\s*(?::|$)", 4),
        (r"(?m)^\s*(?:if|elif|else|for|while|try|except|finally|with)\b[^:\n]*:", 2),
        (r"\b(?:None|True|False)\b", 1),
        (r"\bprint\s*\(", 2),
    )
    java_patterns = (
        (r"\b(?:public|private|protected)\s+(?:(?:static|final|abstract)\s+)*"
         r"(?:class|interface|enum|record)\s+\w+", 4),
        (r"\b(?:class|interface|enum|record)\s+\w+(?:\s*\{|(?=\s*$))", 4),
        (r"\bSystem\s*\.\s*out\s*\.", 4),
        (r"(?m)^\s*package\s+[\w.]+\s*;", 4),
        (r"\b(?:public|private|protected)\s+(?:static\s+)?"
         r"[\w<>\[\].?]+\s+\w+\s*\([^)]*\)\s*\{", 2),
        (r"[{}]", 1),
        (r";", 1),
    )

    def score(patterns: tuple[tuple[str, int], ...]) -> int:
        return sum(weight for pattern, weight in patterns if re.search(pattern, code))

    python_score = score(python_patterns)
    java_score = score(java_patterns)
    if max(python_score, java_score) < 2 or python_score == java_score:
        raise ValueError(
            "Could not determine whether the source is Python or Java. "
            "Choose a language or upload a .py or .java file."
        )
    return "python" if python_score > java_score else "java"


def _finding(
    line: int | None,
    category: str,
    severity: str,
    title: str,
    explanation: str,
    fix: str,
) -> dict[str, Any]:
    references = {
        "hardcoded secret": ("A02", "Cryptographic Failures"),
        "sql injection": ("A03", "Injection"),
        "command execution": ("A03", "Injection"),
        "pickle": ("A08", "Software and Data Integrity Failures"),
        "deserialization": ("A08", "Software and Data Integrity Failures"),
    }
    guidance = None
    if category == "Security":
        title_key = title.lower()
        reference = next(
            (value for key, value in references.items() if key in title_key),
            None,
        )
        if reference:
            guidance = {
                "standard": "OWASP Top 10:2021",
                "reference": f"{reference[0]}: {reference[1]}",
            }

    result = {
        "line": line,
        "type": category,
        "severity": severity,
        "severity_level": SEVERITY_LEVELS.get(severity.lower(), "low"),
        "title": title,
        "explanation": explanation,
        "recommended_fix": fix,
    }
    if guidance:
        result["guidance"] = guidance
    return result


def _finding_key(finding: dict[str, Any]) -> tuple[Any, ...]:
    title = str(finding.get("title", "")).lower()
    if finding.get("type") == "Security":
        topics = {
            "hardcoded-secret": ("hardcoded secret", "password value"),
            "sql-injection": ("sql injection", "dynamic sql"),
            "command-execution": (
                "shell command",
                "command execution",
                "shell=true",
                "subprocess call",
            ),
            "unsafe-deserialization": ("pickle", "deserialization"),
        }
        topic = next(
            (
                key for key, aliases in topics.items()
                if any(alias in title for alias in aliases)
            ),
            title,
        )
    else:
        topic = title
    return finding.get("line"), finding.get("type"), topic


def _python_security(tree: ast.AST) -> list[dict[str, Any]]:
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if len(value.value) >= 5 and value.value.lower() not in {
                    "changeme", "placeholder", "example", "your_api_key"
                }:
                    names = [
                        part.id for target in targets for part in ast.walk(target)
                        if isinstance(part, ast.Name)
                    ]
                    if any(SECRET_PATTERN.search(name) for name in names):
                        findings.append(_finding(
                            node.lineno, "Security", "high", "Possible hardcoded secret",
                            "A credential-like variable is assigned a literal string. Secrets in "
                            "source can leak through repositories and logs.",
                            "Read the secret from an environment variable or a secret manager; "
                            "rotate it if it has been exposed.",
                        ))
                        break

        if not isinstance(node, ast.Call):
            continue

        name = node.func.attr if isinstance(node.func, ast.Attribute) else (
            node.func.id if isinstance(node.func, ast.Name) else ""
        )
        qualified = ast.unparse(node.func) if hasattr(ast, "unparse") else name

        if name in {"execute", "executemany"} and node.args:
            query = node.args[0]
            has_sql = any(
                isinstance(part, ast.Constant)
                and isinstance(part.value, str)
                and re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|DROP)\b", part.value, re.I)
                for part in ast.walk(query)
            )
            dynamic = isinstance(query, ast.JoinedStr) or (
                isinstance(query, ast.BinOp) and isinstance(query.op, ast.Add)
            )
            if has_sql and dynamic:
                findings.append(_finding(
                    node.lineno, "Security", "high", "Potential SQL injection",
                    "The SQL statement appears to combine a query string with dynamic input, "
                    "which can let an attacker change the query.",
                    "Use a parameterized query and pass values separately instead of interpolating "
                    "or concatenating them into SQL.",
                ))

        if name in {"eval", "exec"}:
            findings.append(_finding(
                node.lineno, "Security", "high", f"Dynamic code execution via {name}()",
                f"{name}() interprets a string as code and can execute attacker-controlled input.",
                "Avoid evaluating dynamic strings; use a format-specific parser or "
                "ast.literal_eval() for Python literals.",
            ))

        if name in {"run", "Popen", "call", "check_call", "check_output"} and any(
            keyword.arg == "shell"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        ):
            findings.append(_finding(
                node.lineno, "Security", "high", "Shell command uses shell=True",
                "Passing a command through a shell can enable command injection when untrusted "
                "data reaches the command.",
                "Pass the executable and arguments as a list, keep shell=False, and validate "
                "untrusted arguments.",
            ))

        if qualified in {"pickle.load", "pickle.loads"}:
            findings.append(_finding(
                node.lineno, "Security", "high", "Unsafe pickle deserialization",
                "Unpickling untrusted data can execute arbitrary code.",
                "Do not unpickle untrusted data; prefer a non-executable format such as JSON "
                "with schema validation.",
            ))

    return findings


def _analyze_ruff(source_path: Path, cwd: Path) -> tuple[list[dict], str, str]:
    executable = shutil.which("ruff")
    if executable:
        command = [executable, "check"]
    elif importlib.util.find_spec("ruff"):
        command = [sys.executable, "-m", "ruff", "check"]
    else:
        return [], source_path.read_text(encoding="utf-8"), "unavailable"
    original_code = source_path.read_text(encoding="utf-8")
    rules = ["--select=E4,E7,E9,F"]
    try:
        result = subprocess.run(
            [*command, "--output-format=json", *rules, str(source_path)],
            cwd=cwd, capture_output=True, text=True, timeout=10, check=False, shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Ruff analysis timed out. Try a smaller source file.") from exc

    try:
        diagnostics = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ruff returned an unreadable analysis result.") from exc

    suggested_path = source_path.with_name(
        f"{source_path.stem}-suggested{source_path.suffix}"
    )
    suggested_path.write_text(original_code, encoding="utf-8", newline="")
    try:
        subprocess.run(
            [*command, "--fix", *rules, str(suggested_path)],
            cwd=cwd, capture_output=True, text=True, timeout=10, check=False, shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Ruff auto-fix timed out. Try a smaller source file.") from exc

    findings = []
    for item in diagnostics:
        code = item.get("code", "")
        message = item.get("message", "Ruff detected a code quality issue.")
        findings.append(_finding(
            item.get("location", {}).get("row"),
            "Code quality",
            "error" if code.startswith(("E9", "F6", "F7", "F8")) else "warning",
            f"{code}: {message}",
            message,
            (item.get("fix") or {}).get("message") or message,
        ))
    return findings, suggested_path.read_text(encoding="utf-8"), "available"


def _analyze_bandit(source_path: Path, cwd: Path) -> tuple[list[dict], str]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "bandit", "-f", "json", "-q", str(source_path)],
            cwd=cwd, capture_output=True, text=True, timeout=10, check=False, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            raise RuntimeError("Bandit security analysis timed out.") from exc
        return [], "unavailable"
    try:
        report = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        if result.returncode == 0:
            return [], "available"
        raise RuntimeError("Bandit returned an unreadable analysis result.") from exc

    findings = []
    for item in report.get("results", []):
        test_id = item.get("test_id", "Bandit")
        issue_text = item.get("issue_text", "Bandit detected a potential security issue.")
        explanation = issue_text
        if test_id in {"B105", "B106", "B107"}:
            issue_text = "Possible hardcoded secret or password value (redacted)"
            explanation = "A credential-like value was found; its value is redacted from the result."
        findings.append(_finding(
            item.get("line_number"), "Security",
            str(item.get("issue_severity", "low")).lower(),
            f"{test_id}: {issue_text}",
            explanation,
            item.get("more_info", "Review this finding and use a safe alternative."),
        ))
    return findings, "available"


def _java_security(code: str) -> list[dict[str, Any]]:
    checks = [
        (
            re.compile(
                r"\b(?:password|passwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token)"
                r"\s*=\s*\"([^\"]{5,})\"",
                re.IGNORECASE,
            ),
            "high", "Possible hardcoded secret",
            "A credential-like variable is assigned a literal string and could leak through "
            "source control.",
            "Read the secret from an environment variable or secret manager; rotate it if exposed.",
        ),
        (
            re.compile(
                r"\b(?:executeQuery|executeUpdate|execute|prepareStatement)"
                r"\s*\(\s*[^;\n]*\+"
            ),
            "high", "Potential SQL injection",
            "The SQL call appears to concatenate dynamic input into a query.",
            "Use a PreparedStatement with placeholders and bind each value using the matching "
            "typed setter.",
        ),
        (
            re.compile(r"\bRuntime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec\s*\("),
            "high", "Operating-system command execution",
            "Runtime.exec() invokes an operating-system command and can enable command injection.",
            "Avoid shell commands or use ProcessBuilder with a fixed executable and separately "
            "validated arguments.",
        ),
        (
            re.compile(r"\bObjectInputStream\b|\.\s*readObject\s*\("),
            "high", "Potentially unsafe Java deserialization",
            "Deserializing untrusted Java objects can instantiate unsafe classes.",
            "Avoid deserializing untrusted objects; use a constrained data format and validate input.",
        ),
    ]
    findings = []
    for pattern, severity, title, explanation, fix in checks:
        for match in pattern.finditer(code):
            findings.append(_finding(
                code.count("\n", 0, match.start()) + 1,
                "Security", severity, title, explanation, fix,
            ))
    return findings


def _analyze_java(code: str, filename: str) -> tuple[list[dict], str]:
    compiler = shutil.which("javac")
    if not compiler:
        return [], "unavailable"
    public_class = re.search(
        r"\bpublic\s+(?:(?:abstract|final|sealed|non-sealed)\s+)*class\s+"
        r"([A-Za-z_$][A-Za-z0-9_$]*)",
        code,
    )
    source_name = f"{public_class.group(1)}.java" if public_class else filename
    with tempfile.TemporaryDirectory(prefix="code-review-java-") as temp_dir:
        root = Path(temp_dir)
        source_path = root / source_name
        output_path = root / "classes"
        output_path.mkdir()
        source_path.write_text(code, encoding="utf-8", newline="")
        try:
            result = subprocess.run(
                [compiler, "-proc:none", "-Xlint:all", "-d",
                 str(output_path), str(source_path)],
                cwd=temp_dir, capture_output=True, text=True, timeout=15,
                check=False, shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Java compilation timed out. Try a smaller source file.") from exc

    findings = []
    pattern = re.compile(r"\.java:(\d+):\s*(error|warning):\s*(.*)")
    for match in pattern.finditer(result.stderr + "\n" + result.stdout):
        level, message = match.group(2), match.group(3).strip()
        findings.append(_finding(
            int(match.group(1)),
            "Compilation" if level == "error" else "Code quality",
            "error" if level == "error" else "warning",
            f"javac {level}: {message}", message,
            "Fix the compiler diagnostic at this line, then analyze the source again.",
        ))
    return findings, "available"


def determine_code_quality(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "high"

    severities = {str(item.get("severity", "")).lower() for item in findings}
    security_findings = sum(item.get("type") == "Security" for item in findings)
    quality_findings = sum(item.get("type") in {"Code quality", "Compilation", "Syntax"} for item in findings)

    if severities & {"critical", "error"} or security_findings > 0 or quality_findings > 2:
        return "low"
    if severities & {"high", "warning", "medium"} or security_findings > 0:
        return "medium"
    return "high"


def analyze_code(code: str, language: str, filename: str) -> dict[str, Any]:
    if not code.strip():
        raise ValueError("Source code cannot be empty.")
    if len(code.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("Source code must be no larger than 100 KB.")

    findings: list[dict[str, Any]] = []
    tools: dict[str, str] = {}
    suggested_code = code

    if language == "python":
        try:
            tree = ast.parse(code, filename=filename)
        except SyntaxError as exc:
            tools["python_ast"] = "available"
            findings.append(_finding(
                exc.lineno, "Syntax", "error", f"Python syntax error: {exc.msg}",
                exc.msg, "Correct the syntax at this line, then analyze the code again.",
            ))
        else:
            tools["python_ast"] = "available"
            findings.extend(_python_security(tree))
            with tempfile.TemporaryDirectory(prefix="code-review-python-") as temp_dir:
                source_path = Path(temp_dir) / Path(filename).name
                source_path.write_text(code, encoding="utf-8", newline="")
                issues, suggested_code, tools["ruff"] = _analyze_ruff(
                    source_path, Path(temp_dir)
                )
                findings.extend(issues)
                issues, tools["bandit"] = _analyze_bandit(source_path, Path(temp_dir))
                findings.extend(issues)
    elif language == "java":
        issues, tools["javac"] = _analyze_java(code, filename)
        findings.extend(issues)
        findings.extend(_java_security(code))
        tools["java_security"] = "available"
    else:
        raise ValueError("Language must be either 'python' or 'java'.")

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for finding in findings:
        key = _finding_key(finding)
        existing = unique.get(key)
        if existing is None or SEVERITY_RANK.get(
            finding["severity_level"], len(SEVERITY_RANK)
        ) < SEVERITY_RANK.get(existing["severity_level"], len(SEVERITY_RANK)):
            unique[key] = finding
    findings = sorted(
        unique.values(),
        key=lambda item: (
            item["line"] is None,
            item["line"] or 0,
            item["severity_level"],
            item["title"],
        ),
    )
    counts = {
        "total": len(findings),
        "errors": sum(item["severity"] == "error" for item in findings),
        "warnings": sum(item["severity"] == "warning" for item in findings),
        "security": sum(item["type"] == "Security" for item in findings),
        "quality": sum(item["type"] == "Code quality" for item in findings),
    }
    quality = determine_code_quality(findings)
    return {
        "language": language,
        "filename": filename,
        "findings": findings,
        "counts": counts,
        "quality": quality,
        "suggested_code": suggested_code,
        "auto_fixes_applied": suggested_code != code,
        "tools": tools,
        "code_executed": False,
    }
