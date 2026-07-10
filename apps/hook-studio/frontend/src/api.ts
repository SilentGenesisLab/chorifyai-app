import type { ClientUsage, Job, Mode, Session, Usage } from './types'

const appBase = (import.meta.env.BASE_URL || '/hook-studio/').replace(/\/$/, '')
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') || `${appBase}/api`

export class ApiError extends Error {
  requestId?: string
  status: number
  constructor(message: string, status: number, requestId?: string) {
    super(message)
    this.status = status
    this.requestId = requestId
  }
}

function record(value: unknown): Record<string, unknown> { return value && typeof value === 'object' ? value as Record<string, unknown> : {} }
function sessionFrom(value: unknown): Session {
  const outer = record(value); const p = record(outer.principal || outer.client || outer)
  return { authenticated: true, role: p.role === 'admin' ? 'admin' : 'client', clientName: String(p.client_name || p.name || 'Hook Studio'), clientId: String(p.code_id || p.id || '') }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: { ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...init?.headers },
  })
  const text = await response.text()
  let data: unknown = null
  try { data = text ? JSON.parse(text) : null } catch { data = { message: text } }
  if (!response.ok) {
    const body = (data || {}) as Record<string, unknown>
    const detail = record(body.detail)
    throw new ApiError(String(body.message || detail.message || (typeof body.detail === 'string' ? body.detail : '') || '服务暂时不可用，请稍后重试'), response.status, String(body.request_id || detail.request_id || response.headers.get('x-request-id') || ''))
  }
  return data as T
}

export const api = {
  login: async (accessCode: string) => sessionFrom(await request<unknown>('/auth/login', { method: 'POST', body: JSON.stringify({ access_code: accessCode }) })),
  session: async () => {
    try { return sessionFrom(await request<unknown>('/auth/session')) }
    catch (error) { if (error instanceof ApiError && error.status === 404) return sessionFrom(await request<unknown>('/auth/me')); throw error }
  },
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  bootstrap: () => request<Record<string, unknown>>('/studio/bootstrap'),
  jobs: async () => { const data = await request<unknown>('/studio/jobs'); const r = record(data); return (Array.isArray(data) ? data : Array.isArray(r.items) ? r.items : []) as Job[] },
  generate: (mode: Mode, presetId: string, prompt: string, reference?: File) => {
    const body = new FormData()
    body.append('mode', mode); body.append('preset_id', presetId); body.append('prompt_user', prompt)
    if (mode === 'video') body.append('duration', '5')
    if (reference) body.append('reference', reference)
    return request<Record<string, unknown>>('/studio/jobs', { method: 'POST', body }).then(data => (record(data).job || data) as Job)
  },
  action: async (jobId: string, action: 'preview' | 'regenerate') => { const data = await request<Record<string, unknown>>(`/studio/jobs/${jobId}/${action}`, { method: 'POST' }); return (record(data).job || data) as Job | { url?: string } },
  remove: (jobId: string) => request<void>(`/studio/jobs/${jobId}`, { method: 'DELETE' }),
  downloadUrl: (jobId: string) => `${API_BASE}/studio/jobs/${jobId}/download`,
  admin: () => request<{ clients: ClientUsage[]; usage: Usage; health: string; backup: string }>('/admin/dashboard'),
  updateClient: (id: string, patch: { enabled?: boolean; video_limit?: number }) => request<ClientUsage>(`/admin/access-codes/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled: patch.enabled, daily_video_limit: patch.video_limit }) }),
  updateGlobalLimit: (global_video_daily_limit: number) => request<Usage>('/admin/settings', { method: 'PATCH', body: JSON.stringify({ global_video_daily_limit }) }),
}
