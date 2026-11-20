# AI Code Review & Security Analysis Agent

An AI-powered Code Review and Security Analysis Agent that automatically detects Java and Python code errors, identifies security vulnerabilities, provides actionable code correction suggestions, classifies issues by severity, calculates code health scores, and generates detailed PDF reports

---

## Features

- **Multi-Language Static & AI Analysis:** Detects syntax issues, logical bugs, and code smells across Python and Java files
- 
- **Security Vulnerability Detection:** Flags common security flaws mapped against OWASP Top 10, CWE standards, and custom security rules
- 
- **RAG-Powered Knowledge Base:** Grounds reviews and remediation guidance in curated clean-code playbooks, code smell references, and secure coding standards
- 
- **Severity Classification & Health Scoring:** Categorizes findings by severity and computes an overall code health score
- 
- **Automated Remediation Suggestions:** Generates concrete fixes to resolve identified bugs and vulnerabilities
- 
- **Downloadable PDF Reports:** Exports structured audit summaries and findings into detailed PDF reports
---

## Project Structure

```text
Infosys_Project/
├── Agile/                          # Agile documentation & sprint artifacts
└── ai-code-review-agent/
    ├── backend/                    # Python API, code analyzer, RAG knowledge loader & PDF generator
    │   ├── app/
    │   │   ├── agent_contracts.py
    │   │   ├── api.py
    │   │   ├── code_analyzer.py
    │   │   ├── knowledge_base.py
    │   │   ├── pdf_report.py
    │   │   └── remediation.py
    │   ├── tests/
    │   └── requirements.txt
    ├── frontend/                   # React + Vite + Tailwind CSS web interface
    │   ├── src/
    │   │   ├── components/
    │   │   ├── pages/
    │   │   ├── App.jsx
    │   │   └── api.js
    │   └── package.json
    └── knowledge-base/             # Security & clean-code reference documents
        ├── OWASP-Top-10.md
        ├── clean-code.md
        ├── code-review-playbook.md
        ├── code-smells.md
        ├── cwe.md
        ├── rag-indexing-guide.md
        ├── secure-coding-standards.md
        ├── security-rules.json
        └── spot-bugs.md
```[span_20](start_span)[span_20](end_span)[span_21](start_span)[span_21](end_span)[span_22](start_span)[span_22](end_span)[span_23](start_span)[span_23](end_span)

---

## Tech Stack

- **Frontend:** React, Vite, Tailwind CSS[span_24](start_span)[span_24](end_span)
- **Backend:** Python, REST API, RAG Knowledge Engine, PDF Report Generator[span_25](start_span)[span_25](end_span)[span_26](start_span)[span_26](end_span)
- **Knowledge Base:** Markdown & JSON rulebooks (OWASP Top 10, CWE, SpotBugs, Clean Code)[span_27](start_span)[span_27](end_span)

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm

### 1. Backend Setup

```bash
cd ai-code-review-agent/backend
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```[span_28](start_span)[span_28](end_span)[span_29](start_span)[span_29](end_span)

Configure your environment variables (such as LLM API keys) in a `.env` file inside `backend/`, then start the backend server:

```bash
uvicorn app.api:app --reload
```[span_30](start_span)[span_30](end_span)

### 2. Frontend Setup

Open a new terminal window:

```bash
cd ai-code-review-agent/frontend
npm install
npm run dev
```[span_31](start_span)[span_31](end_span)[span_32](start_span)[span_32](end_span)

Open the local URL shown in your terminal (typically `http://localhost:5173`) to use the application.

---

## Usage

1. Launch both the backend API and the React frontend[span_33](start_span)[span_33](end_span)[span_34](start_span)[span_34](end_span).
2. Upload or paste your Python or Java source code into the web interface[span_35](start_span)[span_35](end_span)[span_36](start_span)[span_36](end_span).
3. Review detected bugs, security vulnerabilities, severity classifications, and code health scores[span_37](start_span)[span_37](end_span).
4. Apply suggested code remediations or export the full analysis as a PDF report[span_38](start_span)[span_38](end_span)[span_39](start_span)[span_39](end_span).
5.
