import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.knowledge_base import (
    DOCUMENT_CHUNK_OVERLAP_WORDS,
    MAX_DOCUMENT_CHUNK_WORDS,
    _document_chunks,
    build_review_summary,
    retrieve_knowledge,
)

client = TestClient(app)


class AnalysisApiTests(unittest.TestCase):
    def test_health_check_is_available_at_root(self):
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.json())

    def test_api_health_check_is_available_through_vite_proxy_path(self):
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "service": "ai-code-review-agent"},
        )

    def test_python_syntax_error_has_line_number(self):
        response = client.post(
            "/api/analyze",
            json={"code": "def greet(:\n    pass\n", "language": "python", "filename": "main.py"},
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["findings"][0]["type"], "Syntax")
        self.assertEqual(result["findings"][0]["line"], 1)
        self.assertFalse(result["code_executed"])

    def test_python_ruff_line_numbers_match_original_source_after_autofix(self):
        source = (
            "import json\n"
            "\n"
            "\n"
            "def build_message(name):\n"
            '    unused_label = "review"\n'
            '    return "Hello, " + name\n'
        ).replace("\n", "\r\n")
        response = client.post(
            "/api/analyze",
            json={"code": source, "language": "python", "filename": "main.py"},
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        finding = next(
            item for item in result["findings"] if item["title"].startswith("F841:")
        )
        self.assertEqual(finding["line"], 5)
        self.assertNotIn("import json", result["suggested_code"])

    def test_python_security_checks_find_dynamic_sql_and_secret(self):
        source = (
            'password = "super-secret-value"\n'
            'cursor.execute(f"SELECT * FROM users WHERE name = \'{user}\'")\n'
        )
        response = client.post(
            "/api/analyze",
            json={"code": source, "language": "python", "filename": "main.py"},
        )
        self.assertEqual(response.status_code, 200)
        titles = [finding["title"] for finding in response.json()["findings"]]
        self.assertIn("Possible hardcoded secret", titles)
        self.assertTrue(any("SQL injection" in title for title in titles))
        mapped_security_findings = [
            finding for finding in response.json()["findings"]
            if finding["type"] == "Security" and "guidance" in finding
        ]
        self.assertTrue(mapped_security_findings)
        self.assertTrue(all(
            finding["guidance"]["standard"] == "OWASP Top 10:2021"
            for finding in mapped_security_findings
        ))
        sql_finding = next(
            finding for finding in response.json()["findings"]
            if "SQL injection" in finding["title"]
        )
        self.assertEqual(sql_finding["rule_id"], "SEC-002")
        self.assertTrue(sql_finding["guidance"]["url"].startswith("https://"))

    def test_analysis_returns_a_real_pr_summary_and_timestamp(self):
        response = client.post(
            "/api/analyze",
            json={
                "code": 'password = "synthetic-only-secret"\n',
                "language": "python",
                "filename": "main.py",
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        high_findings = sum(
            finding["severity"] == "high" for finding in result["findings"]
        )
        self.assertIn(f"{len(result['findings'])} finding(s)", result["summary"]["overview"])
        self.assertEqual(result["summary"]["severity_counts"]["high"], high_findings)
        self.assertEqual(result["quality"], "low")
        self.assertEqual(result["summary"]["quality"], "low")
        self.assertTrue(result["analyzed_at"].endswith("+00:00"))
        self.assertEqual(result["findings"][0]["finding_id"], "F-001")
        self.assertEqual(result["findings"][0]["category"], "Security")
        self.assertEqual(result["findings"][0]["language"], "python")
        self.assertEqual(result["findings"][0]["filename"], "main.py")

    def test_health_dimensions_score_findings_and_analyzer_coverage(self):
        summary = build_review_summary(
            [
                {"type": "Security", "severity": "high"},
                {"type": "Code quality", "severity": "warning"},
                {"type": "Syntax", "severity": "error"},
            ],
            filename="main.py",
            language="python",
            tools={
                "python_ast": "available",
                "ruff": "available",
                "bandit": "unavailable",
            },
        )
        scores = {
            dimension["key"]: dimension["score"]
            for dimension in summary["health_dimensions"]
        }
        self.assertEqual(scores, {
            "security": 85,
            "quality": 92,
            "build": 75,
            "overall": 52,
            "coverage": 67,
        })
        self.assertEqual(
            summary["health_dimensions"][-1]["detail"],
            "2/3 checks completed",
        )

    def test_analysis_includes_finding_remediation_health_and_review_status(self):
        response = client.post(
            "/api/analyze",
            json={
                "code": 'api_key = "synthetic-review-secret"\n',
                "language": "python",
                "filename": "main.py",
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        finding = result["findings"][0]
        self.assertEqual(finding["remediation"]["original_code"], 'api_key = "synthetic-review-secret"')
        self.assertIn('os.environ["API_KEY"]', finding["remediation"]["corrected_code"])
        self.assertTrue(finding["remediation"]["why_problematic"])
        self.assertTrue(finding["remediation"]["why_better"])
        self.assertEqual(result["summary"]["severity_breakdown"]["high"], 1)
        self.assertEqual(result["health_score"], result["summary"]["health_score"])
        self.assertEqual(result["review_status"], "Changes Requested")
        self.assertEqual(result["summary"]["project_name"], "main")
        self.assertIn("security finding", result["summary"]["security_summary"])

    def test_java_sql_finding_includes_a_parameterized_code_example(self):
        response = client.post(
            "/api/analyze",
            json={
                "code": (
                    "class Example { void query(String name) { "
                    'db.executeQuery("SELECT * FROM users " + name); } }\n'
                ),
                "language": "java",
                "filename": "Example.java",
            },
        )
        self.assertEqual(response.status_code, 200)
        finding = next(
            item for item in response.json()["findings"]
            if "SQL injection" in item["title"]
        )
        self.assertIn("PreparedStatement", finding["remediation"]["corrected_code"])
        self.assertIn("setInt", finding["remediation"]["corrected_code"])

    def test_clean_python_code_has_no_security_findings(self):
        response = client.post(
            "/api/analyze",
            json={
                "code": "def add(left, right):\n    return left + right\n",
                "language": "python",
                "filename": "main.py",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["counts"]["security"], 0)
        self.assertEqual(response.json()["findings"], [])

    def test_java_security_checks_find_secret_and_dynamic_sql(self):
        source = (
            'class Example { String apiKey = "super-secret-value"; '
            'void query(String name) { db.executeQuery("SELECT * FROM users " + name); } }\n'
        )
        response = client.post(
            "/api/analyze",
            json={"code": source, "language": "java", "filename": "Example.java"},
        )
        self.assertEqual(response.status_code, 200)
        titles = [finding["title"] for finding in response.json()["findings"]]
        self.assertIn("Possible hardcoded secret", titles)
        self.assertIn("Potential SQL injection", titles)

    def test_detects_python_language_and_filename_when_omitted(self):
        response = client.post(
            "/api/analyze",
            json={"code": "def greet(name):\n    return name\n"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["language"], "python")
        self.assertEqual(response.json()["filename"], "main.py")

    def test_detects_python_syntax_errors_when_language_is_omitted(self):
        response = client.post(
            "/api/analyze",
            json={"code": "def greet(:\n    pass\n"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["language"], "python")
        self.assertEqual(response.json()["findings"][0]["type"], "Syntax")

    def test_detects_java_language_and_filename_when_omitted(self):
        response = client.post(
            "/api/analyze",
            json={
                "code": (
                    "public class Main {\n"
                    "    public static void main(String[] args) {\n"
                    "        System.out.println(\"Hello\");\n"
                    "    }\n"
                    "}\n"
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["language"], "java")
        self.assertEqual(response.json()["filename"], "Main.java")

    def test_rejects_ambiguous_source_when_language_and_filename_are_omitted(self):
        response = client.post("/api/analyze", json={"code": "value = 1"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("Could not determine", response.json()["detail"])

    def test_java_compilation_error_has_line_number(self):
        response = client.post(
            "/api/analyze",
            json={
                "code": "class Broken {\n    void test() {\n        int n = ;\n    }\n}\n",
                "language": "java",
                "filename": "Broken.java",
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["counts"]["errors"] > 0)
        self.assertTrue(all(finding["line"] for finding in result["findings"]))
        self.assertFalse(result["code_executed"])

    def test_rejects_language_file_extension_mismatch(self):
        response = client.post(
            "/api/analyze",
            json={"code": "print('hi')", "language": "python", "filename": "Main.java"},
        )
        self.assertEqual(response.status_code, 422)

    def test_rejects_empty_source(self):
        response = client.post(
            "/api/analyze",
            json={"code": "  ", "language": "java", "filename": "Main.java"},
        )
        self.assertEqual(response.status_code, 422)

    def test_downloads_actual_json_analysis_report(self):
        response = client.post(
            "/api/report",
            json={
                "code": "def greet(:\n    pass\n",
                "language": "python",
                "filename": "main.py",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-disposition"].startswith("attachment;"))
        self.assertEqual(response.json()["findings"][0]["line"], 1)
        self.assertNotIn("suggested_code", response.json())

    def test_json_report_does_not_include_submitted_secret_or_suggested_source(self):
        synthetic_secret = "synthetic-report-secret-123"
        response = client.post(
            "/api/report",
            json={
                "code": f'password = "{synthetic_secret}"\n',
                "language": "python",
                "filename": "main.py",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(synthetic_secret, response.text)
        self.assertNotIn("suggested_code", response.json())

        analysis = client.post(
            "/api/analyze",
            json={
                "code": f'password = "{synthetic_secret}"\n',
                "language": "python",
                "filename": "main.py",
            },
        )
        self.assertEqual(analysis.status_code, 200)
        for finding in analysis.json()["findings"]:
            self.assertNotIn(synthetic_secret, finding["title"])
            self.assertNotIn(synthetic_secret, finding["explanation"])

    def test_pdf_report_download_contains_a_pdf_and_not_submitted_source(self):
        synthetic_secret = "synthetic-pdf-secret-987"
        response = client.post(
            "/api/report/pdf",
            json={
                "code": f'password = "{synthetic_secret}"\n',
                "language": "python",
                "filename": "main.py",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertNotIn(synthetic_secret.encode(), response.content)
        self.assertIn("main.py.review.pdf", response.headers["content-disposition"])

    def test_milestone_four_samples_complete_analysis_assistant_and_pdf_flow(self):
        samples = [
            ("sample_basic_mistakes.py", "python"),
            ("sample_vulnerabilities.java", "java"),
            ("sample_complex_review.py", "python"),
        ]
        for filename, expected_language in samples:
            with self.subTest(filename=filename):
                source = (Path(__file__).parent / filename).read_text(encoding="utf-8")
                request = {
                    "code": source,
                    "filename": filename,
                    "project_name": "Milestone 4 Demo",
                }

                analysis_response = client.post("/api/analyze", json=request)
                self.assertEqual(analysis_response.status_code, 200)
                analysis = analysis_response.json()
                self.assertEqual(analysis["language"], expected_language)
                self.assertEqual(analysis["summary"]["project_name"], "Milestone 4 Demo")
                self.assertFalse(analysis["code_executed"])
                self.assertEqual(
                    sum(analysis["summary"]["severity_breakdown"].values()),
                    analysis["counts"]["total"],
                )
                self.assertTrue(analysis["summary"]["review_status"])
                self.assertTrue(analysis["analyzed_at"])
                self.assertEqual(
                    [dimension["key"] for dimension in analysis["summary"]["health_dimensions"]],
                    ["security", "quality", "build", "overall", "coverage"],
                )
                if expected_language == "java" or filename == "sample_complex_review.py":
                    security_findings = [
                        item for item in analysis["findings"]
                        if item["type"] == "Security"
                    ]
                    self.assertTrue(security_findings)
                    self.assertTrue(all(
                        item["remediation"]["why_better"] for item in security_findings
                    ))

                assistant_response = client.post(
                    "/api/assistant",
                    json={
                        "question": "How can I prevent SQL injection?",
                        "language": expected_language,
                    },
                )
                self.assertEqual(assistant_response.status_code, 200)
                assistant = assistant_response.json()
                self.assertTrue(assistant["sources"])
                self.assertIn("local-keyword", assistant["retrieval"])

                pdf_response = client.post("/api/report/pdf", json=request)
                self.assertEqual(pdf_response.status_code, 200)
                self.assertEqual(pdf_response.headers["content-type"], "application/pdf")
                self.assertTrue(pdf_response.content.startswith(b"%PDF-"))
                self.assertIn(
                    f"{filename}.review.pdf",
                    pdf_response.headers["content-disposition"],
                )

    def test_rag_chunks_are_bounded_and_irrelevant_queries_are_not_returned(self):
        chunks = _document_chunks()
        self.assertTrue(chunks)
        self.assertTrue(all(
            len(chunk["content"].split()) <= MAX_DOCUMENT_CHUNK_WORDS
            for chunk in chunks
        ))
        self.assertTrue(any(chunk["source"] == "OWASP-Top-10.md" for chunk in chunks))
        self.assertGreater(MAX_DOCUMENT_CHUNK_WORDS, DOCUMENT_CHUNK_OVERLAP_WORDS)
        self.assertEqual(
            retrieve_knowledge("quantum chromodynamics", "python")["documents"],
            [],
        )
        matches = retrieve_knowledge("preventing SQL injections", "python")
        self.assertEqual(matches["rules"][0]["rule_id"], "SEC-002")
        self.assertTrue(any(
            "injection" in chunk["content"].lower()
            for chunk in matches["documents"]
        ))

    def test_searches_local_knowledge_by_topic_and_language(self):
        response = client.post(
            "/api/knowledge/search",
            json={"query": "What is SQL injection?", "language": "python"},
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["retrieval"], "local-keyword")
        self.assertEqual(result["rules"][0]["rule_id"], "SEC-002")
        self.assertTrue(result["documents"])

    def test_local_assistant_answers_with_a_source_and_finding_context(self):
        response = client.post(
            "/api/assistant",
            json={
                "question": "Why was this issue detected?",
                "language": "python",
                "code": (
                    "def lookup(cursor, query):\n"
                    "    user_input = input()\n"
                    "    cursor.execute(query + user_input)\n"
                    "    return cursor.fetchone()\n"
                ),
                "finding": {
                    "title": "Potential SQL injection",
                    "category": "Security",
                    "explanation": "The query includes dynamic input.",
                    "line": 3,
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["retrieval"], "local-keyword")
        self.assertIn("dynamic input", result["answer"])
        self.assertTrue(result["sources"][0]["url"].startswith("https://"))
        self.assertIn("3:     cursor.execute", result["code_context"])
        self.assertTrue(any(
            source["title"] == "Submitted source"
            for source in result["sources"]
        ))

    def test_assistant_returns_code_context_for_a_code_question(self):
        response = client.post(
            "/api/assistant",
            json={
                "question": "Explain this code",
                "language": "python",
                "code": "def greet(name):\n    return 'Hello ' + name\n",
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIn("1: def greet(name):", result["code_context"])
        self.assertTrue(result["context_used"])

    def test_assistant_rejects_source_larger_than_the_analysis_limit(self):
        response = client.post(
            "/api/assistant",
            json={"question": "Explain this code", "code": "a" * 100_001},
        )
        self.assertEqual(response.status_code, 422)

    def test_assistant_uses_history_to_resolve_a_follow_up_question(self):
        response = client.post(
            "/api/assistant",
            json={
                "question": "What should I change for that?",
                "language": "python",
                "history": [
                    {
                        "question": "Why is SQL injection dangerous?",
                        "answer": "It may alter a database query.",
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["context_used"])
        self.assertEqual(result["retrieval"], "local-keyword")
        self.assertIn("SQL", result["answer"])

    def test_assistant_reports_when_no_local_guidance_matches(self):
        response = client.post(
            "/api/assistant",
            json={"question": "What is quantum chromodynamics?", "language": "java"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"], [])
        self.assertIn("couldn't find", response.json()["answer"])


if __name__ == "__main__":
    unittest.main()
