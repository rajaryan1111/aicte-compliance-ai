// Transport module for consistency API
// Base-URL bootstrap, JSON fetch, error mapping and shared request pipeline
// Injectable for Node regression tests

export interface TransportOptions {
  baseUrl: string;
  basePath: string;
}

export function buildBaseUrl(options: TransportOptions): string {
  return options.baseUrl + options.basePath;
}

export async function transportFetch(input: RequestInfo, init: RequestInit = {}, options: TransportOptions = { baseUrl: "", basePath: "" }): Promise<Response> {
  const url = new URL(input as string);
  const base = buildBaseUrl(options);
  if (base) {
    url.pathname = base + url.pathname;
  }
  return fetch(url, init);
}

export function mapError(error: unknown): { message: string; status: number } {
  if (error instanceof Response) {
    const status = error.status;
    return { message: error.statusText || "Request failed", status };
  }
  return { message: error instanceof Error ? error.message : "Unknown error", status: 0 };
}
