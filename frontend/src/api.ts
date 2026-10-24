import type {
  ApplicationListResponse,
  ApplicationRead,
  DocumentListResponse,
  DocumentUploadResponse,
  HealthResponse,
  ProcessingJobStatusResponse,
  ReviewSummaryResponse,
  ScrutinyReportResponse,
  Token,
  UserRead,
} from './types';

/** Empty base URL keeps requests same-origin so the Vite dev proxy (and any
 *  reverse proxy in front of the API) forwards them. The browser never talks
 *  to the backend host directly. */
const BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
const TOKEN_KEY = 'aicte.token';

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

/** Turn a FastAPI error body into one readable string. Validation errors
 *  arrive as an array of {loc,msg}; plain errors as {detail}. */
function describe(data: unknown, fallback: string): string {
  if (typeof data === 'string' && data.trim()) return data;
  if (data && typeof data === 'object') {
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const m = (item as { msg?: string }).msg;
          const loc = (item as { loc?: unknown[] }).loc;
          const where = Array.isArray(loc) ? loc.slice(1).join('.') : '';
          return where ? `${where}: ${m ?? 'invalid'}` : m ?? 'invalid';
        })
        .join('; ');
    }
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(
      0,
      'Cannot reach the API. Is the backend running and the proxy configured?',
    );
  }

  if (response.status === 401) {
    setToken(null);
    throw new ApiError(401, 'Session expired or credentials rejected. Please sign in again.');
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      describe(data, `Request failed with HTTP ${response.status}.`),
    );
  }
  return data as T;
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  login: (username: string, password: string) =>
    request<Token>('/api/v1/auth/token', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  me: () => request<UserRead>('/api/v1/auth/me'),

  listApplications: () =>
    request<ApplicationListResponse>('/api/v1/applications?limit=50'),

  getApplication: (id: number) =>
    request<ApplicationRead>(`/api/v1/applications/${id}`),

  createApplication: (applicationType: string, academicYear: string) =>
    request<ApplicationRead>('/api/v1/applications', {
      method: 'POST',
      body: JSON.stringify({
        application_type: applicationType,
        academic_year: academicYear,
      }),
    }),

  listDocuments: (applicationId: number) =>
    request<DocumentListResponse>(`/api/v1/applications/${applicationId}/documents`),

  uploadDocument: (applicationId: number, documentType: string, file: File) => {
    const form = new FormData();
    form.set('document_type', documentType);
    form.set('file', file);
    return request<DocumentUploadResponse>(
      `/api/v1/applications/${applicationId}/documents`,
      { method: 'POST', body: form },
    );
  },

  processing: (applicationId: number, documentId: number, versionId: number) =>
    request<ProcessingJobStatusResponse>(
      `/api/v1/applications/${applicationId}/documents/${documentId}/versions/${versionId}/processing`,
    ),

  validate: (applicationId: number) =>
    request<ScrutinyReportResponse>(
      `/api/v1/applications/${applicationId}/validate`,
      { method: 'POST', body: JSON.stringify({}) },
    ),

  reviewSummary: (applicationId: number) =>
    request<ReviewSummaryResponse>(
      `/api/v1/applications/${applicationId}/review-summary`,
    ),
};
