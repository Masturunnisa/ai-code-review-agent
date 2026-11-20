from typing import Protocol, TypedDict


class ReviewFinding(TypedDict):
    line: int | None
    type: str
    severity: str
    title: str
    explanation: str
    recommended_fix: str


class ReviewContext(TypedDict):
    code: str
    language: str
    filename: str
    findings: list[ReviewFinding]


class AgentResult(TypedDict):
    findings: list[ReviewFinding]
    summary: str


class CodeAnalysisAgent(Protocol):
    def analyze(self, context: ReviewContext) -> AgentResult: ...


class SecurityVulnerabilityAgent(Protocol):
    def analyze_security(self, context: ReviewContext) -> AgentResult: ...


class RemediationAgent(Protocol):
    def recommend_fixes(self, context: ReviewContext) -> AgentResult: ...


class PRSummaryAgent(Protocol):
    def summarize_pull_request(self, context: ReviewContext) -> AgentResult: ...


class ConversationalCodeAssistant(Protocol):
    def answer(self, context: ReviewContext, question: str) -> str: ...
