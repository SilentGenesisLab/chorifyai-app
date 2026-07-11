export type Mode = 'image' | 'video'
export type JobStatus = 'queued' | 'running' | 'waiting_confirmation' | 'succeeded' | 'failed' | 'cancelled'
export type ToolMode = 'create_video' | 'create_image' | 'edit_image' | 'reference_remix' | 'batch_production' | 'reverse_analysis' | 'replace_content'
export type AttachmentKind = 'image' | 'video' | 'audio' | 'document' | 'text' | 'link' | 'file'
export type MessageKind = 'text' | 'question' | 'status' | 'storyboard' | 'media' | 'error' | 'requirement' | 'coverage' | 'approval' | 'delivery'

export type StoryboardStatus = 'draft' | 'planning' | 'review' | 'pending' | 'revision_required' | 'confirmed' | 'approved' | 'frozen' | 'producing' | 'completed'
export type ShotStatus = 'draft' | 'drawing' | 'review' | 'approved' | 'revision_required' | 'locked' | 'producing' | 'qc' | 'completed' | 'failed'
export type PanelStatus = 'draft' | 'generating' | 'review' | 'approved' | 'revision_required' | 'locked' | 'failed'
export type PanelRole = 'start' | 'action' | 'end' | 'proof' | 'transition' | 'reference'
export type DecisionValue = 'approved' | 'revision_required'
export type SkillStageState = 'pending' | 'queued' | 'running' | 'waiting' | 'succeeded' | 'failed' | 'blocked'
export type WorkspaceView = 'shot_table' | 'filmstrip' | 'animatic'
export type InspectorView = 'assets' | 'preview' | 'finals'

export interface Session {
  authenticated: boolean
  role: 'client' | 'admin'
  clientName: string
  clientId?: string
}

export interface Usage {
  globalVideoUsed: number
  globalVideoLimit: number
  clientVideoUsed: number
  clientVideoLimit: number
  imageUsed: number
  imageLimit: number
  resetAt: string
}

export interface Conversation {
  id: string
  title: string
  lastMessage?: string
  updatedAt: string
  createdAt?: string
  unreadCount?: number
}

export interface Attachment {
  id: string
  name: string
  kind: AttachmentKind
  mimeType?: string
  size?: number
  url?: string
  thumbnailUrl?: string
  extractedText?: string
  status?: 'uploading' | 'ready' | 'failed'
}

export interface MediaAsset {
  id: string
  type: Mode | 'audio' | 'document'
  name: string
  url: string
  thumbnailUrl?: string
  durationSeconds?: number
  width?: number
  height?: number
  jobId?: string
  shotId?: string
  panelId?: string
  role?: 'upload' | 'research' | 'annotated' | 'clean' | 'animatic' | 'final'
  approved?: boolean
  createdAt?: string
}

export interface StoryboardPanel {
  id: string
  shotId: string
  order: number
  role: PanelRole
  title: string
  description: string
  moment: string
  status: PanelStatus
  version: number
  required: boolean
  annotatedUrl?: string
  cleanUrl?: string
  thumbnailUrl?: string
  selectedCandidateId?: string
  sendToProvider: boolean
  approval?: ApprovalDecision
  feedback?: string
}

export interface StoryboardShot {
  id: string
  order: number
  code: string
  title: string
  description: string
  durationSeconds: number
  startSeconds: number
  endSeconds: number
  storyFunction: string
  subject: string
  scene: string
  composition: string
  actionStart: string
  actionEnd: string
  shotSize: string
  cameraAngle: string
  lens: string
  cameraMove: string
  audio: string
  transition: string
  continuity: string
  references: string[]
  firstFailureCue: string
  status: ShotStatus
  version: number
  panels: StoryboardPanel[]
  selectedCleanFrameUrl?: string
  imageUrl?: string
  approval?: ApprovalDecision
}

export interface StoryboardCoverage {
  shotTotal: number
  shotReady: number
  panelRequired: number
  panelReady: number
  cleanReady: number
  approvedShots: number
}

export interface ProductionGuard {
  canProduce: boolean
  blockers: string[]
}

export interface ApprovalDecision {
  id: string
  scope: 'storyboard' | 'shot' | 'panel' | 'animatic'
  scopeId: string
  decision: DecisionValue
  feedback?: string
  version: number
  createdAt: string
}

export interface SkillStage {
  id: string
  label: string
  state: SkillStageState
  startedAt?: string
  finishedAt?: string
  latencyMs?: number
  inputCount?: number
  outputCount?: number
  retryCount?: number
  publicMessage?: string
  blocker?: string
}

export interface Animatic {
  id: string
  status: 'missing' | 'generating' | 'review' | 'confirmed' | 'failed'
  url?: string
  durationSeconds: number
  version: number
  confirmed: boolean
  createdAt?: string
}

export interface Storyboard {
  id: string
  taskId?: string
  conversationId?: string
  version: string
  revision: number
  status: StoryboardStatus
  summary?: string
  brief?: string
  totalDurationSeconds: number
  estimatedVideoUnits: number
  shots: StoryboardShot[]
  coverage: StoryboardCoverage
  guard: ProductionGuard
  skillStages: SkillStage[]
  animatic?: Animatic
  updatedAt?: string
}

export interface WorkflowEvent {
  schema: 'hook.event.v1' | string
  id: string
  taskId: string
  type: string
  state?: SkillStageState | JobStatus
  publicLabel: string
  message: string
  occurredAt: string
  heartbeatAt?: string
  indeterminate?: boolean
  waitedSeconds?: number
  inputCount?: number
  outputCount?: number
  queue?: QueueSnapshot
  snapshot?: unknown
}

export interface QueueSnapshot {
  imageQueued: number
  imageRunning: number
  imageSucceeded: number
  imageFailed: number
  videoQueued: number
  videoRunning: number
  videoSucceeded: number
  videoFailed: number
  waitingApproval: number
  succeeded: number
  failed: number
}

export interface ChatMessage {
  id: string
  conversationId: string
  role: 'user' | 'assistant' | 'system'
  kind: MessageKind
  text: string
  attachments: Attachment[]
  assets: MediaAsset[]
  storyboard?: Storyboard
  taskId?: string
  createdAt: string
}

export interface Task {
  id: string
  conversationId: string
  storyboardId?: string
  title: string
  tool: ToolMode
  status: JobStatus
  stage: string
  progress: number
  queuePosition?: number
  etaSeconds?: number
  waitingSeconds?: number
  heartbeatAt?: string
  errorMessage?: string
  assetIds: string[]
  createdAt: string
  updatedAt?: string
}

export interface ClientUsage {
  id: string
  name: string
  enabled: boolean
  videoUsed: number
  videoLimit: number
  imageUsed?: number
  imageLimit?: number
  downloads: number
}

export interface Job {
  id: string
  mode: Mode
  status: JobStatus
  resultUrl?: string
  thumbnailUrl?: string
  queuePosition?: number
  etaSeconds?: number
  createdAt: string
  errorMessage?: string
}
