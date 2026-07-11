import type {
  Animatic, ApprovalDecision, Attachment, AttachmentKind, ChatMessage, Conversation,
  MediaAsset, PanelRole, PanelStatus, QueueSnapshot, SkillStage, SkillStageState, Storyboard,
  StoryboardPanel, StoryboardShot, Task, Usage, WorkflowEvent,
} from './types'

export function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

export function numberValue(value: unknown, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export function arrayValue(value: unknown, key = 'items'): unknown[] {
  const body = record(value)
  return Array.isArray(value) ? value : Array.isArray(body[key]) ? body[key] as unknown[] : []
}

function payload(value: unknown) {
  const body = record(value)
  const raw = body.payload_json ?? body.payload ?? body.contract
  if (typeof raw === 'string') {
    try { return { ...record(JSON.parse(raw)), ...body } } catch { return body }
  }
  return { ...record(raw), ...body }
}

const PRIVATE_LABELS = /\b(?:model|provider|gateway)\s*[:：]?\s*[a-z0-9._-]+/gi

export function publicText(value: unknown, fallback = '') {
  const text = String(value ?? '').trim()
  return (text || fallback).replace(PRIVATE_LABELS, '生成能力')
}

export function normalizeUsage(value: unknown): Usage {
  const body = record(value)
  return {
    globalVideoUsed: numberValue(body.global_video_used ?? body.globalVideoUsed),
    globalVideoLimit: numberValue(body.global_video_limit ?? body.globalVideoLimit, 100),
    clientVideoUsed: numberValue(body.client_video_used ?? body.clientVideoUsed),
    clientVideoLimit: numberValue(body.client_video_limit ?? body.clientVideoLimit, 100),
    imageUsed: numberValue(body.image_used ?? body.client_image_used ?? body.imageUsed),
    imageLimit: numberValue(body.image_limit ?? body.client_image_limit ?? body.imageLimit, 1000),
    resetAt: String(body.reset_at ?? body.resetAt ?? ''),
  }
}

export function normalizeQueues(value: unknown): QueueSnapshot {
  const outer = record(value)
  const body = record(outer.counts || outer.queues || outer.queue || value)
  return {
    imageQueued: numberValue(body.image_queued ?? body.imageQueued),
    imageRunning: numberValue(body.image_running ?? body.imageRunning),
    imageSucceeded: numberValue(body.image_succeeded ?? body.imageSucceeded),
    imageFailed: numberValue(body.image_failed ?? body.imageFailed),
    videoQueued: numberValue(body.video_queued ?? body.videoQueued),
    videoRunning: numberValue(body.video_running ?? body.videoRunning),
    videoSucceeded: numberValue(body.video_succeeded ?? body.videoSucceeded),
    videoFailed: numberValue(body.video_failed ?? body.videoFailed),
    waitingApproval: numberValue(body.waiting_approval ?? body.waitingApproval),
    succeeded: numberValue(body.succeeded), failed: numberValue(body.failed),
  }
}

export function normalizeConversation(value: unknown): Conversation {
  const body = record(value)
  return {
    id: String(body.id || body.conversation_id || ''),
    title: publicText(body.title, '新对话'),
    lastMessage: publicText(body.last_message || body.lastMessage),
    updatedAt: String(body.updated_at || body.updatedAt || body.created_at || new Date().toISOString()),
    createdAt: String(body.created_at || body.createdAt || ''),
    unreadCount: numberValue(body.unread_count || body.unreadCount),
  }
}

export function attachmentKind(mime: string, name: string): AttachmentKind {
  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('audio/')) return 'audio'
  if (mime.startsWith('text/') || /\.(txt|md|csv|json)$/i.test(name)) return 'text'
  if (/\.(pdf|docx?|xlsx?|pptx?)$/i.test(name)) return 'document'
  return 'file'
}

export function normalizeAttachment(value: unknown): Attachment {
  const body = record(value)
  const mime = String(body.mime_type || body.mimeType || '')
  const name = String(body.name || body.filename || '附件')
  return {
    id: String(body.id || body.attachment_id || `${name}-${body.url || ''}`),
    name,
    kind: (body.kind || attachmentKind(mime, name)) as AttachmentKind,
    mimeType: mime,
    size: numberValue(body.size || body.bytes),
    url: String(body.url || ''),
    thumbnailUrl: String(body.thumbnail_url || body.thumbnailUrl || ''),
    extractedText: String(body.extracted_text || body.extractedText || ''),
    status: (body.status || 'ready') as Attachment['status'],
  }
}

export function normalizeAsset(value: unknown): MediaAsset {
  const body = payload(value)
  const rawType = String(body.type || body.media_type || body.mode || body.kind || 'image')
  const role = String(body.role || body.asset_role || body.scope || '')
  return {
    id: String(body.id || body.asset_id || body.job_id || body.url || ''),
    type: (rawType === 'video' || rawType === 'audio' || rawType === 'document' ? rawType : 'image'),
    name: publicText(body.name || body.filename, rawType === 'video' ? '生成视频' : '生成图片'),
    url: String(body.url || body.result_url || body.media_url || ''),
    thumbnailUrl: String(body.thumbnail_url || body.thumbnailUrl || ''),
    durationSeconds: numberValue(body.duration_seconds || body.durationSeconds) || undefined,
    width: numberValue(body.width) || undefined,
    height: numberValue(body.height) || undefined,
    jobId: String(body.job_id || body.jobId || ''),
    shotId: String(body.shot_id || body.shotId || ''),
    panelId: String(body.panel_id || body.panelId || ''),
    role: (['upload', 'research', 'annotated', 'clean', 'animatic', 'final'].includes(role) ? role : undefined) as MediaAsset['role'],
    approved: Boolean(body.approved),
    createdAt: String(body.created_at || body.createdAt || ''),
  }
}

function normalizeDecision(value: unknown, scope: ApprovalDecision['scope'], scopeId: string, version: number): ApprovalDecision | undefined {
  if (value === true) return { id: `${scopeId}-approval`, scope, scopeId, decision: 'approved', version, createdAt: '' }
  const body = record(value)
  const raw = String(body.decision || body.status || '')
  if (!body.id && !raw) return undefined
  return {
    id: String(body.id || `${scopeId}-approval-v${version}`), scope, scopeId,
    decision: raw === 'approved' || body.approved === true ? 'approved' : 'revision_required',
    feedback: publicText(body.feedback || body.note), version: numberValue(body.version, version),
    createdAt: String(body.created_at || body.createdAt || ''),
  }
}

function normalizePanel(value: unknown, shotId: string, index: number): StoryboardPanel {
  const body = payload(value)
  const id = String(body.id || body.panel_id || `${shotId}-panel-${index + 1}`)
  const version = numberValue(body.version || body.revision, 1)
  const selected = record(body.selected_candidate || body.selected_asset || body.clean_asset)
  const annotated = record(body.annotated_asset || body.annotated)
  const cleanUrl = String(body.clean_url || body.clean_frame_url || selected.url || body.image_url || '')
  const annotatedUrl = String(body.annotated_url || body.storyboard_url || annotated.url || body.thumbnail_url || '')
  const rawRole = String(body.role || body.panel_role || (index === 0 ? 'start' : 'action'))
  const role = (['start', 'action', 'end', 'proof', 'transition', 'reference'].includes(rawRole) ? rawRole : 'action') as PanelRole
  const rawStatus = String(body.status || 'draft')
  const status = (['draft', 'generating', 'review', 'approved', 'revision_required', 'locked', 'failed'].includes(rawStatus) ? rawStatus : 'draft') as PanelStatus
  return {
    id, shotId, order: numberValue(body.order || body.ordinal, index + 1), role,
    title: publicText(body.title || body.label, `画格 ${index + 1}`),
    description: publicText(body.description || body.action || body.note, '等待补充该画格的动作说明'),
    moment: publicText(body.moment || body.action_endpoint, role === 'start' ? '动作起点' : role === 'end' ? '动作终点' : '关键动作'),
    status, version, required: body.required !== false,
    annotatedUrl, cleanUrl, thumbnailUrl: String(body.thumbnail_url || body.thumbnailUrl || annotatedUrl || cleanUrl),
    selectedCandidateId: String(body.selected_candidate_id || selected.id || ''),
    sendToProvider: Boolean(body.send_to_provider),
    approval: normalizeDecision(body.approval || body.decision || body.approved, 'panel', id, version),
    feedback: publicText(body.feedback),
  }
}

function normalizeShot(value: unknown, index: number, loosePanels: unknown[]): StoryboardShot {
  const body = payload(value)
  const id = String(body.id || body.shot_id || `shot-${index + 1}`)
  const version = numberValue(body.version || body.revision, 1)
  const nestedPanels = arrayValue(body.panels)
  const matchingPanels = nestedPanels.length ? nestedPanels : loosePanels.filter(panel => String(record(panel).shot_id || record(panel).shotId) === id)
  const imageUrl = String(body.image_url || body.storyboard_url || body.thumbnail_url || '')
  const panels = (matchingPanels.length ? matchingPanels : imageUrl ? [{ id: `${id}-panel-1`, shot_id: id, annotated_url: imageUrl, clean_url: body.clean_frame_url || imageUrl, required: true }] : [])
    .map((panel, panelIndex) => normalizePanel(panel, id, panelIndex))
    .sort((a, b) => a.order - b.order)
  const startSeconds = numberValue(body.start_seconds || body.start_time || body.in_seconds)
  const durationSeconds = numberValue(body.duration_seconds || body.duration, 4)
  const rawStatus = String(body.status || 'draft')
  const status = (['draft', 'drawing', 'review', 'approved', 'revision_required', 'locked', 'producing', 'qc', 'completed', 'failed'].includes(rawStatus) ? rawStatus : 'draft') as StoryboardShot['status']
  return {
    id, order: numberValue(body.order || body.ordinal || body.index, index + 1),
    code: String(body.code || body.shot_code || `S${String(index + 1).padStart(2, '0')}`),
    title: publicText(body.title || body.label, `镜头 ${index + 1}`),
    description: publicText(body.description || body.visual || body.visual_description || body.prompt, '等待补充完整画面描述'),
    durationSeconds, startSeconds, endSeconds: numberValue(body.end_seconds, startSeconds + durationSeconds),
    storyFunction: publicText(body.story_function || body.purpose, '待明确镜头功能'),
    subject: publicText(body.subject, '待明确主体'), scene: publicText(body.scene || body.environment, '待明确场景'),
    composition: publicText(body.composition, '待明确前景、中景、背景和视觉重心'),
    actionStart: publicText(body.action_start || body.start_action, '待明确动作起点'),
    actionEnd: publicText(body.action_end || body.action_result || body.end_action || body.action_endpoint, '待明确动作终点'),
    shotSize: publicText(body.shot_size || body.framing, '待定景别'),
    cameraAngle: publicText(body.camera_angle || body.angle, '待定机位'),
    lens: publicText(body.lens || body.lens_feeling, '自然透视'),
    cameraMove: publicText(body.camera_move || body.camera_movement, '固定机位'),
    audio: publicText(body.audio || body.sound || body.voiceover, '待确认声音'),
    transition: publicText(body.transition || body.edit_relation, '直接切换'),
    continuity: publicText(body.continuity || body.continuity_notes || arrayValue(body.stable_truth).join('；'), '保持产品、人物与场景连续'),
    references: arrayValue(body.references || body.reference_manifest).map(value => publicText(record(value).label || record(value).role || value)).filter(Boolean),
    firstFailureCue: publicText(body.first_failure_cue || body.risk, '主体或动作偏离即回炉'),
    status, version, panels,
    selectedCleanFrameUrl: String(body.selected_clean_frame_url || body.clean_frame_url || panels.find(panel => panel.cleanUrl)?.cleanUrl || ''),
    imageUrl, approval: normalizeDecision(body.approval || body.decision || body.approved, 'shot', id, version),
  }
}

function normalizeSkillStage(value: unknown, index: number): SkillStage {
  const body = payload(value)
  const rawState = String(body.state || body.status || 'pending')
  const state = (['pending', 'queued', 'running', 'waiting', 'succeeded', 'failed', 'blocked'].includes(rawState) ? rawState : 'pending') as SkillStageState
  return {
    id: String(body.id || body.run_id || `stage-${index + 1}`),
    label: publicText(body.public_label || body.label || body.name, `能力步骤 ${index + 1}`), state,
    startedAt: String(body.started_at || body.startedAt || ''), finishedAt: String(body.finished_at || body.finishedAt || ''),
    latencyMs: numberValue(body.latency_ms || body.latencyMs) || undefined,
    inputCount: numberValue(body.input_count || body.inputCount) || undefined,
    outputCount: numberValue(body.output_count || body.outputCount) || undefined,
    retryCount: numberValue(body.retry_count || body.retryCount) || undefined,
    publicMessage: publicText(body.public_message || body.message), blocker: publicText(body.blocker || body.blocking_reason),
  }
}

function normalizeAnimatic(value: unknown, totalDuration: number): Animatic | undefined {
  const body = record(value)
  if (!body.id && !body.url && !body.status) return undefined
  const status = String(body.status || (body.confirmed ? 'confirmed' : 'review')) as Animatic['status']
  return {
    id: String(body.id || body.animatic_id || 'animatic'), status,
    url: String(body.url || body.result_url || ''), durationSeconds: numberValue(body.duration_seconds || body.duration, totalDuration),
    version: numberValue(body.version, 1), confirmed: Boolean(body.confirmed || status === 'confirmed'),
    createdAt: String(body.created_at || body.createdAt || ''),
  }
}

export function normalizeStoryboard(value: unknown): Storyboard | undefined {
  const outer = record(value)
  const body = payload(outer.storyboard || outer.snapshot || value)
  if (!body.id && !body.storyboard_id) return undefined
  const loosePanels = arrayValue(outer.panels).length ? arrayValue(outer.panels) : arrayValue(body.panels)
  const shots = arrayValue(body.shots).map((shot, index) => normalizeShot(shot, index, loosePanels)).sort((a, b) => a.order - b.order)
  let timelineCursor = 0
  shots.forEach((shot, index) => {
    if (index > 0 && shot.startSeconds === 0) {
      shot.startSeconds = timelineCursor
      shot.endSeconds = timelineCursor + shot.durationSeconds
    }
    timelineCursor = Math.max(timelineCursor, shot.endSeconds)
  })
  const totalDuration = numberValue(body.total_duration_seconds || body.totalDurationSeconds, shots.reduce((sum, shot) => sum + shot.durationSeconds, 0))
  const rawCoverage = record(body.coverage || outer.coverage)
  const requiredPanels = shots.flatMap(shot => shot.panels.filter(panel => panel.required))
  const approvedShots = shots.filter(shot => shot.approval?.decision === 'approved' || ['approved', 'locked', 'producing', 'qc', 'completed'].includes(shot.status)).length
  const coverage = {
    shotTotal: numberValue(rawCoverage.shot_total ?? rawCoverage.shots_total ?? rawCoverage.shotTotal, shots.length),
    shotReady: numberValue(rawCoverage.shot_ready ?? rawCoverage.shotReady, shots.filter(shot => shot.description && shot.panels.length).length),
    panelRequired: numberValue(rawCoverage.panel_required ?? rawCoverage.panels_total ?? rawCoverage.panelRequired, requiredPanels.length),
    panelReady: numberValue(rawCoverage.panel_ready ?? rawCoverage.panels_total ?? rawCoverage.panelReady, requiredPanels.filter(panel => panel.annotatedUrl || panel.thumbnailUrl || panel.status === 'approved').length),
    cleanReady: numberValue(rawCoverage.clean_ready ?? rawCoverage.clean_frames ?? rawCoverage.cleanReady, shots.filter(shot => Boolean(shot.selectedCleanFrameUrl)).length),
    approvedShots: numberValue(rawCoverage.approved_shots ?? rawCoverage.shots_approved ?? rawCoverage.approvedShots, approvedShots),
  }
  const animatic = normalizeAnimatic(body.animatic || outer.animatic, totalDuration)
  const rawGuard = record(body.guard || body.production_guard || outer.guard)
  const derivedBlockers: string[] = []
  if (!shots.length) derivedBlockers.push('等待镜头拆解')
  if (coverage.shotReady < coverage.shotTotal) derivedBlockers.push('镜头描述尚未补齐')
  if (coverage.panelReady < coverage.panelRequired || coverage.panelRequired < coverage.shotTotal) derivedBlockers.push('故事板画格尚未覆盖全部镜头')
  if (coverage.cleanReady < coverage.shotTotal) derivedBlockers.push('干净参考帧尚未覆盖全部镜头')
  if (coverage.approvedShots < coverage.shotTotal) derivedBlockers.push('仍有镜头等待批准')
  if (body.board_approved === false) derivedBlockers.push('整板尚未批准')
  if (!animatic?.confirmed) derivedBlockers.push('动态预演尚未确认')
  const blockers = arrayValue(rawGuard.blockers).map(value => publicText(value)).filter(Boolean)
  const guard = {
    canProduce: Boolean(rawGuard.can_produce ?? rawGuard.canProduce ?? body.can_produce ?? (derivedBlockers.length === 0)),
    blockers: blockers.length ? blockers : derivedBlockers,
  }
  const revision = numberValue(body.revision || body.version, 1)
  const rawStatus = String(body.status || 'draft')
  return {
    id: String(body.id || body.storyboard_id), taskId: String(body.task_id || body.taskId || outer.task_id || ''),
    conversationId: String(body.conversation_id || body.conversationId || ''),
    version: /^v/i.test(String(body.version)) ? String(body.version) : `v${revision}`,
    revision, status: rawStatus as Storyboard['status'], summary: publicText(body.summary), brief: publicText(body.brief || body.requirement_summary),
    totalDurationSeconds: totalDuration, estimatedVideoUnits: numberValue(body.estimated_video_units || body.estimatedVideoUnits, shots.length),
    shots, coverage, guard,
    skillStages: arrayValue(body.skill_stages || body.skill_runs || outer.skill_stages || outer.skill_runs).map(normalizeSkillStage),
    animatic, updatedAt: String(body.updated_at || body.updatedAt || ''),
  }
}

export function normalizeMessage(value: unknown, conversationId: string): ChatMessage {
  const body = record(value)
  const storyboard = normalizeStoryboard(body.storyboard)
  const assets = arrayValue(body.assets).map(normalizeAsset).filter(asset => asset.url)
  const role = body.role === 'user' || body.role === 'system' ? body.role : 'assistant'
  return {
    id: String(body.id || body.message_id || crypto.randomUUID()),
    conversationId: String(body.conversation_id || body.conversationId || conversationId), role,
    kind: (body.kind || (storyboard ? 'storyboard' : assets.length ? 'media' : 'text')) as ChatMessage['kind'],
    text: role === 'user' ? String(body.text || body.content || body.message || '') : publicText(body.text || body.content || body.message),
    attachments: arrayValue(body.attachments).map(normalizeAttachment), assets, storyboard,
    taskId: String(body.task_id || body.taskId || ''), createdAt: String(body.created_at || body.createdAt || new Date().toISOString()),
  }
}

export function normalizeTask(value: unknown): Task {
  const body = payload(value)
  return {
    id: String(body.id || body.task_id || ''), conversationId: String(body.conversation_id || body.conversationId || ''),
    storyboardId: String(body.storyboard_id || body.storyboardId || ''), title: publicText(body.title || body.name, '生产任务'),
    tool: (body.tool || body.mode || 'create_video') as Task['tool'], status: (body.status || 'queued') as Task['status'],
    stage: publicText(body.public_stage || body.stage || body.current_stage, '排队中'),
    progress: Math.min(100, Math.max(0, numberValue(body.progress || body.progress_percent))),
    queuePosition: numberValue(body.queue_position || body.queuePosition) || undefined,
    etaSeconds: numberValue(body.eta_seconds || body.etaSeconds) || undefined,
    waitingSeconds: numberValue(body.waiting_seconds || body.waitingSeconds) || undefined,
    heartbeatAt: String(body.heartbeat_at || body.heartbeatAt || ''), errorMessage: publicText(body.error_message || body.errorMessage),
    assetIds: arrayValue(body.asset_ids).map(String), createdAt: String(body.created_at || body.createdAt || new Date().toISOString()),
    updatedAt: String(body.updated_at || body.updatedAt || ''),
  }
}

export function normalizeWorkflowEvent(value: WorkflowEvent): WorkflowEvent {
  return { ...value, publicLabel: publicText(value.publicLabel, '任务更新'), message: publicText(value.message, '任务仍在处理') }
}
