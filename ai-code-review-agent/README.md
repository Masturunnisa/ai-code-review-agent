# AI Code & Security

A local-first Python and Java static-analysis dashboard with a Monaco editor,
file uploads, actionable findings, an original-vs-suggested code diff, a
knowledge-base assistant, health-scored PR summaries, per-finding remediation
examples, and downloadable JSON, Markdown, and PDF reports.

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer and npm
- A JDK on `PATH` for Java compilation findings (`javac -version`)

Ruff, Bandit, and ReportLab are installed from `backend/requirements.txt`. Java
analysis is independent of Python analysis; without `javac`, static Java
security checks still run and the dashboard marks compilation checks
unavailable.

## Run in VS Code on Windows

Open the `ai-code-review-agent` folder in VS Code. Open two integrated
PowerShell terminals and run these commands from the project folder.

**Terminal 1 — backend:**

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

If PowerShell blocks activation, run the backend without activating the
environment:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

**Terminal 2 — frontend:**

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The FastAPI health check and interactive API
documentation are at `http://127.0.0.1:8001/` and
`http://127.0.0.1:8001/docs`.

Both terminals must stay running. The Vite `/api` proxy is configured to
forward to `http://127.0.0.1:8001`; an `ECONNREFUSED` proxy error means the
FastAPI process is not listening on that address, not that analysis succeeded.
Confirm the API is up with
`Invoke-RestMethod http://127.0.0.1:8001/api/health` (expected response:
`status: ok`, `service: ai-code-review-agent`). The dashboard verifies both
values, so an unrelated server on the API port is not reported as connected.
If port 8001 is already occupied, set `VITE_API_PROXY_TARGET` in
`frontend/.env` to the actual backend origin and use that same port in the
Uvicorn startup command. Restart Vite after changing the proxy target.

## Reviewing code

1. Upload or drag in a `.py` or `.java` file, or paste/write source in the
   Monaco editor. Syntax-based detection updates the language indicator;
   ambiguous code requires a manual language choice.
2. Choose **Analyze code**. Results show actual API counts, severity filters,
   source context, recommended fixes, and OWASP Top 10:2021 references where
   the implemented checks map to them.
3. Filter findings by severity and category. Expand an issue to see its
   affected source line, remediation explanation, corrected example, and
   copy-fixed-code action. Examples are illustrative templates; adapt and test
   them before applying.
4. Ask a question in the assistant. It uses the current editor code, selected
   finding, and recent conversation turns to show relevant numbered source
   lines alongside locally retrieved rule/document passages. If no knowledge
   base match is found, it says so.
5. Preview the full report directly in the report workspace or download JSON,
   Markdown, or PDF. The readable preview includes findings, severity counts,
   health dimensions, remediation examples, and the prioritized roadmap, even
   when the browser cannot render embedded PDFs. PDF reports include branded
   page headers and footers, review status, severity breakdown, findings,
   recommendations, and available corrected examples. Submitted source lines
   and the suggested full source are omitted to reduce accidental credential or
   proprietary-code disclosure.

Python uses the Python AST, Ruff, and Bandit. Java uses `javac` with annotation
processing disabled and additional static checks for common security
vulnerabilities. Ruff automatic fixes run only on an isolated temporary copy;
review them in the diff before applying them in the editor. Findings and fixes
are static-analysis guidance, not a guarantee that code is safe.

**Submitted source is never executed.** Java compilation takes place in a
temporary directory with annotation processing disabled. Source files are
limited to 100 KB. The backend does not save submitted code or findings.

The structured rule catalog is `knowledge-base/security-rules.json`; it includes
rule IDs, languages, severity, detection guidance, fixes, and OWASP/CWE source
references. Each result includes a 0–100 health score, normalized Critical /
High / Medium / Low counts, a deterministic PR-style status, and a separate
remediation object for every finding. Safe, rule-specific examples are
illustrative, not automatically applied.

The review summary also includes a five-axis code-health radar: Security, Code
quality, Syntax & build, Overall health, and Check coverage. Finding-based
scores start at 100 and subtract the existing severity penalties for findings
in that category; coverage is the percentage of expected local analyzers that
completed. These explainable static-check signals are not runtime, performance, or
general maintainability measurements.

The assistant performs local keyword retrieval over the rules and Markdown
knowledge base, plus lexical retrieval of relevant numbered lines from the
current editor code. It uses recent turns when resolving follow-up questions.
This is a local, extractive RAG baseline: it does not use embeddings or an
external LLM, and it reports when no relevant knowledge-base source is found.
Code is included only in the assistant request to the local backend and is not
stored. The API remains stateless; analysis results live in the current
frontend session and are not saved to a server-side history or database.

The backend exposes typed agent contracts in `backend/app/agent_contracts.py`.
Static analysis, security checks, per-finding remediation, a findings-based PR
summary, local knowledge retrieval, and PDF generation are implemented.
Independent LLM agents, vector/embedding retrieval, and persistent review
history are not implemented. See [ARCHITECTURE.md](./ARCHITECTURE.md) for
component responsibilities, data flow, endpoint contracts, and limitations.

## API

- `POST /api/analyze` — JSON request:
  `{"code": "...", "filename": "main.py"}`; language is inferred from the
  filename or source syntax. Existing requests may continue to specify
  `"language": "python"` or `"language": "java"`.
- `POST /api/knowledge/search` — accepts `query`, optional `language`, and
  optional result `limit`; returns matching local rules and document chunks
- `POST /api/assistant` — accepts a question, optional language, up to 100 KB
  of current source code, finding metadata, and recent conversation turns;
  returns relevant numbered code lines and grounded local guidance
- `POST /api/report` — same request as analysis; returns JSON without suggested
  source code
- `POST /api/report/pdf` — same request as analysis; returns a downloadable PDF
- `GET /api/health` — backend readiness for the frontend proxy
- `GET /` — API health check
- `GET /docs` — FastAPI OpenAPI documentation

In development, the Vite server proxies `/api` requests to the backend at
`http://127.0.0.1:8001`. Set `VITE_API_PROXY_TARGET` in `frontend/.env` to
change the Vite development proxy target. Set `VITE_API_URL` in a frontend
`.env` file only when calling a different API origin directly; leave it unset
to use the Vite proxy.

## Test and build

From `backend`, run `python -m unittest test_analysis -v` to test analysis,
remediation, assistant context, API validation, and reports. From `frontend`,
run `npm test` for frontend tests and `npm run build` for a production build.
