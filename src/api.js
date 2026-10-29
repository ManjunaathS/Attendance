const API = '/api/v1'
export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API}${path}`, { credentials: 'include', ...options, headers })
  if (response.status === 204) return null
  const type = response.headers.get('content-type') || ''
  const payload = type.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) throw new Error(payload?.detail || payload?.message || `Request failed (${response.status})`)
  return payload
}
export const post = (path, body) => api(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body) })
export const patch = (path, body) => api(path, { method: 'PATCH', body: body instanceof FormData ? body : JSON.stringify(body) })
export const get = (path) => api(path)
