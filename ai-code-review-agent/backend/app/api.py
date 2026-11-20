import json
import re
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .code_analyzer import analyze_code, detect_language
from .knowledge_base import (
    answer_question,
    attach_rule_metadata,
    build_review_summary,
    retrieve_knowledge,
)
from .pdf_report import create_pdf_report
from .remediation import attach_remediation

router = APIRouter()


@router.get("/health")
def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-code-review-agent"}


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100_000)
    language: Literal["python", "java"] | None = None
    filename: str | None = Field(default=None, min_length=1, max_length=255)
    project_name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str | None) -> str | None:
        if value is None:
            return value
        safe_name = PurePath(value.replace("\\", "/")).name
        if safe_name != value or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError("Filename must be a simple source filename.")
        return value

    @field_validator("project_name")
    @classmethod
    def validate_project_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        project_name = value.strip()
        if not project_name:
            raise ValueError("Project name cannot be empty.")
        return project_name

    @field_validator("code")
    @classmethod
    def validate_source_size(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Source code cannot be empty.")
        if len(value.encode("utf-8")) > 100_000:
            raise ValueError("Source code must be no larger than 100 KB.")
        return value


class KnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2_000)
    language: Literal["python", "java"] | None = None
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Search query cannot be empty.")
        return value.strip()


class FindingContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=300)
    category: str = Field(default="", max_length=100)
    explanation: str = Field(default="", max_length=1_000)


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)
    answer: str = Field(default="", max_length=3_000)


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)
    language: Literal["python", "java"] | None = None
    finding: FindingContext | None = None
    history: list[ConversationTurn] = Field(default_factory=list, max_length=8)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be empty.")
        return value.strip()


def _analyze(submission: AnalysisRequest) -> dict:
    try:
        language = submission.language or detect_language(
            submission.code, submission.filename
        )
        filename = submission.filename or (
            "main.py" if language == "python" else "Main.java"
        )
        extension = ".py" if language == "python" else ".java"
        if not filename.lower().endswith(extension):
            raise HTTPException(
                status_code=422,
                detail=f"A {language.capitalize()} file must use the {extension} extension.",
            )
        result = analyze_code(submission.code, language, filename)
        attach_rule_metadata(result)
        for index, finding in enumerate(result["findings"], start=1):
            finding["finding_id"] = f"F-{index:03d}"
            finding["category"] = finding["type"]
            finding["language"] = language
            finding["filename"] = filename
        attach_remediation(
            submission.code,
            result["suggested_code"],
            result["findings"],
            language,
        )
        result["summary"] = build_review_summary(
            result["findings"], filename, language, submission.project_name
        )
        result["quality"] = result["summary"]["quality"]
        result["health_score"] = result["summary"]["health_score"]
        result["review_status"] = result["summary"]["review_status"]
        result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        return result
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/analyze")
def analyze_submission(submission: AnalysisRequest) -> dict:
    return _analyze(submission)


@router.post("/knowledge/search")
def search_knowledge(submission: KnowledgeSearchRequest) -> dict:
    try:
        matches = retrieve_knowledge(
            submission.query, submission.language, submission.limit
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"query": submission.query, "retrieval": "local-keyword", **matches}


@router.post("/assistant")
def ask_assistant(submission: AssistantRequest) -> dict:
    finding = submission.finding.model_dump(exclude_unset=False) if submission.finding else None
    try:
        history = [turn.model_dump() for turn in submission.history]
        return answer_question(
            submission.question, submission.language, finding, history
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/report")
def generate_report(submission: AnalysisRequest) -> Response:
    result = _analyze(submission)
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", result["filename"])
    report = {key: value for key, value in result.items() if key != "suggested_code"}
    for finding in report["findings"]:
        finding.get("remediation", {}).pop("original_code", None)
    content = json.dumps(report, indent=2, ensure_ascii=False)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}.review.json"'},
    )


@router.post("/report/pdf")
def generate_pdf_report(submission: AnalysisRequest) -> Response:
    result = _analyze(submission)
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", result["filename"])
    return Response(
        content=create_pdf_report(result),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.review.pdf"'
        },
    )
