import type { ValidationRequest, ValidationResponse } from "@/lib/api";

const columns = [
  "record_type",
  "request_institution_id",
  "institution_id",
  "application_type",
  "status",
  "validation_scope",
  "checked_at",
  "report_generated_at",
  "source",
  "notice",
  "required_documents_json",
  "submitted_documents_json",
  "expiry_dates_json",
  "finding_code",
  "document_type",
  "message",
  "evidence_json",
];

export function safeSpreadsheetValue(value: string): string {
  // Prefix risky formula initiators, including ones preceded by whitespace or controls.
  let firstMeaningfulCharacter = 0;
  while (firstMeaningfulCharacter < value.length) {
    const character = value[firstMeaningfulCharacter];
    const code = value.charCodeAt(firstMeaningfulCharacter);
    if (character.trim() !== "" && code > 31 && code !== 127 && code !== 0xfeff) break;
    firstMeaningfulCharacter += 1;
  }
  const trigger = value[firstMeaningfulCharacter];
  return trigger && "=+-@".includes(trigger) ? `'${value}` : value;
}

function csvCell(value: string): string {
  return `"${safeSpreadsheetValue(value).replace(/"/g, '""')}"`;
}

function serializeRequestValues(values: string[] | Record<string, string>): string {
  return JSON.stringify(values);
}

export function createValidationCsv(
  request: ValidationRequest,
  response: ValidationResponse,
  reportGeneratedAt: string,
): string {
  const common = [
    request.institution_id,
    response.institution_id,
    response.application_type,
    response.status,
    response.validation_scope,
    response.checked_at,
    reportGeneratedAt,
    response.source,
    response.notice,
    serializeRequestValues(request.required_documents),
    serializeRequestValues(request.submitted_documents),
    serializeRequestValues(request.expiry_dates),
  ];

  const rows = response.findings.length
    ? response.findings.map((finding) => [
        "finding",
        ...common,
        finding.code,
        finding.document_type,
        finding.message,
        JSON.stringify(finding.evidence),
      ])
    : [[
        "summary",
        ...common,
        "",
        "",
        "No findings returned",
        "{}",
      ]];

  return [columns, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

export function validationReportFilename(checkedAt: string): string {
  const date = /^\d{4}-\d{2}-\d{2}/.exec(checkedAt)?.[0] ?? "undated";
  return `preliminary-validation-${date}.csv`;
}

export function downloadValidationCsv(
  request: ValidationRequest,
  response: ValidationResponse,
): void {
  const generatedAt = new Date().toISOString();
  const file = new Blob([createValidationCsv(request, response, generatedAt)], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(file);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = validationReportFilename(response.checked_at);
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
