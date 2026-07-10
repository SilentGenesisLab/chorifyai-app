export type Mode = 'image' | 'video'
export type JobStatus = 'queued' | 'running' | 'waiting_confirmation' | 'succeeded' | 'failed' | 'cancelled'
export type ToolMode = 'create_video' | 'create_image' | 'reference_remix' | 'batch_production' | 'reverse_analysis' | 'replace_content'
export type AttachmentKind = 'image' | 'video' | 'audio' | 'document' | 'text' | 'link' | 'file'
export type MessageKind = 'text' | 'question' | 'status' | 'storyboard' | 'media' | 'error'

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
  createdAt?: string
}

export interface StoryboardShot {
  id: string
  order: number
  title: string
  description: string
  durationSeconds: number
  imageUrl?: string
  status?: 'draft' | 'approved' | 'revision_required'
}

export interface Storyboard {
  id: string
  version: string
  status: 'pending' | 'confirmed' | 'revision_required'
  summary?: string
  totalDurationSeconds: number
  estimatedVideoUnits: number
  shots: StoryboardShot[]
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
  title: string
  tool: ToolMode
  status: JobStatus
  stage: string
  progress: number
  queuePosition?: number
  etaSeconds?: number
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
