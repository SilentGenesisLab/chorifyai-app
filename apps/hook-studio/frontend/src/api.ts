import type { ClientUsage, Conversation, Session, Task, ToolMode, Usage } from './types'

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

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function list<T>(value: unknown): T[] {
  const body = record(value)
  return (Array.isArray(value) ? value : Array.isArray(body.items) ? body.items : []) as T[]
}

function sessionFrom(value: unknown): Session {
  const outer = record(value)
  const principal = record(outer.principal || outer.client || outer)
  return {
    authenticated: true,
    role: principal.role === 'admin' ? 'admin' : 'client',
    clientName: String(principal.client_name || principal.name || 'Hook Studio'),
    clientId: String(principal.code_id || principal.id || ''),
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
  })
  const contentType = response.headers.get('content-type') || ''
  const text = await response.text()
  let data: unknown = null
  try { data = text && contentType.includes('json') ? JSON.parse(text) : text ? { message: text } : null } catch { data = { message: text } }
  if (!response.ok) {
    const body = record(data)
    const detail = record(body.detail)
    throw new ApiError(
      String(body.message || detail.message || (typeof body.detail === 'string' ? body.detail : '') || '服务暂时不可用，请稍后重试'),
      response.status,
      String(body.request_id || detail.request_id || response.headers.get('x-request-id') || ''),
    )
  }
  return data as T
}

export interface SendMessageInput {
  text: string
  tool: ToolMode
  durationSeconds?: number
  files: File[]
  links: string[]
}

export const api = {
  login: async (accessCode: string) => sessionFrom(await request<unknown>('/auth/login', { method: 'POST', body: JSON.stringify({ access_code: accessCode }) })),
  session: async () => {
    try { return sessionFrom(await request<unknown>('/auth/session')) }
    catch (error) {
      if (error instanceof ApiError && error.status === 404) return sessionFrom(await request<unknown>('/auth/me'))
      throw error
    }
  },
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  bootstrap: () => request<Record<string, unknown>>('/studio/bootstrap'),

  conversations: async () => list<Conversation>(await request<unknown>('/studio/conversations')),
  createConversation: (title = '新对话') => request<Conversation>('/studio/conversations', { method: 'POST', body: JSON.stringify({ title }) }),
  renameConversation: (id: string, title: string) => request<Conversation>(`/studio/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  removeConversation: (id: string) => request<void>(`/studio/conversations/${id}`, { method: 'DELETE' }),
  messages: async (conversationId: string) => list<unknown>(await request<unknown>(`/studio/conversations/${conversationId}/messages`)),
  sendMessage: async (conversationId: string, input: SendMessageInput) => {
    const body = new FormData()
    body.append('text', input.text)
    body.append('tool', input.tool)
    body.append('links', JSON.stringify(input.links))
    if (input.durationSeconds) body.append('duration_seconds', String(input.durationSeconds))
    input.files.forEach(file => body.append('attachments', file))
    return request<Record<string, unknown>>(`/studio/conversations/${conversationId}/messages`, { method: 'POST', body })
  },
  confirmStoryboard: (storyboardId: string, approved: boolean, feedback = '') => request<Record<string, unknown>>(`/studio/storyboards/${storyboardId}/confirm`, { method: 'POST', body: JSON.stringify({ approved, feedback }) }),

  tasks: async (conversationId?: string) => {
    const query = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : ''
    return list<Task>(await request<unknown>(`/studio/tasks${query}`))
  },
  task: (taskId: string) => request<Task>(`/studio/tasks/${taskId}`),
  cancelTask: (taskId: string) => request<Task>(`/studio/tasks/${taskId}/cancel`, { method: 'POST' }),
  batchDownload: (assetIds: string[]) => request<{ download_url: string }>('/studio/assets/batch-download', { method: 'POST', body: JSON.stringify({ asset_ids: assetIds }) }),
  assetDownloadUrl: (assetId: string) => `${API_BASE}/studio/assets/${assetId}/download`,

  admin: () => request<{ clients: ClientUsage[]; usage: Usage; health: string; backup: string; tables: Record<string, number> }>('/admin/dashboard'),
  trainingExportUrl: () => `${API_BASE}/admin/training/export`,
  eventsExportUrl: () => `${API_BASE}/admin/events/export`,
  updateClient: (id: string, patch: { enabled?: boolean; video_limit?: number; image_limit?: number }) => request<ClientUsage>(`/admin/access-codes/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled: patch.enabled, daily_video_limit: patch.video_limit, daily_image_limit: patch.image_limit }) }),
  updateGlobalLimit: (globalVideoDailyLimit: number) => request<Usage>('/admin/settings', { method: 'PATCH', body: JSON.stringify({ global_video_daily_limit: globalVideoDailyLimit }) }),
}
