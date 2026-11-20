from __future__ import annotations

from typing import Any


def _example_for(finding: dict[str, Any], language: str) -> str | None:
    title = str(finding.get("title", "")).lower()

    if "hardcoded secret" in title:
        if language == "python":
            return 'import os\n\nAPI_KEY = os.environ["API_KEY"]'
        return (
            'String apiKey = System.getenv("API_KEY");\n'
            'if (apiKey == null || apiKey.isBlank()) {\n'
            '    throw new IllegalStateException("API_KEY is not configured");\n'
            '}'
        )

    if "sql injection" in title:
        if language == "python":
            return (
                'cursor.execute(\n'
                '    "SELECT * FROM users WHERE id = ?",\n'
                '    (user_id,),\n'
                ')'
            )
        return (
            'String sql = "SELECT * FROM users WHERE id = ?";\n'
            'try (PreparedStatement statement = connection.prepareStatement(sql)) {\n'
            '    statement.setInt(1, userId);\n'
            '    try (ResultSet results = statement.executeQuery()) {\n'
            '        // Process the result set.\n'
            '    }\n'
            '}'
        )

    if language == "python" and (
        "dynamic code execution" in title or "eval(" in title or "exec(" in title
    ):
        return "import ast\n\nvalue = ast.literal_eval(untrusted_text)"

    if language == "python" and "shell command" in title:
        return (
            'subprocess.run(\n'
            '    ["tool", validated_argument],\n'
            '    check=True,\n'
            '    shell=False,\n'
            ')'
        )

    if language == "python" and "pickle" in title:
        return "import json\n\ndata = json.loads(untrusted_payload)"

    if language == "java" and "command execution" in title:
        return (
            'Process process = new ProcessBuilder("tool", validatedArgument)\n'
            '        .start();'
        )

    if language == "java" and "deserialization" in title:
        return (
            "// Parse a non-executable format, then validate its schema.\n"
            "UserInput input = jsonMapper.readValue(payload, UserInput.class);"
        )

    return None


def _why_better(finding: dict[str, Any]) -> str:
    title = str(finding.get("title", "")).lower()
    if "hardcoded secret" in title:
        return (
            "Loading credentials from the environment or a secret manager keeps "
            "them out of source control and supports environment-specific rotation."
        )
    if "sql injection" in title:
        return (
            "Bound parameters are treated as data rather than SQL syntax, so user "
            "input cannot change the structure of the query."
        )
    if "dynamic code execution" in title or "eval(" in title or "exec(" in title:
        return (
            "Parsing only supported literal values avoids interpreting untrusted "
            "text as executable code."
        )
    if "shell command" in title or "command execution" in title:
        return (
            "Passing arguments separately avoids shell interpretation; validate "
            "each argument and keep the executable fixed."
        )
    if "pickle" in title or "deserialization" in title:
        return (
            "A non-executable data format avoids constructing arbitrary objects "
            "from untrusted serialized input; validate the parsed schema."
        )
    return (
        "The recommended change addresses the reported diagnostic while leaving "
        "application-specific behavior available for review and testing."
    )


def attach_remediation(
    code: str,
    suggested_code: str,
    findings: list[dict[str, Any]],
    language: str,
) -> None:
    source_lines = code.splitlines()
    suggested_lines = suggested_code.splitlines()
    for finding in findings:
        line = finding.get("line")
        original = (
            source_lines[line - 1]
            if isinstance(line, int) and 0 < line <= len(source_lines)
            else None
        )
        corrected = _example_for(finding, language)
        if (
            corrected is None
            and isinstance(line, int)
            and 0 < line <= len(suggested_lines)
            and suggested_lines[line - 1] != original
        ):
            corrected = suggested_lines[line - 1]

        finding["remediation"] = {
            "original_code": original,
            "corrected_code": corrected,
            "why_problematic": finding.get("explanation", ""),
            "why_better": _why_better(finding),
            "example_is_template": corrected is not None
            and corrected != suggested_lines[line - 1]
            if isinstance(line, int) and 0 < line <= len(suggested_lines)
            else corrected is not None,
        }
