import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Check, CheckSquare2, ChevronDown, CircleAlert, Clock3, Copy, Download,
  FileText, Film, Gauge, Image as ImageIcon, Layers3, Link as LinkIcon,
  LoaderCircle, LogOut, Menu, MoreHorizontal, Paperclip, PanelRightOpen,
  Play, Plus, RefreshCw, ScanSearch, Search, Send, Settings2, ShieldCheck,
  Square, Trash2, Users, Video, Volume2, X,
} from 'lucide-react'
import { ApiError, api } from './api'
import Login from './components/Login'
import type {
  Attachment, AttachmentKind, ChatMessage, ClientUsage, Conversation, MediaAsset,
  Session, Storyboard, StoryboardShot, Task, ToolMode, Usage,
} from './types'

const EMPTY_USAGE: Usage = {
  globalVideoUsed: 0, globalVideoLimit: 100, clientVideoUsed: 0, clientVideoLimit: 100,
  imageUsed: 0, imageLimit: 1000, resetAt: '',
}

const TOOLS: Array<{ id: ToolMode; label: string; short: string; icon: typeof Video; needsDuration: boolean }> = [
  { id: 'create_video', label: '视频生产', short: '视频', icon: Video, needsDuration: true },
  { id: 'create_image', label: '图片生产', short: '图片', icon: ImageIcon, needsDuration: false },
  { id: 'reference_remix', label: '参控复刻', short: '复刻', icon: Copy, needsDuration: true },
  { id: 'batch_production', label: '批量生产', short: '批量', icon: Layers3, needsDuration: true },
  { id: 'reverse_analysis', label: '逆向分析', short: '逆向', icon: ScanSearch, needsDuration: false },
  { id: 'replace_content', label: '定向替换', short: '替换', icon: RefreshCw, needsDuration: true },
]

const TASK_STAGES = ['解析素材', '逆向分析', '分镜规划', '等待确认', '镜头生成', '后期合成', '技术质检']

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function n(value: unknown, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function list(value: unknown, key = 'items'): unknown[] {
  const body = asRecord(value)
  return Array.isArray(value) ? value : Array.isArray(body[key]) ? body[key] as unknown[] : []
}

function normalizeUsage(value: unknown): Usage {
  const body = asRecord(value)
  return {
    globalVideoUsed: n(body.global_video_used ?? body.globalVideoUsed),
    globalVideoLimit: n(body.global_video_limit ?? body.globalVideoLimit, 100),
    clientVideoUsed: n(body.client_video_used ?? body.clientVideoUsed),
    clientVideoLimit: n(body.client_video_limit ?? body.clientVideoLimit, 100),
    imageUsed: n(body.image_used ?? body.client_image_used ?? body.imageUsed),
    imageLimit: n(body.image_limit ?? body.client_image_limit ?? body.imageLimit, 1000),
    resetAt: String(body.reset_at ?? body.resetAt ?? ''),
  }
}

function normalizeConversation(value: unknown): Conversation {
  const body = asRecord(value)
  return {
    id: String(body.id || body.conversation_id || ''),
    title: String(body.title || '新对话'),
    lastMessage: String(body.last_message || body.lastMessage || ''),
    updatedAt: String(body.updated_at || body.updatedAt || body.created_at || new Date().toISOString()),
    createdAt: String(body.created_at || body.createdAt || ''),
    unreadCount: n(body.unread_count || body.unreadCount),
  }
}

function attachmentKind(mime: string, name: string): AttachmentKind {
  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('audio/')) return 'audio'
  if (mime.startsWith('text/') || /\.(txt|md|csv|json)$/i.test(name)) return 'text'
  if (/\.(pdf|docx?|xlsx?|pptx?)$/i.test(name)) return 'document'
  return 'file'
}

function normalizeAttachment(value: unknown): Attachment {
  const body = asRecord(value)
  const mime = String(body.mime_type || body.mimeType || '')
  const name = String(body.name || body.filename || '附件')
  return {
    id: String(body.id || body.attachment_id || `${name}-${body.url || ''}`),
    name,
    kind: (body.kind || attachmentKind(mime, name)) as AttachmentKind,
    mimeType: mime,
    size: n(body.size || body.bytes),
    url: String(body.url || ''),
    thumbnailUrl: String(body.thumbnail_url || body.thumbnailUrl || ''),
    extractedText: String(body.extracted_text || body.extractedText || ''),
    status: (body.status || 'ready') as Attachment['status'],
  }
}

function normalizeAsset(value: unknown): MediaAsset {
  const body = asRecord(value)
  const rawType = String(body.type || body.media_type || body.mode || 'image')
  return {
    id: String(body.id || body.asset_id || body.job_id || body.url || ''),
    type: (rawType === 'video' || rawType === 'audio' || rawType === 'document' ? rawType : 'image'),
    name: String(body.name || body.filename || (rawType === 'video' ? '生成视频' : '生成图片')),
    url: String(body.url || body.result_url || body.media_url || ''),
    thumbnailUrl: String(body.thumbnail_url || body.thumbnailUrl || ''),
    durationSeconds: n(body.duration_seconds || body.durationSeconds) || undefined,
    width: n(body.width) || undefined,
    height: n(body.height) || undefined,
    jobId: String(body.job_id || body.jobId || ''),
    createdAt: String(body.created_at || body.createdAt || ''),
  }
}

function normalizeStoryboard(value: unknown): Storyboard | undefined {
  const body = asRecord(value)
  if (!body.id && !body.storyboard_id) return undefined
  const shots: StoryboardShot[] = list(body.shots).map((shot, index) => {
    const item = asRecord(shot)
    return {
      id: String(item.id || item.shot_id || `shot-${index + 1}`),
      order: n(item.order || item.index, index + 1),
      title: String(item.title || `镜头 ${index + 1}`),
      description: String(item.description || item.prompt || ''),
      durationSeconds: n(item.duration_seconds || item.duration, 4),
      imageUrl: String(item.image_url || item.storyboard_url || item.thumbnail_url || ''),
      status: (item.status || 'draft') as StoryboardShot['status'],
    }
  })
  return {
    id: String(body.id || body.storyboard_id),
    version: String(body.version || 'v1'),
    status: (body.status || 'pending') as Storyboard['status'],
    summary: String(body.summary || ''),
    totalDurationSeconds: n(body.total_duration_seconds || body.totalDurationSeconds, shots.reduce((sum, shot) => sum + shot.durationSeconds, 0)),
    estimatedVideoUnits: n(body.estimated_video_units || body.estimatedVideoUnits, shots.length),
    shots,
  }
}

function normalizeMessage(value: unknown, conversationId: string): ChatMessage {
  const body = asRecord(value)
  const storyboard = normalizeStoryboard(body.storyboard)
  const assets = list(body.assets).map(normalizeAsset).filter(asset => asset.url)
  return {
    id: String(body.id || body.message_id || crypto.randomUUID()),
    conversationId: String(body.conversation_id || body.conversationId || conversationId),
    role: (body.role === 'user' || body.role === 'system' ? body.role : 'assistant'),
    kind: (body.kind || (storyboard ? 'storyboard' : assets.length ? 'media' : 'text')) as ChatMessage['kind'],
    text: String(body.text || body.content || body.message || ''),
    attachments: list(body.attachments).map(normalizeAttachment),
    assets,
    storyboard,
    taskId: String(body.task_id || body.taskId || ''),
    createdAt: String(body.created_at || body.createdAt || new Date().toISOString()),
  }
}

function normalizeTask(value: unknown): Task {
  const body = asRecord(value)
  return {
    id: String(body.id || body.task_id || ''),
    conversationId: String(body.conversation_id || body.conversationId || ''),
    title: String(body.title || body.name || '生产任务'),
    tool: (body.tool || body.mode || 'create_video') as ToolMode,
    status: (body.status || 'queued') as Task['status'],
    stage: String(body.stage || body.current_stage || '排队中'),
    progress: Math.min(100, Math.max(0, n(body.progress || body.progress_percent))),
    queuePosition: n(body.queue_position || body.queuePosition) || undefined,
    etaSeconds: n(body.eta_seconds || body.etaSeconds) || undefined,
    errorMessage: String(body.error_message || body.errorMessage || ''),
    assetIds: list(body.asset_ids).map(String),
    createdAt: String(body.created_at || body.createdAt || new Date().toISOString()),
    updatedAt: String(body.updated_at || body.updatedAt || ''),
  }
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [checking, setChecking] = useState(true)
  useEffect(() => { api.session().then(setSession).catch(() => setSession(null)).finally(() => setChecking(false)) }, [])
  if (checking) return <FullLoader label="正在连接工作台" />
  if (!session) return <Login onLogin={setSession} />
  if (session.role === 'admin' || location.pathname.endsWith('/admin')) return <Admin session={session} onLogout={() => setSession(null)} />
  return <ChatWorkspace session={session} onLogout={() => setSession(null)} />
}

function ChatWorkspace({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [usage, setUsage] = useState(EMPTY_USAGE)
  const [tool, setTool] = useState<ToolMode>('create_video')
  const [duration, setDuration] = useState('')
  const [draft, setDraft] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [links, setLinks] = useState<string[]>([])
  const [linkDraft, setLinkDraft] = useState('')
  const [showLinkInput, setShowLinkInput] = useState(false)
  const [askingDuration, setAskingDuration] = useState(false)
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<MediaAsset | null>(null)
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [leftOpen, setLeftOpen] = useState(false)
  const [rightOpen, setRightOpen] = useState(false)
  const [search, setSearch] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const messageEnd = useRef<HTMLDivElement>(null)

  const loadConversations = useCallback(async () => {
    const rows = (await api.conversations()).map(normalizeConversation).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    setConversations(rows)
    setActiveId(current => current || rows[0]?.id || '')
  }, [])

  const loadWorkspace = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [bootstrap, taskRows] = await Promise.all([api.bootstrap(), api.tasks()])
      const body = asRecord(bootstrap)
      setUsage(normalizeUsage(body.usage || body))
      setTasks(taskRows.map(normalizeTask))
      setError('')
    } catch (reason) {
      if (!silent) setError(reason instanceof ApiError ? reason.message : '工作台暂时无法连接')
    } finally { if (!silent) setLoading(false) }
  }, [])

  const loadMessages = useCallback(async (conversationId: string, silent = false) => {
    if (!conversationId) { setMessages([]); return }
    try {
      const rows = (await api.messages(conversationId)).map(row => normalizeMessage(row, conversationId))
      setMessages(rows.sort((a, b) => a.createdAt.localeCompare(b.createdAt)))
      if (!silent) setError('')
    } catch (reason) {
      if (!silent) setError(reason instanceof ApiError ? reason.message : '读取对话失败')
    }
  }, [])

  useEffect(() => { Promise.all([loadConversations(), loadWorkspace()]).catch(() => setLoading(false)) }, [loadConversations, loadWorkspace])
  useEffect(() => { loadMessages(activeId) }, [activeId, loadMessages])
  useEffect(() => {
    const timer = window.setInterval(() => {
      loadWorkspace(true)
      if (activeId) loadMessages(activeId, true)
    }, 4000)
    return () => window.clearInterval(timer)
  }, [activeId, loadMessages, loadWorkspace])
  useEffect(() => { messageEnd.current?.scrollIntoView({ block: 'end' }) }, [messages, askingDuration])

  const assets = useMemo(() => messages.flatMap(message => message.assets), [messages])
  useEffect(() => { if (!preview && assets.length) setPreview(assets[assets.length - 1]) }, [assets, preview])
  const activeTask = useMemo(() => tasks.find(task => ['running', 'queued', 'waiting_confirmation'].includes(task.status)) || tasks[0], [tasks])
  const taskCounts = useMemo(() => ({
    waiting: tasks.filter(task => task.status === 'queued' || task.status === 'waiting_confirmation').length,
    running: tasks.filter(task => task.status === 'running').length,
    succeeded: tasks.filter(task => task.status === 'succeeded').length,
    failed: tasks.filter(task => task.status === 'failed').length,
  }), [tasks])
  const filteredConversations = conversations.filter(item => `${item.title} ${item.lastMessage || ''}`.toLowerCase().includes(search.toLowerCase()))
  const currentTool = TOOLS.find(item => item.id === tool) || TOOLS[0]

  async function newConversation() {
    try {
      const created = normalizeConversation(await api.createConversation())
      setConversations(current => [created, ...current])
      setActiveId(created.id)
      setMessages([])
      setLeftOpen(false)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : '新建对话失败') }
  }

  async function ensureConversation() {
    if (activeId) return activeId
    const title = draft.trim().slice(0, 24) || currentTool.label
    const created = normalizeConversation(await api.createConversation(title))
    setConversations(current => [created, ...current])
    setActiveId(created.id)
    return created.id
  }

  async function sendMessage(durationOverride?: number) {
    if (!draft.trim() && !files.length && !links.length) { setError('请先输入需求或添加素材') ; return }
    const resolvedDuration = durationOverride || n(duration)
    if (currentTool.needsDuration && !resolvedDuration) { setAskingDuration(true); return }
    setSending(true)
    setAskingDuration(false)
    setError('')
    try {
      const conversationId = await ensureConversation()
      const urlsInText = Array.from(draft.matchAll(/https?:\/\/[^\s]+/g), match => match[0])
      const optimistic: ChatMessage = {
        id: `local-${Date.now()}`, conversationId, role: 'user', kind: 'text', text: draft.trim(),
        attachments: files.map((file, index) => ({ id: `local-file-${index}`, name: file.name, kind: attachmentKind(file.type, file.name), mimeType: file.type, size: file.size, url: file.type.startsWith('image/') || file.type.startsWith('video/') ? URL.createObjectURL(file) : '' })),
        assets: [], createdAt: new Date().toISOString(),
      }
      setMessages(current => [...current, optimistic])
      await api.sendMessage(conversationId, { text: draft.trim(), tool, durationSeconds: resolvedDuration || undefined, files, links: Array.from(new Set([...links, ...urlsInText])) })
      setDraft(''); setFiles([]); setLinks([]); setDuration('')
      if (fileInput.current) fileInput.current.value = ''
      await Promise.all([loadMessages(conversationId, true), loadConversations(), loadWorkspace(true)])
    } catch (reason) {
      setError(reason instanceof ApiError ? `${reason.message}${reason.requestId ? `（请求 ${reason.requestId}）` : ''}` : '提交失败，请重试')
    } finally { setSending(false) }
  }

  function addLink() {
    const value = linkDraft.trim()
    try {
      const parsed = new URL(value)
      if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error()
      setLinks(current => current.includes(value) ? current : [...current, value])
      setLinkDraft(''); setShowLinkInput(false); setError('')
    } catch { setError('请输入完整的 http 或 https 链接') }
  }

  async function confirmStoryboard(storyboard: Storyboard, approved: boolean) {
    try {
      await api.confirmStoryboard(storyboard.id, approved, approved ? '' : '请按当前对话反馈重新规划')
      await Promise.all([loadMessages(activeId, true), loadWorkspace(true)])
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : '分镜确认失败') }
  }

  function toggleAsset(asset: MediaAsset) {
    setSelected(current => {
      const next = new Set(current)
      if (next.has(asset.id)) next.delete(asset.id); else next.add(asset.id)
      return next
    })
  }

  async function batchDownload() {
    if (!selected.size) return
    try {
      const result = await api.batchDownload(Array.from(selected))
      const anchor = document.createElement('a')
      anchor.href = result.download_url
      anchor.download = ''
      anchor.click()
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : '批量下载失败') }
  }

  async function logout() { try { await api.logout() } finally { onLogout() } }

  return <div className="chat-app">
    <button className="mobile-panel-button mobile-left" onClick={() => setLeftOpen(true)} title="打开对话列表"><Menu /></button>
    <button className="mobile-panel-button mobile-right" onClick={() => setRightOpen(true)} title="打开任务与预览"><PanelRightOpen /></button>
    {(leftOpen || rightOpen) && <button className="drawer-scrim" onClick={() => { setLeftOpen(false); setRightOpen(false) }} aria-label="关闭侧栏" />}

    <aside className={leftOpen ? 'conversation-rail is-open' : 'conversation-rail'}>
      <div className="rail-brand"><span>HS</span><b>Hook Studio</b><button className="rail-close" onClick={() => setLeftOpen(false)} title="关闭"><X /></button></div>
      <button className="new-conversation" onClick={newConversation}><Plus />新建对话</button>
      <label className="conversation-search"><Search /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索对话" aria-label="搜索对话" /></label>
      <nav className="tool-nav" aria-label="生产工具">
        <p>生产工具</p>
        {TOOLS.map(item => <button key={item.id} className={tool === item.id ? 'is-active' : ''} onClick={() => { setTool(item.id); setLeftOpen(false) }}><item.icon /><span>{item.label}</span></button>)}
      </nav>
      <div className="conversation-list"><p>最近对话</p>{filteredConversations.length ? filteredConversations.map(item => <button key={item.id} className={activeId === item.id ? 'is-active' : ''} onClick={() => { setActiveId(item.id); setLeftOpen(false) }}><span>{item.title}</span><small>{item.lastMessage || new Date(item.updatedAt).toLocaleDateString('zh-CN')}</small>{Boolean(item.unreadCount) && <em>{item.unreadCount}</em>}</button>) : <div className="rail-empty">还没有对话</div>}</div>
      <div className="account-dock">
        <div className="account-row"><span>{session.clientName.slice(0, 1).toUpperCase()}</span><div><b>{session.clientName}</b><small>{session.clientId || '客户工作区'}</small></div><button onClick={logout} title="退出登录"><LogOut /></button></div>
        <QuotaLine icon={<ImageIcon />} label="图片额度" used={usage.imageUsed} limit={usage.imageLimit} />
        <QuotaLine icon={<Film />} label="视频额度" used={usage.clientVideoUsed} limit={usage.clientVideoLimit} />
      </div>
    </aside>

    <main className="chat-main">
      <header className="chat-header"><div><p>{currentTool.label}</p><h1>{conversations.find(item => item.id === activeId)?.title || '新对话'}</h1></div><div className="header-usage"><span>图片 <b>{usage.imageUsed}/{usage.imageLimit}</b></span><span>视频 <b>{usage.clientVideoUsed}/{usage.clientVideoLimit}</b></span></div></header>
      {error && <div className="workspace-error" role="alert"><CircleAlert /><span>{error}</span><button onClick={() => setError('')} title="关闭"><X /></button></div>}
      <section className="message-stream" aria-live="polite">
        {loading ? <SmallLoader label="正在读取工作区" /> : messages.length === 0 ? <EmptyConversation tool={currentTool.label} /> : messages.map(message => <Message key={message.id} message={message} selected={selected} onPreview={asset => { setPreview(asset); setRightOpen(true) }} onToggle={toggleAsset} onConfirm={confirmStoryboard} />)}
        {askingDuration && <DurationQuestion onChoose={seconds => { setDuration(String(seconds)); sendMessage(seconds) }} onCancel={() => setAskingDuration(false)} />}
        <div ref={messageEnd} />
      </section>

      <section className="composer-wrap">
        {files.length > 0 && <div className="composer-files">{files.map((file, index) => <div key={`${file.name}-${index}`}><FileKindIcon file={file} /><span>{file.name}</span><button onClick={() => setFiles(current => current.filter((_, itemIndex) => itemIndex !== index))} title="移除附件"><X /></button></div>)}</div>}
        {links.length > 0 && <div className="composer-links">{links.map(item => <span key={item}><LinkIcon />{new URL(item).hostname}<button onClick={() => setLinks(current => current.filter(link => link !== item))} title="移除链接"><X /></button></span>)}</div>}
        {showLinkInput && <div className="link-entry"><LinkIcon /><input value={linkDraft} onChange={event => setLinkDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); addLink() } }} placeholder="粘贴商品页或参考视频链接" autoFocus /><button onClick={addLink}>添加</button><button onClick={() => setShowLinkInput(false)} title="关闭"><X /></button></div>}
        <div className="composer">
          <textarea value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage() } }} placeholder="描述要制作、复刻、分析或替换的内容" aria-label="创作需求" />
          <div className="composer-toolbar">
            <div className="composer-tools">
              <label className="tool-select"><currentTool.icon /><select value={tool} onChange={event => { setTool(event.target.value as ToolMode); setDuration('') }}>{TOOLS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select><ChevronDown /></label>
              <button onClick={() => fileInput.current?.click()} title="添加文件"><Paperclip /></button>
              <input ref={fileInput} hidden multiple type="file" accept="image/*,video/*,audio/*,.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json,.html,.srt,.vtt" onChange={event => setFiles(current => [...current, ...Array.from(event.target.files || [])])} />
              <button onClick={() => setShowLinkInput(current => !current)} title="添加链接"><LinkIcon /></button>
              {currentTool.needsDuration && <label className="duration-select"><Clock3 /><input value={duration} onChange={event => setDuration(event.target.value)} type="number" min="4" step="1" placeholder="时长(秒)" aria-label="视频时长（秒）" /></label>}
            </div>
            <button className="send-button" onClick={() => sendMessage()} disabled={sending || (!draft.trim() && !files.length && !links.length)} title="发送">{sending ? <LoaderCircle className="spin" /> : <Send />}</button>
          </div>
        </div>
      </section>
    </main>

    <aside className={rightOpen ? 'inspector is-open' : 'inspector'}>
      <header className="inspector-header"><div><p>任务与预览</p><b>{tasks.length} 个任务</b></div><button className="rail-close" onClick={() => setRightOpen(false)} title="关闭"><X /></button></header>
      <div className="task-counts"><StatusCount label="等待" value={taskCounts.waiting} tone="wait" /><StatusCount label="执行" value={taskCounts.running} tone="run" /><StatusCount label="成功" value={taskCounts.succeeded} tone="ok" /><StatusCount label="失败" value={taskCounts.failed} tone="bad" /></div>
      <section className="preview-pane"><div className="inspector-section-head"><span>媒体预览</span>{preview && <a href={api.assetDownloadUrl(preview.id)} title="下载"><Download /></a>}</div>{preview ? <MediaPreview asset={preview} /> : <div className="preview-empty"><Play /><span>选择对话中的图片或视频</span></div>}</section>
      <section className="task-progress"><div className="inspector-section-head"><span>执行阶段</span>{activeTask && <em>{activeTask.progress}%</em>}</div>{activeTask ? <><div className="current-task"><b>{activeTask.title}</b><small>{activeTask.stage}{activeTask.queuePosition ? ` · 前方 ${Math.max(0, activeTask.queuePosition - 1)} 个任务` : ''}</small><div><i style={{ width: `${activeTask.progress}%` }} /></div></div><ol>{TASK_STAGES.map((stage, index) => { const currentIndex = Math.max(0, TASK_STAGES.findIndex(item => activeTask.stage.includes(item))); const state = index < currentIndex ? 'done' : index === currentIndex ? 'active' : ''; return <li key={stage} className={state}><span>{state === 'done' ? <Check /> : index + 1}</span><b>{stage}</b></li> })}</ol></> : <div className="inspector-empty">当前没有执行中的任务</div>}</section>
      <section className="asset-batch"><div className="inspector-section-head"><span>本次结果</span><button onClick={() => setSelected(current => current.size === assets.length ? new Set() : new Set(assets.map(asset => asset.id)))}>{selected.size === assets.length && assets.length ? <CheckSquare2 /> : <Square />}{selected.size}/{assets.length}</button></div><div className="asset-strip">{assets.map(asset => <button key={asset.id} className={selected.has(asset.id) ? 'is-selected' : ''} onClick={() => { setPreview(asset); toggleAsset(asset) }}>{asset.type === 'video' ? <video src={asset.url} muted preload="metadata" /> : <img src={asset.thumbnailUrl || asset.url} alt={asset.name} />}<span>{selected.has(asset.id) && <Check />}</span></button>)}</div><button className="batch-download" disabled={!selected.size} onClick={batchDownload}><Download />批量下载 {selected.size ? `(${selected.size})` : ''}</button></section>
    </aside>
  </div>
}

function Message({ message, selected, onPreview, onToggle, onConfirm }: { message: ChatMessage; selected: Set<string>; onPreview: (asset: MediaAsset) => void; onToggle: (asset: MediaAsset) => void; onConfirm: (storyboard: Storyboard, approved: boolean) => void }) {
  return <article className={`message ${message.role} kind-${message.kind}`}>
    <div className="message-author">{message.role === 'user' ? '你' : message.role === 'system' ? '系统' : 'Hook Studio'}<time>{new Date(message.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</time></div>
    {message.text && <div className="message-text">{message.text}</div>}
    {message.attachments.length > 0 && <div className="message-attachments">{message.attachments.map(item => <a key={item.id} href={item.url || undefined} target="_blank" rel="noreferrer"><AttachmentIcon kind={item.kind} />{item.kind === 'image' && item.url ? <img src={item.thumbnailUrl || item.url} alt={item.name} /> : item.kind === 'video' && item.url ? <video src={item.url} muted preload="metadata" /> : null}<span>{item.name}<small>{item.extractedText ? '已解析' : item.status === 'uploading' ? '上传中' : '已接收'}</small></span></a>)}</div>}
    {message.storyboard && <StoryboardCard storyboard={message.storyboard} onConfirm={onConfirm} />}
    {message.assets.length > 0 && <div className="message-media">{message.assets.map(asset => <div key={asset.id} className={selected.has(asset.id) ? 'media-result is-selected' : 'media-result'}><button className="media-open" onClick={() => onPreview(asset)}>{asset.type === 'video' ? <video src={asset.url} poster={asset.thumbnailUrl} controls preload="metadata" /> : <img src={asset.thumbnailUrl || asset.url} alt={asset.name} />}</button><div><span>{asset.name}</span><button onClick={() => onToggle(asset)} title="选择用于批量下载">{selected.has(asset.id) ? <CheckSquare2 /> : <Square />}</button><a href={api.assetDownloadUrl(asset.id)} title="下载"><Download /></a></div></div>)}</div>}
    {message.kind === 'status' && message.taskId && <span className="message-task-id">任务 {message.taskId.slice(0, 8)}</span>}
  </article>
}

function StoryboardCard({ storyboard, onConfirm }: { storyboard: Storyboard; onConfirm: (storyboard: Storyboard, approved: boolean) => void }) {
  return <section className="storyboard"><header><div><span>故事板 {storyboard.version}</span><b>{storyboard.totalDurationSeconds}s · {storyboard.shots.length} 个镜头</b></div><em>预计消耗 {storyboard.estimatedVideoUnits} 条视频额度</em></header>{storyboard.summary && <p>{storyboard.summary}</p>}<div className="storyboard-grid">{storyboard.shots.map(shot => <article key={shot.id}>{shot.imageUrl ? <img src={shot.imageUrl} alt={`镜头 ${shot.order}：${shot.title}`} /> : <div className="shot-placeholder"><Film /></div>}<div><span>{String(shot.order).padStart(2, '0')} · {shot.durationSeconds}s</span><b>{shot.title}</b><p>{shot.description}</p></div></article>)}</div>{storyboard.status === 'pending' ? <footer><button className="storyboard-revise" onClick={() => onConfirm(storyboard, false)}><RefreshCw />调整分镜</button><button className="storyboard-confirm" onClick={() => onConfirm(storyboard, true)}><Check />确认生产</button></footer> : <div className={`storyboard-state ${storyboard.status}`}><Check />{storyboard.status === 'confirmed' ? '已确认生产' : '已退回调整'}</div>}</section>
}

function DurationQuestion({ onChoose, onCancel }: { onChoose: (seconds: number) => void; onCancel: () => void }) {
  return <article className="message assistant duration-question"><div className="message-author">Hook Studio</div><div className="message-text">这支视频准备做多长？支持60秒以上，系统会自动拆镜头并拼接。</div><div className="duration-options">{[15, 30, 60, 120, 300].map(seconds => <button key={seconds} onClick={() => onChoose(seconds)}>{seconds}s</button>)}<button onClick={onCancel}>自定义时长</button></div></article>
}

function EmptyConversation({ tool }: { tool: string }) {
  return <div className="empty-conversation"><div className="empty-mark">HS</div><h2>{tool}</h2><p>发来需求、文件、图片、视频或链接。</p><div><span><Paperclip />多格式素材</span><span><Film />故事板确认</span><span><Layers3 />批量交片</span></div></div>
}

function MediaPreview({ asset }: { asset: MediaAsset }) {
  if (asset.type === 'video') return <video className="preview-media" src={asset.url} poster={asset.thumbnailUrl} controls autoPlay muted />
  if (asset.type === 'audio') return <div className="audio-preview"><Volume2 /><audio src={asset.url} controls /></div>
  if (asset.type === 'document') return <a className="document-preview" href={asset.url} target="_blank" rel="noreferrer"><FileText /><span>{asset.name}</span></a>
  return <img className="preview-media" src={asset.url} alt={asset.name} />
}

function AttachmentIcon({ kind }: { kind: AttachmentKind }) {
  if (kind === 'image') return <ImageIcon />
  if (kind === 'video') return <Film />
  if (kind === 'audio') return <Volume2 />
  if (kind === 'link') return <LinkIcon />
  return <FileText />
}

function FileKindIcon({ file }: { file: File }) { return <AttachmentIcon kind={attachmentKind(file.type, file.name)} /> }

function QuotaLine({ icon, label, used, limit }: { icon: React.ReactNode; label: string; used: number; limit: number }) {
  const percent = Math.min(100, used / Math.max(1, limit) * 100)
  return <div className="quota-line"><div>{icon}<span>{label}</span><b>{used}/{limit}</b></div><i><span style={{ width: `${percent}%` }} /></i></div>
}

function StatusCount({ label, value, tone }: { label: string; value: number; tone: string }) { return <div className={`task-count ${tone}`}><span>{label}</span><b>{value}</b></div> }

function Admin({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [clients, setClients] = useState<ClientUsage[]>([])
  const [usage, setUsage] = useState(EMPTY_USAGE)
  const [health, setHealth] = useState('检查中')
  const [backup, setBackup] = useState('检查中')
  const [tables, setTables] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.admin(); const raw = asRecord(data); const healthData = asRecord(raw.health)
      setClients(list(raw.clients).map(value => { const item = asRecord(value); return { id: String(item.id || item.code_id), name: String(item.name || item.client_name), enabled: Boolean(item.enabled), videoUsed: n(item.video_used), videoLimit: n(item.video_limit || item.daily_video_limit, 100), imageUsed: n(item.image_used), imageLimit: n(item.image_limit || item.daily_image_limit, 1000), downloads: n(item.downloads) } }))
      const backupData = healthData.backup || raw.backup
      const backupLabel = typeof backupData === 'string' ? backupData : asRecord(backupData).verified ? `已验证 · ${String(asRecord(backupData).created_at || '').slice(0, 10)}` : '暂无记录'
      setUsage(normalizeUsage(Array.isArray(raw.usage) ? raw.usage[0] : raw.usage)); setHealth(String(healthData.database || raw.health || '正常')); setBackup(backupLabel); setTables(asRecord(raw.tables) as Record<string, number>); setError('')
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : '管理数据加载失败') } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])
  async function logout() { try { await api.logout() } finally { onLogout() } }
  return <div className="admin-shell">
    <header className="admin-topbar"><div><span>HS</span><b>Hook Studio 管理后台</b></div><div><em>{session.clientName}</em><button onClick={logout} title="退出"><LogOut /></button></div></header>
    <main className="admin-main">
      <div className="admin-title"><div><p>运营控制台</p><h1>今日运行概览</h1></div><div className="admin-title-actions"><label>全站视频上限 <QuotaEditor used={usage.globalVideoUsed} limit={usage.globalVideoLimit} max={1000} onSave={async value => { await api.updateGlobalLimit(value); await load() }} /></label><button onClick={load}><RefreshCw />刷新</button></div></div>
      {error && <div className="workspace-error"><CircleAlert />{error}</div>}
      <div className="admin-metrics"><Metric icon={<Gauge />} label="全站视频" value={`${usage.globalVideoUsed}/${usage.globalVideoLimit}`} note="UTC+8 重置" /><Metric icon={<Users />} label="活跃账号" value={String(clients.filter(client => client.enabled).length)} note={`共 ${clients.length} 个`} /><Metric icon={<ShieldCheck />} label="服务健康" value={health} note="队列与数据库" /><Metric icon={<Clock3 />} label="最近备份" value={backup} note="数据与事件日志" /></div>
      <section className="admin-table-section"><header><div><h2>账号与额度</h2><p>服务端强制执行访问状态和额度。</p></div><Settings2 /></header>{loading ? <SmallLoader label="读取账号" /> : <div className="table-wrap"><table><thead><tr><th>账号</th><th>图片</th><th>视频</th><th>下载</th><th>状态</th></tr></thead><tbody>{clients.map(client => <tr key={client.id}><td><b>{client.name}</b><small>{client.id}</small></td><td><QuotaEditor used={client.imageUsed || 0} limit={client.imageLimit || 1000} max={1000} onSave={value => api.updateClient(client.id, { image_limit: value })} /></td><td><QuotaEditor used={client.videoUsed} limit={client.videoLimit} max={100} onSave={value => api.updateClient(client.id, { video_limit: value })} /></td><td>{client.downloads}</td><td><button className={client.enabled ? 'status-toggle on' : 'status-toggle'} onClick={async () => { await api.updateClient(client.id, { enabled: !client.enabled }); load() }}>{client.enabled ? '已启用' : '已停用'}</button></td></tr>)}</tbody></table></div>}</section>
      <section className="admin-table-section data-assets"><header><div><h2>训练数据资产</h2><p>对话、附件、任务和结果已结构化入库，可直接导出。</p></div><FileText /></header><div className="data-counts"><span>对话<b>{n(tables.conversations)}</b></span><span>消息<b>{n(tables.messages)}</b></span><span>素材<b>{n(tables.assets)}</b></span><span>任务<b>{n(tables.task_runs)}</b></span><span>训练样本<b>{n(tables.training_examples)}</b></span></div><div className="data-actions"><a href={api.trainingExportUrl()}><Download />导出训练 JSONL</a><a href={api.eventsExportUrl()}><Download />导出事件 JSONL</a></div></section>
    </main>
  </div>
}

function Metric({ icon, label, value, note }: { icon: React.ReactNode; label: string; value: string; note: string }) { return <article className="admin-metric"><div>{icon}<span>{label}</span></div><b>{value}</b><small>{note}</small></article> }
function QuotaEditor({ used, limit, max, onSave }: { used: number; limit: number; max: number; onSave: (value: number) => Promise<unknown> }) {
  const [value, setValue] = useState(String(limit))
  return <label className="quota-editor"><span>{used}/</span><input aria-label="每日额度" type="number" min="0" max={max} value={value} onChange={event => setValue(event.target.value)} onBlur={async () => { const next = Math.max(0, Math.min(max, n(value, limit))); setValue(String(next)); if (next !== limit) await onSave(next) }} /></label>
}
function FullLoader({ label }: { label: string }) { return <div className="full-loader"><span>HS</span><LoaderCircle className="spin" /><p>{label}</p></div> }
function SmallLoader({ label }: { label: string }) { return <div className="small-loader"><LoaderCircle className="spin" /><span>{label}</span></div> }
