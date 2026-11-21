export function detectLanguage(code) {
  const pythonPatterns = [
    [/^\s*(?:async\s+)?def\s+\w+\b/m, 4],
    [/^\s*class\s+\w+(?:\([^)]*\))?\s*(?::|$)/m, 4],
    [/^\s*(?:if|elif|else|for|while|try|except|finally|with)\b[^:\n]*:/m, 2],
    [/^\s*(?:from\s+[\w.]+\s+import|import\s+\w+)/m, 2],
    [/\b(?:None|True|False)\b/, 1],
    [/\bprint\s*\(/, 2],
  ];
  const javaPatterns = [
    [/\b(?:public|private|protected)\s+(?:(?:static|final|abstract)\s+)*(?:class|interface|enum|record)\s+\w+/, 4],
    [/\b(?:class|interface|enum|record)\s+\w+(?:\s*\{|(?=\s*$))/, 4],
    [/\bSystem\s*\.\s*out\s*\./, 4],
    [/^\s*package\s+[\w.]+\s*;/m, 4],
    [/^\s*import\s+[\w.*]+\s*;/m, 3],
    [/^\s*(?:byte|short|int|long|float|double|boolean|char|String)\s+\w+\s*(?:=|;|,)/m, 2],
    [/\b(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\].?]+\s+\w+\s*\([^)]*\)\s*\{/, 2],
    [/[{}]/, 1],
    [/;/, 1],
  ];
  const score = (patterns) => patterns.reduce(
    (total, [pattern, weight]) => total + (pattern.test(code) ? weight : 0),
    0,
  );

  const pythonScore = score(pythonPatterns);
  const javaScore = score(javaPatterns);
  if (Math.max(pythonScore, javaScore) < 2 || pythonScore === javaScore) return null;
  return pythonScore > javaScore ? 'python' : 'java';
}

export async function readJsonResponse(response, action) {
  const body = await response.text();
  const status = `HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ''}`;

  if (!body.trim()) {
    const reason = response.ok
      ? 'returned an empty response'
      : `failed (${status}) with an empty response`;
    throw new Error(`${action} ${reason}.`);
  }

  let result;
  try {
    result = JSON.parse(body);
  } catch {
    const reason = response.ok
      ? `returned a non-JSON response (${status})`
      : `failed (${status}) with a non-JSON response`;
    throw new Error(`${action} ${reason}.`);
  }

  if (!response.ok) {
    const detail = typeof result?.detail === 'string'
      ? result.detail
      : Array.isArray(result?.detail)
        ? result.detail.map((item) => item.msg).filter(Boolean).join(' ')
        : '';
    throw new Error(detail || `${action} failed (${status}).`);
  }

  if (!result || typeof result !== 'object' || Array.isArray(result)) {
    throw new Error(`${action} returned an invalid JSON response (${status}).`);
  }

  return result;
}

function escapeMarkdownTableCell(value) {
  return String(value ?? '').replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');
}

export function createMarkdownReport(analysis) {
  const severityCounts = analysis.summary?.severity_counts || {};
  const findings = analysis.findings || [];
  const findingRows = findings.length
    ? findings.map((finding) => (
      `| ${escapeMarkdownTableCell(finding.finding_id || '—')} | ${escapeMarkdownTableCell(finding.severity)} | ${escapeMarkdownTableCell(finding.title)} | ${escapeMarkdownTableCell(finding.category || finding.type)} | ${finding.line ?? '—'} |`
    ))
    : ['| — | — | No findings reported | — | — |'];
  const prioritizedFindings = analysis.summary?.recommended_corrections || findings;
  const recommendations = prioritizedFindings.map((finding) => (
    `- **${escapeMarkdownTableCell(finding.severity ? `${finding.severity.charAt(0).toUpperCase()}${finding.severity.slice(1)} · ` : '')}${escapeMarkdownTableCell(finding.title)}**${finding.line ? ` (line ${finding.line})` : ''}: ${escapeMarkdownTableCell(finding.recommended_fix)}`
  ));
  const references = findings
    .filter((finding) => finding.guidance)
    .map((finding) => (
      `- ${escapeMarkdownTableCell(finding.rule_id || finding.guidance.reference)}: `
      + `[${escapeMarkdownTableCell(finding.guidance.standard)}](${finding.guidance.url || ''})`
    ));
  const tools = Object.entries(analysis.tools || {})
    .map(([name, status]) => `- ${name}: ${status}`);
  const normalizedCounts = analysis.summary?.severity_breakdown;
  const counts = normalizedCounts
    ? ['critical', 'high', 'medium', 'low'].map((severity) => `- ${severity}: ${normalizedCounts[severity] || 0}`)
    : Object.entries(severityCounts)
      .filter(([, count]) => count > 0)
      .map(([severity, count]) => `- ${severity}: ${count}`);
  const remediations = findings.flatMap((finding) => {
    const remediation = finding.remediation;
    if (!remediation?.corrected_code) return [];
    return [
      `### ${escapeMarkdownTableCell(finding.finding_id || finding.title)}`,
      '',
      `Why the original is problematic: ${escapeMarkdownTableCell(remediation.why_problematic)}`,
      '',
      '```',
      remediation.corrected_code,
      '```',
      `Why the correction is safer: ${escapeMarkdownTableCell(remediation.why_better)}`,
      '',
    ];
  });

  return [
    `# Code Review Report — ${escapeMarkdownTableCell(analysis.filename)}`,
    '',
    `- Project: ${escapeMarkdownTableCell(analysis.summary?.project_name || analysis.filename)}`,
    `- Language: ${escapeMarkdownTableCell(analysis.language)}`,
    `- Code health: ${analysis.health_score ?? analysis.summary?.health_score ?? 'Not scored'}/100`,
    `- Review status: ${escapeMarkdownTableCell(analysis.review_status || 'Needs Review')}`,
    `- Analyzed at: ${analysis.analyzed_at || 'Not recorded'}`,
    '- Source code is not included in this report.',
    '',
    '## Executive summary',
    '',
    analysis.summary?.overview || `${findings.length} finding(s) reported.`,
    '',
    analysis.summary?.security_summary || '',
    '',
    analysis.summary?.quality_summary || '',
    '',
    ...(analysis.summary?.health_dimensions?.length
      ? [
        '## Multidimensional code health',
        '',
        ...analysis.summary.health_dimensions.map(
          ({ label, score, detail }) => `- ${escapeMarkdownTableCell(label)}: ${score}/100 — ${escapeMarkdownTableCell(detail)}`,
        ),
        '- Scores summarize available static-check findings; they are not runtime or performance measurements.',
        '',
      ]
      : []),
    '## Severity breakdown',
    '',
    ...(counts.length ? counts : ['- No findings']),
    '',
    '## Findings',
    '',
    '| ID | Severity | Finding | Category | Line |',
    '| --- | --- | --- | --- | ---: |',
    ...findingRows,
    '',
    '## Recommended fixes',
    '',
    ...(recommendations.length ? recommendations : ['No fixes are currently recommended.']),
    '',
    ...(remediations.length ? ['## Corrected code examples', '', ...remediations] : []),
    '## References',
    '',
    ...(references.length ? references : ['No rule references were attached to these findings.']),
    '',
    '## Analysis tools',
    '',
    ...(tools.length ? tools : ['- No tool status recorded']),
    '',
    '## Limitations',
    '',
    analysis.summary?.limitations
      || 'Static analysis checks only supported patterns and does not guarantee the absence of vulnerabilities.',
    '',
  ].join('\n');
}
