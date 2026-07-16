import { useAuthStore } from '@/shared/auth/authStore'

// Backend paths are root-level (/auth, /patients, …); the dev proxy strips
// this prefix. Keeps SPA routes and API paths from colliding.
const API_PREFIX = '/api'

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `Request failed with status ${status}`)
    this.status = status
    this.detail = detail
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  body?: unknown
  formData?: FormData
}

// Single in-flight refresh shared across concurrent 401s.
let refreshPromise: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  const { refreshToken, setAccessToken, clear } = useAuthStore.getState()
  if (!refreshToken) return false
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_PREFIX}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (res) => {
        if (!res.ok) {
          clear()
          return false
        }
        const data = (await res.json()) as { access_token: string }
        setAccessToken(data.access_token)
        return true
      })
      .catch(() => false)
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const doFetch = () => {
    const token = useAuthStore.getState().accessToken
    const headers: Record<string, string> = {}
    if (token) headers.Authorization = `Bearer ${token}`
    let body: BodyInit | undefined
    if (options.formData) {
      body = options.formData
    } else if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json'
      body = JSON.stringify(options.body)
    }
    return fetch(`${API_PREFIX}${path}`, { method: options.method ?? 'GET', headers, body })
  }

  let res = await doFetch()
  if (res.status === 401 && useAuthStore.getState().refreshToken) {
    if (await tryRefresh()) {
      res = await doFetch()
    }
  }

  if (!res.ok) {
    let detail: unknown = null
    try {
      detail = ((await res.json()) as { detail?: unknown }).detail
    } catch {
      // non-JSON error body
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
