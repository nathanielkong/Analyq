// Hosted builds use the same-origin proxy so session cookies stay first-party.
const DEFAULT_API_BASE_URL = import.meta.env.DEV ? 'http://localhost:8000' : '/api'

// Guest credentials stay in memory and disappear when the page is refreshed.
const guestTokens = new Map<string, string>()
export function rememberGuestChat(id: string, token: string) {
  guestTokens.set(id, token)
}
function guestHeaders(path: string, body?: unknown): Record<string, string> {
  const sessionId = path.match(/\/sessions\/([^/]+)/)?.[1] ??
    (body && typeof body === 'object' && 'session_id' in body ? String(body.session_id) : '')
  const token = guestTokens.get(sessionId || '')
  return token ? { 'X-Guest-Chat': token } : {}
}

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()
const apiBaseUrl = (configuredApiBaseUrl || DEFAULT_API_BASE_URL).replace(
  /\/$/,
  '',
)

export async function apiGet<TResponse>(
  path: string,
  signal?: AbortSignal,
): Promise<TResponse> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: 'include',
    signal,
    headers: guestHeaders(path),
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  return response.json() as Promise<TResponse>
}

export async function apiGetOptional<TResponse>(
  path: string,
): Promise<TResponse | null> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: 'include',
  })

  if (response.status === 401) {
    return null
  }

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  return response.json() as Promise<TResponse>
}

export async function apiPost<TResponse, TBody>(
  path: string,
  body: TBody,
  signal?: AbortSignal,
): Promise<TResponse> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: 'POST',
    signal,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...guestHeaders(path, body),
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  return response.json() as Promise<TResponse>
}

export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: guestHeaders(path),
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }
}

async function getErrorMessage(response: Response) {
  try {
    const errorBody = (await response.json()) as { detail?: unknown }

    if (typeof errorBody.detail === 'string') {
      return errorBody.detail
    }
  } catch {
    // Fall through to the generic status message.
  }

  return `Backend request failed with status ${response.status}`
}
