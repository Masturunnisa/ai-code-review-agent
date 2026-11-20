import { describe, expect, it } from 'vitest';
import { createMarkdownReport, detectLanguage, readJsonResponse } from './api';

function makeResponse(body, { status = 200, statusText = 'OK' } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    text: async () => body,
  };
}

describe('detectLanguage', () => {
  it('detects Python code from its syntax', () => {
    expect(detectLanguage('def greet(name):\n    return f"Hi {name}"')).toBe('python');
  });

  it('detects Python even when a function declaration has a syntax error', () => {
    expect(detectLanguage('def greet(:\n    pass')).toBe('python');
  });

  it('detects short Python snippets that begin with an import', () => {
    expect(detectLanguage('import os\nprint(os.name)')).toBe('python');
  });

  it('detects Java code from its syntax', () => {
    expect(detectLanguage('public class Main {\n  public static void main(String[] args) {\n    System.out.println("Hi");\n  }\n}')).toBe('java');
  });

  it('detects short Java snippets with an import or typed declaration', () => {
    expect(detectLanguage('import java.util.List;\nList<String> names = List.of("Ada");')).toBe('java');
    expect(detectLanguage('int count = 1;')).toBe('java');
  });

  it('leaves ambiguous code unchanged', () => {
    expect(detectLanguage('value = 1')).toBeNull();
  });

  it('recognizes Java syntax before the class closing brace is typed', () => {
    expect(detectLanguage('public class Main {')).toBe('java');
  });
});

describe('readJsonResponse', () => {
  it('parses a successful JSON response', async () => {
    await expect(readJsonResponse(makeResponse('{"findings":[]}'), 'Analysis'))
      .resolves.toEqual({ findings: [] });
  });

  it('reports an empty successful response without exposing a JSON parse error', async () => {
    await expect(readJsonResponse(makeResponse(''), 'Analysis'))
      .rejects.toThrow('Analysis returned an empty response.');
  });

  it('reports a non-JSON successful response', async () => {
    await expect(readJsonResponse(makeResponse('<html>error</html>'), 'Analysis'))
      .rejects.toThrow('Analysis returned a non-JSON response (HTTP 200 OK).');
  });

  it('preserves API validation details for unsuccessful responses', async () => {
    await expect(readJsonResponse(
      makeResponse('{"detail":"Invalid source"}', { status: 422, statusText: 'Unprocessable Entity' }),
      'Analysis',
    )).rejects.toThrow('Invalid source');
  });

  it('reports the status when an unsuccessful response has no body', async () => {
    await expect(readJsonResponse(
      makeResponse('', { status: 502, statusText: 'Bad Gateway' }),
      'Analysis',
    )).rejects.toThrow('Analysis failed (HTTP 502 Bad Gateway) with an empty response.');
  });
});

describe('createMarkdownReport', () => {
  it('formats actual analysis details without embedding submitted source', () => {
    const report = createMarkdownReport({
      filename: 'main.py',
      language: 'python',
      analyzed_at: '2026-10-25T12:00:00+00:00',
      suggested_code: 'password = "do-not-export-this"',
      summary: {
        overview: 'One high severity issue.',
        severity_counts: { high: 1, medium: 0, low: 0 },
        limitations: 'Static analysis is not a guarantee.',
      },
      findings: [{
        title: 'Possible hardcoded secret',
        type: 'Security',
        severity: 'high',
        line: 1,
        recommended_fix: 'Read it from a secret manager.',
        rule_id: 'SEC-001',
        guidance: {
          standard: 'OWASP Secrets Management Cheat Sheet',
          reference: 'CWE-798',
          url: 'https://example.com/secret-guidance',
        },
      }],
      tools: { python_ast: 'available' },
    });

    expect(report).toContain('# Code Review Report — main.py');
    expect(report).toContain('Possible hardcoded secret');
    expect(report).toContain('SEC-001');
    expect(report).toContain('python_ast: available');
    expect(report).not.toContain('do-not-export-this');
  });

  it('includes the PR status, health score, and corrected code example', () => {
    const report = createMarkdownReport({
      filename: 'Main.java',
      language: 'java',
      health_score: 85,
      review_status: 'Changes Requested',
      summary: {
        project_name: 'Main',
        severity_breakdown: { critical: 0, high: 1, medium: 0, low: 0 },
        security_summary: 'One security finding.',
        quality_summary: 'No code quality findings.',
        overview: 'One high severity security finding.',
      },
      findings: [{
        finding_id: 'F-001',
        title: 'Potential SQL injection',
        severity: 'high',
        type: 'Security',
        line: 12,
        recommended_fix: 'Use a PreparedStatement.',
        remediation: {
          why_problematic: 'Query input is concatenated.',
          corrected_code: 'statement.setInt(1, userId);',
          why_better: 'Bind values separately from the query.',
        },
      }],
    });

    expect(report).toContain('Code health: 85/100');
    expect(report).toContain('Review status: Changes Requested');
    expect(report).toContain('One security finding.');
    expect(report).toContain('statement.setInt(1, userId);');
  });
});
