// Hosted builds use the same-origin proxy so session cookies stay first-party.
const DEFAULT_API_BASE_URL = import.meta.env.DEV ? 'http://localhost:8000' : '/api'

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
