import type {
  ClientUsage, Conversation, DecisionValue, Session, Task, ToolMode,
  Usage, WorkflowEvent,
} from './types'

const appBase = (import.meta.env.BASE_URL || '/hook-studio/').replace(/\/$/, '')
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') || `${appBase}/api`

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

function decodeEvent(taskId: string, source: MessageEvent<string>, fallbackType = 'message'): WorkflowEvent {
  let payload: Record<string, unknown> = {}
  try { payload = record(source.data ? JSON.parse(source.data) : {}) } catch { payload = { message: source.data } }
  const data = record(payload.data)
  const counts = record(data.counts || data.queue || payload.queue)
  return {
    schema: String(payload.schema || 'hook.event.v1'),
    id: String(payload.id || source.lastEventId || `${taskId}-${Date.now()}`),
    taskId: String(payload.task_id || payload.taskId || taskId),
    type: String(payload.type || payload.event_type || fallbackType),
    state: payload.state as WorkflowEvent['state'],
    publicLabel: String(payload.public_label || payload.publicLabel || payload.label || data.public_label || data.publicLabel || data.label || '任务更新'),
    message: String(payload.message || payload.public_message || payload.detail || data.message || data.public_message || data.detail || '任务仍在处理'),
    occurredAt: String(payload.occurred_at || payload.occurredAt || payload.ts || new Date().toISOString()),
    heartbeatAt: String(payload.heartbeat_at || payload.heartbeatAt || ''),
    indeterminate: Boolean(payload.indeterminate ?? data.indeterminate),
    waitedSeconds: Number(payload.waited_seconds ?? payload.waitedSeconds ?? data.waited_seconds ?? data.waitedSeconds) || undefined,
    inputCount: Number(payload.input_count ?? payload.inputCount ?? data.input_count ?? data.inputCount) || undefined,
    outputCount: Number(payload.output_count ?? payload.outputCount ?? data.output_count ?? data.outputCount) || undefined,
    queue: Object.keys(counts).length ? {
      imageQueued: Number(counts.image_queued ?? counts.imageQueued) || 0,
      imageRunning: Number(counts.image_running ?? counts.imageRunning) || 0,
      imageSucceeded: Number(counts.image_succeeded ?? counts.imageSucceeded) || 0,
      imageFailed: Number(counts.image_failed ?? counts.imageFailed) || 0,
      videoQueued: Number(counts.video_queued ?? counts.videoQueued) || 0,
      videoRunning: Number(counts.video_running ?? counts.videoRunning) || 0,
      videoSucceeded: Number(counts.video_succeeded ?? counts.videoSucceeded) || 0,
      videoFailed: Number(counts.video_failed ?? counts.videoFailed) || 0,
      waitingApproval: Number(counts.waiting_approval ?? counts.waitingApproval) || 0,
      succeeded: Number(counts.succeeded) || 0,
      failed: Number(counts.failed) || 0,
    } : undefined,
    snapshot: payload.snapshot || payload.data,
  }
}

export interface SendMessageInput {
  text: string
  tool: ToolMode
  durationSeconds?: number
  files: File[]
  links: string[]
  idempotencyKey: string
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
    return request<Record<string, unknown>>(`/studio/conversations/${conversationId}/messages`, {
      method: 'POST', body, headers: { 'Idempotency-Key': input.idempotencyKey },
    })
  },
  confirmStoryboard: (storyboardId: string, approved: boolean, feedback = '') => request<Record<string, unknown>>(`/studio/storyboards/${storyboardId}/confirm`, { method: 'POST', body: JSON.stringify({ approved, feedback }) }),

  storyboard: (storyboardId: string) => request<unknown>(`/studio/storyboards/${storyboardId}`),
  patchShot: (storyboardId: string, shotId: string, patch: Record<string, unknown>, expectedVersion: number) => request<unknown>(`/studio/storyboards/${storyboardId}/shots/${shotId}`, {
    method: 'PATCH', body: JSON.stringify({ ...patch, expected_version: expectedVersion }),
  }),
  regeneratePanel: (storyboardId: string, panelId: string, feedback: string, expectedVersion: number) => request<unknown>(`/studio/storyboards/${storyboardId}/panels/${panelId}/regenerate`, {
    method: 'POST', body: JSON.stringify({ feedback, expected_version: expectedVersion }),
  }),
  regenerateShot: (storyboardId: string, shotId: string, feedback: string, expectedVersion: number) => request<unknown>(`/studio/storyboards/${storyboardId}/shots/${shotId}/regenerate`, {
    method: 'POST', body: JSON.stringify({ feedback, expected_version: expectedVersion }),
  }),
  panelCandidates: (storyboardId: string, panelId: string) => request<Record<string, unknown>>(`/studio/storyboards/${storyboardId}/panels/${panelId}/candidates`),
  selectPanelCandidate: (storyboardId: string, panelId: string, candidateId: string, expectedVersion: number) => request<unknown>(`/studio/storyboards/${storyboardId}/panels/${panelId}/candidates/${candidateId}/select`, {
    method: 'POST', body: JSON.stringify({ expected_version: expectedVersion }),
  }),
  decideStoryboard: (storyboardId: string, input: { scope: 'storyboard' | 'shot' | 'panel' | 'animatic'; scopeId: string; decision: DecisionValue; feedback?: string; expectedVersion: number }) => request<unknown>(`/studio/storyboards/${storyboardId}/decisions`, {
    method: 'POST', body: JSON.stringify({
      scope: input.scope, target_id: input.scopeId, scope_id: input.scopeId, decision: input.decision,
      approved: input.decision === 'approved', feedback: input.feedback || '', expected_version: input.expectedVersion,
    }),
  }),
  createAnimatic: (storyboardId: string, expectedVersion: number) => request<unknown>(`/studio/storyboards/${storyboardId}/animatic`, {
    method: 'POST', body: JSON.stringify({ expected_version: expectedVersion }),
  }),
  produceStoryboard: (storyboardId: string, expectedVersion: number) => request<unknown>(`/studio/storyboards/${storyboardId}/produce`, {
    method: 'POST', body: JSON.stringify({ expected_version: expectedVersion }),
  }),
  openTaskEvents: (taskId: string, handlers: { onOpen?: () => void; onEvent: (event: WorkflowEvent) => void; onError?: () => void }) => {
    const source = new EventSource(`${API_BASE}/studio/tasks/${encodeURIComponent(taskId)}/events`, { withCredentials: true })
    source.onopen = () => handlers.onOpen?.()
    source.onerror = () => handlers.onError?.()
    source.onmessage = event => handlers.onEvent(decodeEvent(taskId, event))
    ;['hook.event.v1', 'task.snapshot', 'task.updated', 'skill.updated', 'storyboard.updated', 'panel.updated', 'approval.updated', 'animatic.updated', 'heartbeat'].forEach(type => {
      source.addEventListener(type, event => handlers.onEvent(decodeEvent(taskId, event as MessageEvent<string>, type)))
    })
    return () => source.close()
  },

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
