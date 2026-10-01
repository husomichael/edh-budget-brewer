import type {
  Brew,
  BrewRequest,
  Commander,
  ImportSummary,
} from './types'

/** Thrown for any non-2xx response, carrying the server's structured detail. */
export class RequestError extends Error {
  code?: string
  minimumCents?: number
  fieldErrors?: Record<string, string[]>

  constructor(
    message: string,
    opts: {
      code?: string
      minimumCents?: number
      fieldErrors?: Record<string, string[]>
    } = {},
  ) {
    super(message)
    this.name = 'RequestError'
    this.code = opts.code
    this.minimumCents = opts.minimumCents
    this.fieldErrors = opts.fieldErrors
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (!response.ok) {
    let body: Record<string, unknown> = {}
    try {
      body = await response.json()
    } catch {
      throw new RequestError(`${response.status} ${response.statusText}`)
    }
    // DRF reports validation errors as {field: [messages]} and our own
    // failures as {detail, code, ...}. Handle both shapes.
    if (typeof body.detail === 'string') {
      throw new RequestError(body.detail, {
        code: body.code as string | undefined,
        minimumCents: body.minimum_cents as number | undefined,
      })
    }
    const fieldErrors = body as Record<string, string[]>
    const first = Object.entries(fieldErrors)[0]
    throw new RequestError(
      first ? `${first[0]}: ${first[1]}` : 'Request failed',
      { fieldErrors },
    )
  }

  return response.json() as Promise<T>
}

export function searchCommanders(query: string, signal?: AbortSignal) {
  const qs = new URLSearchParams({ q: query })
  return request<{ results: Commander[] }>(`/api/commanders/?${qs}`, { signal })
}

export function brew(payload: BrewRequest) {
  return request<Brew>('/api/brew/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function saveBrew(payload: BrewRequest & { name?: string }) {
  return request<{ id: number; name: string }>('/api/brew/save/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function importCollection(text: string, replace: boolean) {
  return request<ImportSummary>('/api/collection/import/', {
    method: 'POST',
    body: JSON.stringify({ text, replace }),
  })
}

export function listCollection() {
  return request<{ count: number; results: { id: number; name: string }[] }>(
    '/api/collection/',
  )
}
