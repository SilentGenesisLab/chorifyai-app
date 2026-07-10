export type Mode = 'image' | 'video'
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface Preset {
  id: string
  name: string
  summary: string
  costUnits: number
  accent: string
}

export interface Job {
  id: string
  mode: Mode
  presetId: string
  presetName?: string
  status: JobStatus
  resultUrl?: string
  thumbnailUrl?: string
  queuePosition?: number
  etaSeconds?: number
  createdAt: string
  errorMessage?: string
}

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
  resetAt: string
}

export interface ClientUsage {
  id: string
  name: string
  enabled: boolean
  videoUsed: number
  videoLimit: number
  downloads: number
}
