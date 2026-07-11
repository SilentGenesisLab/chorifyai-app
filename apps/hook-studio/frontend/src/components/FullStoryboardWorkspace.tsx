import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Archive, BadgeCheck, Check, CheckCircle2, ChevronDown, CircleAlert, CircleDashed,
  Clock3, Download, Eye, FileText, Film, GalleryHorizontalEnd, Image as ImageIcon,
  Layers3, Link as LinkIcon, ListChecks, LoaderCircle, LockKeyhole, LogOut, Menu,
  MessageSquareText, PackageCheck, PanelRightOpen, Paperclip, Play, Plus, RefreshCw,
  ScanLine, Search, Send, Table2, Timer, Video, Volume2, X,
} from 'lucide-react'
import { ApiError, api } from '../api'
import {
  arrayValue, attachmentKind, normalizeAsset, normalizeConversation, normalizeMessage,
  normalizeQueues, normalizeStoryboard, normalizeTask, normalizeUsage, normalizeWorkflowEvent, numberValue,
  record,
} from '../storyboard'
import type {
  AttachmentKind, ChatMessage, Conversation, InspectorView, MediaAsset, QueueSnapshot, Session,
  SkillStage, Storyboard, StoryboardPanel, StoryboardShot, Task, ToolMode, Usage, WorkflowEvent,
  WorkspaceView,
} from '../types'

const EMPTY_USAGE: Usage = {
  globalVideoUsed: 0, globalVideoLimit: 100, clientVideoUsed: 0, clientVideoLimit: 100,
  imageUsed: 0, imageLimit: 1000, resetAt: '',
}

const EMPTY_QUEUES: QueueSnapshot = {
  imageQueued: 0, imageRunning: 0, imageSucceeded: 0, imageFailed: 0,
  videoQueued: 0, videoRunning: 0, videoSucceeded: 0, videoFailed: 0,
  waitingApproval: 0, succeeded: 0, failed: 0,
}

const TOOLS: Array<{ id: ToolMode; label: string; icon: typeof Video; needsDuration: boolean }> = [
  { id: 'create_video', label: '视频生产', icon: Video, needsDuration: true },
  { id: 'create_image', label: '图片生产', icon: ImageIcon, needsDuration: false },
  { id: 'edit_image', label: '局部修图', icon: ScanLine, needsDuration: false },
  { id: 'reference_remix', label: '参控复刻', icon: Layers3, needsDuration: true },
  { id: 'batch_production', label: '批量生产', icon: GalleryHorizontalEnd, needsDuration: true },
  { id: 'reverse_analysis', label: '逆向分析', icon: Search, needsDuration: false },
  { id: 'replace_content', label: '定向替换', icon: RefreshCw, needsDuration: true },
]

const CAPABILITY_STAGES = ['素材理解', '联网研究', '商业节拍', '分镜设计', '连续性校验', '参考帧制作', '动态预演', '生产质检']
const IMAGE_CAPABILITY_STAGES = ['图片需求', '素材与区域', '编辑路由', '生成处理', '像素合成', '生产质检']

type PreviewItem = MediaAsset & { label?: string }
type StreamState = 'idle' | 'connecting' | 'live' | 'recovering'
type PanelCandidate = {
  id: string; version: number; cleanUrl: string; annotatedUrl: string; isCurrent: boolean;
}

export default function FullStoryboardWorkspace({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [usage, setUsage] = useState(EMPTY_USAGE)
  const [queues, setQueues] = useState(EMPTY_QUEUES)
  const [storyboard, setStoryboard] = useState<Storyboard>()
  const [events, setEvents] = useState<WorkflowEvent[]>([])
  const [streamState, setStreamState] = useState<StreamState>('idle')
  const [activeView, setActiveView] = useState<WorkspaceView>('filmstrip')
  const [selectedShotId, setSelectedShotId] = useState('')
  const [frameMode, setFrameMode] = useState<'annotated' | 'clean'>('annotated')
  const [selectedPanelId, setSelectedPanelId] = useState('')
  const [inspectorView, setInspectorView] = useState<InspectorView>('assets')
  const [preview, setPreview] = useState<PreviewItem>()
  const [selectedAssets, setSelectedAssets] = useState<Set<string>>(() => new Set())
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
  const [leftOpen, setLeftOpen] = useState(false)
  const [rightOpen, setRightOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [confirmProduction, setConfirmProduction] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const editSourceInput = useRef<HTMLInputElement>(null)
  const editMaskInput = useRef<HTMLInputElement>(null)
  const editAnnotationInput = useRef<HTMLInputElement>(null)
  const messageEnd = useRef<HTMLDivElement>(null)
  const submissionRef = useRef<{ fingerprint: string; key: string } | null>(null)

  const currentTool = TOOLS.find(item => item.id === tool) || TOOLS[0]

  const loadShell = useCallback(async () => {
    setLoading(true)
    try {
      const [conversationRows, bootstrap] = await Promise.all([api.conversations(), api.bootstrap()])
      const rows = conversationRows.map(normalizeConversation).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      setConversations(rows)
      setActiveId(current => current || rows[0]?.id || '')
      const body = record(bootstrap)
      setUsage(normalizeUsage(body.usage || body))
      setQueues(normalizeQueues(body.queues))
      setError('')
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '工作台暂时无法连接')
    } finally { setLoading(false) }
  }, [])

  const loadConversation = useCallback(async (conversationId: string, silent = false) => {
    if (!conversationId) { setMessages([]); setTasks([]); setStoryboard(undefined); return }
    if (!silent) setLoading(true)
    try {
      const [messageRows, taskRows, bootstrap] = await Promise.all([api.messages(conversationId), api.tasks(conversationId), api.bootstrap()])
      setMessages(messageRows.map(value => normalizeMessage(value, conversationId)).sort((a, b) => a.createdAt.localeCompare(b.createdAt)))
      setTasks(taskRows.map(normalizeTask).sort((a, b) => (b.updatedAt || b.createdAt).localeCompare(a.updatedAt || a.createdAt)))
      const body = record(bootstrap)
      setUsage(normalizeUsage(body.usage || body))
      setQueues(normalizeQueues(body.queues))
      setError('')
    } catch (reason) {
      if (!silent) setError(reason instanceof ApiError ? reason.message : '读取当前对话失败')
    } finally { if (!silent) setLoading(false) }
  }, [])

  const loadStoryboard = useCallback(async (storyboardId: string, fallback?: Storyboard) => {
    if (!storyboardId) { if (fallback) setStoryboard(fallback); return }
    try {
      const board = normalizeStoryboard(await api.storyboard(storyboardId)) || fallback
      if (board) setStoryboard(board)
    } catch (reason) {
      if (fallback) setStoryboard(fallback)
      else if (!(reason instanceof ApiError && reason.status === 404)) setError(reason instanceof ApiError ? reason.message : '故事板快照恢复失败')
    }
  }, [])

  useEffect(() => { loadShell() }, [loadShell])
  useEffect(() => { setStoryboard(undefined); setEvents([]); setSelectedShotId(''); loadConversation(activeId) }, [activeId, loadConversation])

  const messageStoryboard = useMemo(() => [...messages].reverse().find(message => message.storyboard)?.storyboard, [messages])
  const activeTask = useMemo(() => tasks.find(task => ['running', 'queued', 'waiting_confirmation'].includes(task.status)) || tasks[0], [tasks])
  const storyboardId = activeTask?.storyboardId || messageStoryboard?.id || ''

  useEffect(() => { if (storyboardId) loadStoryboard(storyboardId, messageStoryboard) }, [storyboardId, messageStoryboard, loadStoryboard])
  useEffect(() => {
    const first = storyboard?.shots[0]
    if (!first) return
    setSelectedShotId(current => storyboard.shots.some(shot => shot.id === current) ? current : first.id)
  }, [storyboard])
  useEffect(() => {
    const shot = storyboard?.shots.find(item => item.id === selectedShotId)
    if (!shot) return
    setSelectedPanelId(current => shot.panels.some(panel => panel.id === current) ? current : shot.panels[0]?.id || '')
  }, [storyboard, selectedShotId])

  useEffect(() => {
    if (!activeTask || !['running', 'queued', 'waiting_confirmation'].includes(activeTask.status)) { setStreamState('idle'); return }
    let recoveryTimer = 0
    let eventRefreshTimer = 0
    let closed = false
    const recover = () => {
      window.clearTimeout(recoveryTimer)
      recoveryTimer = window.setTimeout(async () => {
        if (closed) return
        setStreamState('recovering')
        try {
          const task = normalizeTask(await api.task(activeTask.id))
          setTasks(current => [task, ...current.filter(item => item.id !== task.id)])
          if (task.storyboardId || storyboardId) await loadStoryboard(task.storyboardId || storyboardId, messageStoryboard)
        } catch { /* native EventSource keeps reconnecting */ }
      }, 1200)
    }
    setStreamState('connecting')
    const close = api.openTaskEvents(activeTask.id, {
      onOpen: () => { window.clearTimeout(recoveryTimer); setStreamState('live') },
      onError: recover,
      onEvent: raw => {
        const event = normalizeWorkflowEvent(raw)
        setEvents(current => [...current.filter(item => item.id !== event.id), event].slice(-30))
        const snapshot = record(event.snapshot)
        if (event.queue || event.type === 'queue.snapshot') setQueues(event.queue || normalizeQueues(snapshot))
        if (snapshot.task || snapshot.status) {
          const task = normalizeTask(snapshot.task || snapshot)
          if (task.id) setTasks(current => [task, ...current.filter(item => item.id !== task.id)])
        }
        const board = normalizeStoryboard(snapshot.storyboard || (snapshot.shots ? snapshot : undefined))
        if (board) setStoryboard(board)
        const eventStatus = String(record(snapshot.task).status || snapshot.status || event.state || '')
        if (['succeeded', 'failed', 'cancelled'].includes(eventStatus) && activeId) {
          window.setTimeout(() => loadConversation(activeId, true), 120)
        }
        if (!board && /storyboard|panel|approval|animatic|snapshot|task|provider|completed|failed/.test(event.type)) {
          window.clearTimeout(eventRefreshTimer)
          eventRefreshTimer = window.setTimeout(async () => {
            try {
              const task = normalizeTask(await api.task(activeTask.id))
              setTasks(current => [task, ...current.filter(item => item.id !== task.id)])
              await loadStoryboard(task.storyboardId || storyboardId, messageStoryboard)
            } catch { await loadStoryboard(storyboardId, messageStoryboard) }
          }, 180)
        }
      },
    })
    return () => { closed = true; window.clearTimeout(recoveryTimer); window.clearTimeout(eventRefreshTimer); close() }
  }, [activeTask?.id, activeTask?.status, storyboardId, loadStoryboard, loadConversation, messageStoryboard, activeId])

  useEffect(() => { messageEnd.current?.scrollIntoView({ block: 'end' }) }, [messages, askingDuration, events.length])

  const assets = useMemo(() => {
    const collected: PreviewItem[] = messages.flatMap(message => message.assets)
    storyboard?.shots.forEach(shot => shot.panels.forEach(panel => {
      if (panel.annotatedUrl) collected.push({ id: `${panel.id}-annotated`, panelId: panel.id, shotId: shot.id, type: 'image', role: 'annotated', name: `${shot.code} 带标注故事板`, url: panel.annotatedUrl, thumbnailUrl: panel.thumbnailUrl })
      if (panel.cleanUrl) collected.push({ id: `${panel.id}-clean`, panelId: panel.id, shotId: shot.id, type: 'image', role: 'clean', name: `${shot.code} 干净参考帧`, url: panel.cleanUrl, thumbnailUrl: panel.cleanUrl, approved: panel.approval?.decision === 'approved' })
    }))
    if (storyboard?.animatic?.url) collected.push({ id: storyboard.animatic.id, type: 'video', role: 'animatic', name: '动态预演', url: storyboard.animatic.url, durationSeconds: storyboard.animatic.durationSeconds })
    const unique = new Map<string, PreviewItem>()
    collected.filter(item => item.url).forEach(item => unique.set(item.id || item.url, item))
    return Array.from(unique.values())
  }, [messages, storyboard])
  const finalAssets = useMemo(() => assets.filter(asset => asset.role === 'final' || (asset.type === 'video' && asset.role !== 'animatic')), [assets])
  const filteredConversations = conversations.filter(item => `${item.title} ${item.lastMessage || ''}`.toLowerCase().includes(search.toLowerCase()))

  async function newConversation() {
    try {
      const created = normalizeConversation(await api.createConversation())
      setConversations(current => [created, ...current]); setActiveId(created.id); setMessages([]); setStoryboard(undefined); setLeftOpen(false)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : '新建对话失败') }
  }

  async function ensureConversation() {
    if (activeId) return activeId
    const created = normalizeConversation(await api.createConversation(draft.trim().slice(0, 24) || currentTool.label))
    setConversations(current => [created, ...current]); setActiveId(created.id)
    return created.id
  }

  async function sendMessage(durationOverride?: number) {
    if (!draft.trim() && !files.length && !links.length) { setError('请先输入需求或添加素材'); return }
    const resolvedDuration = durationOverride || numberValue(duration)
    if (currentTool.needsDuration && !resolvedDuration) { setAskingDuration(true); return }
    if (currentTool.needsDuration && (resolvedDuration < 4 || resolvedDuration > 60)) { setError('成片时长请填写 4-60 秒，系统会自动拆成 4-15 秒镜头'); return }
    setSending(true); setAskingDuration(false); setError('')
    try {
      const conversationId = await ensureConversation()
      const urlsInText = Array.from(draft.matchAll(/https?:\/\/[^\s]+/g), match => match[0])
      const submissionLinks = Array.from(new Set([...links, ...urlsInText]))
      const fingerprint = JSON.stringify({ conversationId, text: draft.trim(), tool, duration: resolvedDuration || null, files: files.map(file => [file.name, file.size, file.lastModified]), links: submissionLinks })
      if (submissionRef.current?.fingerprint !== fingerprint) {
        submissionRef.current = { fingerprint, key: crypto.randomUUID() }
      }
      const optimistic: ChatMessage = {
        id: `local-${Date.now()}`, conversationId, role: 'user', kind: 'text', text: draft.trim(),
        attachments: files.map((file, index) => ({ id: `local-file-${index}`, name: file.name, kind: attachmentKind(file.type, file.name), mimeType: file.type, size: file.size, url: file.type.startsWith('image/') || file.type.startsWith('video/') ? URL.createObjectURL(file) : '' })),
        assets: [], createdAt: new Date().toISOString(),
      }
      setMessages(current => [...current, optimistic])
      await api.sendMessage(conversationId, { text: draft.trim(), tool, durationSeconds: resolvedDuration || undefined, files, links: submissionLinks, idempotencyKey: submissionRef.current.key })
      setDraft(''); setFiles([]); setLinks([]); setDuration('')
      submissionRef.current = null
      if (fileInput.current) fileInput.current.value = ''
      for (const input of [editSourceInput.current, editMaskInput.current, editAnnotationInput.current]) {
        if (input) input.value = ''
      }
      await loadConversation(conversationId, true)
      const rows = (await api.conversations()).map(normalizeConversation).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      setConversations(rows)
    } catch (reason) {
      setError(reason instanceof ApiError ? `${reason.message}${reason.requestId ? `（请求 ${reason.requestId}）` : ''}` : '提交失败，请重试')
    } finally { setSending(false) }
  }

  function addLink() {
    const value = linkDraft.trim()
    try {
      const parsed = new URL(value)
      if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error()
      setLinks(current => current.includes(value) ? current : [...current, value]); setLinkDraft(''); setShowLinkInput(false); setError('')
    } catch { setError('请输入完整的 http 或 https 链接') }
  }

  async function applyBoardMutation(action: () => Promise<unknown>) {
    if (!storyboard) return
    try {
      const response = await action()
      const next = normalizeStoryboard(response)
      if (next) setStoryboard(next); else await loadStoryboard(storyboard.id, storyboard)
      setError('')
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : '操作未完成，请重试') }
  }

  async function batchDownload() {
    if (!selectedAssets.size) return
    try {
      const result = await api.batchDownload(Array.from(selectedAssets))
      const anchor = document.createElement('a'); anchor.href = result.download_url; anchor.download = ''; anchor.click()
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : '批量下载失败') }
  }

  async function logout() { try { await api.logout() } finally { onLogout() } }

  return <div className="fs-app">
    <button className="mobile-panel-button mobile-left" onClick={() => setLeftOpen(true)} title="打开对话列表"><Menu /></button>
    <button className="mobile-panel-button mobile-right" onClick={() => setRightOpen(true)} title="打开资产与预览"><PanelRightOpen /></button>
    {(leftOpen || rightOpen) && <button className="drawer-scrim" onClick={() => { setLeftOpen(false); setRightOpen(false) }} aria-label="关闭侧栏" />}

    <aside className={leftOpen ? 'fs-rail is-open' : 'fs-rail'}>
      <div className="rail-brand"><span>HS</span><b>Hook Studio</b><button className="rail-close" onClick={() => setLeftOpen(false)} title="关闭"><X /></button></div>
      <button className="new-conversation" onClick={newConversation}><Plus />新建任务</button>
      <label className="conversation-search"><Search /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索任务" aria-label="搜索任务" /></label>
      <div className="conversation-list"><p>最近任务</p>{filteredConversations.length ? filteredConversations.map(item => <button key={item.id} className={activeId === item.id ? 'is-active' : ''} onClick={() => { setActiveId(item.id); setLeftOpen(false) }}><span>{item.title}</span><small>{item.lastMessage || new Date(item.updatedAt).toLocaleDateString('zh-CN')}</small>{Boolean(item.unreadCount) && <em>{item.unreadCount}</em>}</button>) : <div className="rail-empty">还没有任务</div>}</div>
      <div className="account-dock">
        <div className="account-row"><span>{session.clientName.slice(0, 1).toUpperCase()}</span><div><b>{session.clientName}</b><small>{session.clientId || '客户工作区'}</small></div><button onClick={logout} title="退出登录"><LogOut /></button></div>
        <QuotaLine icon={<ImageIcon />} label="图片额度" used={usage.imageUsed} limit={usage.imageLimit} />
        <QuotaLine icon={<Film />} label="视频额度" used={usage.clientVideoUsed} limit={usage.clientVideoLimit} />
      </div>
    </aside>

    <main className="fs-main">
      <header className="fs-header">
        <div><p>{currentTool.label}</p><h1>{conversations.find(item => item.id === activeId)?.title || '新任务'}</h1></div>
        {storyboard ? <CoveragePills storyboard={storyboard} compact /> : <div className="header-usage"><span>图片 <b>{usage.imageUsed}/{usage.imageLimit}</b></span><span>视频 <b>{usage.clientVideoUsed}/{usage.clientVideoLimit}</b></span></div>}
      </header>
      {error && <div className="workspace-error" role="alert"><CircleAlert /><span>{error}</span><button onClick={() => setError('')} title="关闭"><X /></button></div>}

      <section className="fs-stream" aria-live="polite">
        {loading ? <SmallLoader label="正在恢复任务快照" /> : messages.length === 0 && !storyboard ? <EmptyConversation /> : <>
          {messages.map(message => <ConversationMessage key={message.id} message={message} onPreview={asset => { setPreview(asset); setInspectorView('preview'); setRightOpen(true) }} />)}
          <RequirementCard messages={messages} storyboard={storyboard} />
          {(activeTask || storyboard?.skillStages.length) && <CapabilityProgressCard task={activeTask} storyboard={storyboard} events={events} streamState={streamState} queues={queues} />}
          {storyboard && <>
            <CoverageCard storyboard={storyboard} onApproveBoard={() => applyBoardMutation(() => api.decideStoryboard(storyboard.id, { scope: 'storyboard', scopeId: storyboard.id, decision: 'approved', expectedVersion: storyboard.revision }))} onCreateAnimatic={() => applyBoardMutation(() => api.createAnimatic(storyboard.id, storyboard.revision))} onConfirmAnimatic={() => applyBoardMutation(() => api.decideStoryboard(storyboard.id, { scope: 'animatic', scopeId: storyboard.animatic?.id || 'animatic', decision: 'approved', expectedVersion: storyboard.revision }))} onProduce={() => setConfirmProduction(true)} />
            <StoryboardWorkbench
              storyboard={storyboard} activeView={activeView} setActiveView={setActiveView}
              selectedShotId={selectedShotId} setSelectedShotId={setSelectedShotId}
              selectedPanelId={selectedPanelId} setSelectedPanelId={setSelectedPanelId}
              frameMode={frameMode} setFrameMode={setFrameMode}
              onPreview={asset => { setPreview(asset); setInspectorView('preview'); setRightOpen(true) }}
              onMutate={applyBoardMutation}
            />
          </>}
        </>}
        {askingDuration && <DurationQuestion onChoose={seconds => { setDuration(String(seconds)); sendMessage(seconds) }} onCustom={() => setAskingDuration(false)} />}
        <div ref={messageEnd} />
      </section>

      <section className="fs-composer-wrap">
        {files.length > 0 && <div className="composer-files">{files.map((file, index) => <div key={`${file.name}-${index}`}><AttachmentGlyph kind={attachmentKind(file.type, file.name)} /><span>{file.name}</span><button onClick={() => setFiles(current => current.filter((_, itemIndex) => itemIndex !== index))} title="移除附件"><X /></button></div>)}</div>}
        {links.length > 0 && <div className="composer-links">{links.map(item => <span key={item}><LinkIcon />{new URL(item).hostname}<button onClick={() => setLinks(current => current.filter(link => link !== item))} title="移除链接"><X /></button></span>)}</div>}
        {showLinkInput && <div className="link-entry"><LinkIcon /><input value={linkDraft} onChange={event => setLinkDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); addLink() } }} placeholder="粘贴商品页或参考视频链接" autoFocus /><button onClick={addLink}>添加</button><button onClick={() => setShowLinkInput(false)} title="关闭"><X /></button></div>}
        <div className="composer">
          <textarea value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage() } }} placeholder="描述产品、受众、卖点和希望呈现的结果，也可以上传文本、图片、视频或链接" aria-label="创作需求" />
          <div className="composer-toolbar"><div className="composer-tools">
            <label className="tool-select"><currentTool.icon /><select value={tool} onChange={event => { setTool(event.target.value as ToolMode); setDuration(''); setFiles([]) }}>{TOOLS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select><ChevronDown /></label>
            {tool === 'edit_image' ? <>
              <button onClick={() => editSourceInput.current?.click()} title="选择原图"><ImageIcon /></button>
              <input ref={editSourceInput} hidden type="file" accept="image/*" onChange={event => { const file = event.target.files?.[0]; if (file) setFiles(current => [...current.filter(item => !item.name.startsWith('source-')), taggedFile(file, 'source')]) }} />
              <button onClick={() => editMaskInput.current?.click()} title="选择PNG蒙版"><ScanLine /></button>
              <input ref={editMaskInput} hidden type="file" accept="image/png" onChange={event => { const file = event.target.files?.[0]; if (file) setFiles(current => [...current.filter(item => !item.name.startsWith('mask-')), taggedFile(file, 'mask')]) }} />
              <button onClick={() => editAnnotationInput.current?.click()} title="选择定位说明图"><BadgeCheck /></button>
              <input ref={editAnnotationInput} hidden type="file" accept="image/*" onChange={event => { const file = event.target.files?.[0]; if (file) setFiles(current => [...current.filter(item => !item.name.startsWith('annotation-')), taggedFile(file, 'annotation')]) }} />
            </> : <>
              <button onClick={() => fileInput.current?.click()} title="添加文件"><Paperclip /></button>
              <input ref={fileInput} hidden multiple type="file" accept="image/*,video/*,audio/*,.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json,.html,.srt,.vtt" onChange={event => setFiles(current => [...current, ...Array.from(event.target.files || [])])} />
            </>}
            <button onClick={() => setShowLinkInput(current => !current)} title="添加链接"><LinkIcon /></button>
            {currentTool.needsDuration && <label className="duration-select" title="成片 4-60 秒，系统按镜头拆成 4-15 秒生产"><Clock3 /><input value={duration} onChange={event => setDuration(event.target.value)} type="number" min="4" max="60" step="1" placeholder="4-60s" aria-label="成片时长（秒）" /></label>}
          </div><button className="send-button" onClick={() => sendMessage()} disabled={sending || (!draft.trim() && !files.length && !links.length)} title="发送">{sending ? <LoaderCircle className="spin" /> : <Send />}</button></div>
          {currentTool.needsDuration && <p className="composer-hint">成片可填 4-60 秒，生产内核会自动拆分为 4-15 秒镜头。</p>}
        </div>
      </section>
    </main>

    <aside className={rightOpen ? 'fs-inspector is-open' : 'fs-inspector'}>
      <header className="inspector-header"><div><p>当前任务</p><b>资产与成品</b></div><button className="rail-close" onClick={() => setRightOpen(false)} title="关闭"><X /></button></header>
      <nav className="fs-inspector-tabs" aria-label="资产视图">
        <button className={inspectorView === 'assets' ? 'is-active' : ''} onClick={() => setInspectorView('assets')}><Archive />资产库</button>
        <button className={inspectorView === 'preview' ? 'is-active' : ''} onClick={() => setInspectorView('preview')}><Eye />预览板</button>
        <button className={inspectorView === 'finals' ? 'is-active' : ''} onClick={() => setInspectorView('finals')}><PackageCheck />成品库</button>
      </nav>
      {inspectorView === 'assets' && <AssetLibrary assets={assets} onPreview={asset => { setPreview(asset); setInspectorView('preview') }} />}
      {inspectorView === 'preview' && <PreviewPane preview={preview} storyboard={storyboard} selectedShotId={selectedShotId} frameMode={frameMode} />}
      {inspectorView === 'finals' && <FinalLibrary assets={finalAssets} selected={selectedAssets} setSelected={setSelectedAssets} onPreview={asset => { setPreview(asset); setInspectorView('preview') }} onDownload={batchDownload} />}
    </aside>

    {confirmProduction && storyboard && <ProductionConfirm storyboard={storyboard} onCancel={() => setConfirmProduction(false)} onConfirm={async () => { setConfirmProduction(false); await applyBoardMutation(() => api.produceStoryboard(storyboard.id, storyboard.revision)) }} />}
  </div>
}

function CoveragePills({ storyboard, compact = false }: { storyboard: Storyboard; compact?: boolean }) {
  const { coverage } = storyboard
  return <div className={compact ? 'fs-coverage-pills is-compact' : 'fs-coverage-pills'} data-testid="coverage-summary">
    <span>镜头 <b>{coverage.shotReady}/{coverage.shotTotal}</b></span>
    <span>画格 <b>{coverage.panelReady}/{coverage.panelRequired}</b></span>
    <span>干净帧 <b>{coverage.cleanReady}/{coverage.shotTotal}</b></span>
    <span>已批准 <b>{coverage.approvedShots}/{coverage.shotTotal}</b></span>
  </div>
}

function RequirementCard({ messages, storyboard }: { messages: ChatMessage[]; storyboard?: Storyboard }) {
  const userMessage = [...messages].reverse().find(message => message.role === 'user')
  const delivered = messages.some(message => message.role !== 'user' && message.assets.length > 0)
  if (!userMessage && !storyboard?.brief) return null
  return <article className="fs-dialog-card fs-requirement-card">
    <header><div><MessageSquareText /><span>需求理解</span></div><em>{storyboard ? '已形成生产结构' : delivered ? '已确认并完成' : '正在理解'}</em></header>
    <p>{storyboard?.brief || userMessage?.text || '已接收本次素材与要求。'}</p>
    <div className="fs-fact-row"><span>比例 <b>9:16</b></span>{storyboard && <><span>成片 <b>{storyboard.totalDurationSeconds}s</b></span><span>镜头 <b>{storyboard.shots.length}</b></span></>}</div>
  </article>
}

function CapabilityProgressCard({ task, storyboard, events, streamState, queues }: { task?: Task; storyboard?: Storyboard; events: WorkflowEvent[]; streamState: StreamState; queues: QueueSnapshot }) {
  const [, tick] = useState(0)
  useEffect(() => {
    if (!task || !['running', 'queued'].includes(task.status)) return
    const timer = window.setInterval(() => tick(value => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [task])
  const latest = events[events.length - 1]
  const elapsed = task ? task.waitingSeconds || Math.max(0, Math.floor((Date.now() - new Date(task.createdAt).getTime()) / 1000)) : 0
  const providerWaiting = Boolean(latest?.indeterminate || latest?.type === 'provider.waiting')
  const shownElapsed = latest?.waitedSeconds ?? elapsed
  const terminal = Boolean(task && ['succeeded', 'failed', 'cancelled'].includes(task.status))
  const hasMeasuredProgress = (Boolean(task?.progress) || terminal) && !providerWaiting
  const supplied = storyboard?.skillStages || []
  const currentIndex = stageIndex(task?.stage || latest?.publicLabel || '')
  const fallbackStages = task?.tool === 'create_image' || task?.tool === 'edit_image' ? IMAGE_CAPABILITY_STAGES : CAPABILITY_STAGES
  const stages: SkillStage[] = supplied.length ? supplied : fallbackStages.map((label, index) => ({
    id: `public-stage-${index}`, label,
    state: task?.status === 'succeeded' ? 'succeeded' as const : task?.status === 'failed' && index === currentIndex ? 'failed' as const : index < currentIndex ? 'succeeded' as const : index === currentIndex ? 'running' as const : 'pending' as const,
  }))
  const liveTitle = task?.status === 'succeeded' ? '生产完成' : task?.status === 'failed' ? '任务未完成' : latest?.publicLabel || task?.stage || '准备能力链'
  const liveMessage = task?.status === 'succeeded' ? '结果已进入右侧成品库，可预览、选择和批量下载。' : task?.status === 'failed' ? task.errorMessage || '任务已保留，可修改后重试。' : latest?.message || (task?.status === 'queued' ? `正在排队${task.queuePosition ? `，前方 ${Math.max(0, task.queuePosition - 1)} 个任务` : ''}` : '系统正按镜头复杂度生成关键画面、动作序列或动态预演')
  return <article className="fs-dialog-card fs-progress-card" data-testid="execution-card">
    <header><div><CircleDashed className={task?.status === 'running' ? 'spin' : ''} /><span>任务执行</span></div>{terminal ? <StatusPill status={task?.status || ''} /> : <StreamBadge state={streamState} />}</header>
    <div className="fs-live-message"><b>{liveTitle}</b><span>{liveMessage}</span><small>{terminal ? `总用时 ${formatDuration(shownElapsed)}` : `已等待 ${formatDuration(shownElapsed)} · ${task?.heartbeatAt || latest?.heartbeatAt ? '心跳正常' : streamState === 'live' ? '事件连接正常' : '正在恢复连接'}`}</small></div>
    <div className={hasMeasuredProgress ? 'fs-task-meter' : 'fs-task-meter is-indeterminate'} aria-label={hasMeasuredProgress ? '任务进度' : '任务等待中，无虚假百分比'}><i style={hasMeasuredProgress ? { width: `${task?.progress}%` } : undefined} /></div>
    <div className="fs-queue-snapshot" data-testid="queue-snapshot">
      <div><span><ImageIcon />图片队列</span><b>等待 {queues.imageQueued}</b><b>执行 {queues.imageRunning}</b><b>成功 {queues.imageSucceeded}</b><b>失败 {queues.imageFailed}</b></div>
      <div><span><Video />视频队列</span><b>等待 {queues.videoQueued}</b><b>执行 {queues.videoRunning}</b><b>成功 {queues.videoSucceeded}</b><b>失败 {queues.videoFailed}</b></div>
      <div><span><CheckCircle2 />总计</span><b>待确认 {queues.waitingApproval}</b><b>成功 {queues.succeeded}</b><b>失败 {queues.failed}</b></div>
    </div>
    <ol className="fs-capability-list">{stages.map(stage => <li key={stage.id} className={`is-${stage.state}`}><span>{stage.state === 'succeeded' ? <Check /> : stage.state === 'running' ? <LoaderCircle className="spin" /> : ''}</span><div><b>{stage.label}</b>{stage.publicMessage && <small>{stage.publicMessage}</small>}</div>{stage.outputCount !== undefined && <em>{stage.outputCount} 项</em>}</li>)}</ol>
  </article>
}

function CoverageCard({ storyboard, onApproveBoard, onCreateAnimatic, onConfirmAnimatic, onProduce }: { storyboard: Storyboard; onApproveBoard: () => void; onCreateAnimatic: () => void; onConfirmAnimatic: () => void; onProduce: () => void }) {
  const boardNeedsApproval = storyboard.guard.blockers.some(blocker => blocker.includes('整板'))
  const boardApprovalReady = storyboard.coverage.approvedShots === storyboard.coverage.shotTotal && !storyboard.guard.blockers.some(blocker => /Panel|画格/.test(blocker))
  return <article className="fs-dialog-card fs-coverage-card">
    <header><div><ListChecks /><span>生产覆盖</span></div><em>{storyboard.guard.canProduce ? '全部确认完成' : '仍需确认'}</em></header>
    <CoveragePills storyboard={storyboard} />
    {!storyboard.guard.canProduce && <ul>{storyboard.guard.blockers.map(blocker => <li key={blocker}><CircleAlert />{blocker}</li>)}</ul>}
    <footer>
      {boardNeedsApproval && <button className="secondary-action" disabled={!boardApprovalReady} onClick={onApproveBoard}><BadgeCheck />批准整板</button>}
      {!storyboard.animatic && <button className="secondary-action" onClick={onCreateAnimatic}><Play />生成动态预演</button>}
      {storyboard.animatic && !storyboard.animatic.confirmed && <button className="secondary-action" onClick={onConfirmAnimatic}><CheckCircle2 />确认动态预演</button>}
      <button className="primary-action" data-testid="production-button" disabled={!storyboard.guard.canProduce} onClick={onProduce}><LockKeyhole />批准真实生产</button>
    </footer>
  </article>
}

function StoryboardWorkbench(props: {
  storyboard: Storyboard; activeView: WorkspaceView; setActiveView: (view: WorkspaceView) => void;
  selectedShotId: string; setSelectedShotId: (id: string) => void; selectedPanelId: string; setSelectedPanelId: (id: string) => void;
  frameMode: 'annotated' | 'clean'; setFrameMode: (mode: 'annotated' | 'clean') => void;
  onPreview: (asset: PreviewItem) => void; onMutate: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const { storyboard, activeView, setActiveView, selectedShotId, setSelectedShotId, selectedPanelId, setSelectedPanelId, frameMode, setFrameMode, onPreview, onMutate } = props
  const selectedShot = storyboard.shots.find(shot => shot.id === selectedShotId) || storyboard.shots[0]
  if (!selectedShot) return null
  return <section className="fs-workbench" data-testid="storyboard-workbench">
    <header className="fs-workbench-head"><div><span>全镜头故事板</span><b>{storyboard.version} · {storyboard.totalDurationSeconds}s</b></div><nav aria-label="故事板视图">
      <button className={activeView === 'shot_table' ? 'is-active' : ''} onClick={() => setActiveView('shot_table')}><Table2 />镜头表</button>
      <button className={activeView === 'filmstrip' ? 'is-active' : ''} onClick={() => setActiveView('filmstrip')}><GalleryHorizontalEnd />分镜带</button>
      <button className={activeView === 'animatic' ? 'is-active' : ''} onClick={() => setActiveView('animatic')}><Play />动态预演</button>
    </nav></header>
    {activeView === 'shot_table' && <ShotTable storyboard={storyboard} selectedShotId={selectedShot.id} onSelect={setSelectedShotId} />}
    {activeView === 'filmstrip' && <FilmstripView storyboard={storyboard} shot={selectedShot} panelId={selectedPanelId} setPanelId={setSelectedPanelId} frameMode={frameMode} setFrameMode={setFrameMode} onSelectShot={setSelectedShotId} onPreview={onPreview} onMutate={onMutate} />}
    {activeView === 'animatic' && <AnimaticView storyboard={storyboard} selectedShotId={selectedShot.id} onSelectShot={setSelectedShotId} onMutate={onMutate} />}
  </section>
}

function ShotTable({ storyboard, selectedShotId, onSelect }: { storyboard: Storyboard; selectedShotId: string; onSelect: (id: string) => void }) {
  return <div className="fs-shot-table-wrap" data-testid="shot-table"><table><thead><tr><th>镜头</th><th>时间</th><th>镜头功能与画面</th><th>动作起止</th><th>摄影</th><th>故事板</th><th>状态</th></tr></thead><tbody>{storyboard.shots.map(shot => <tr key={shot.id} className={selectedShotId === shot.id ? 'is-selected' : ''} onClick={() => onSelect(shot.id)}><td><b>{shot.code}</b><small>r{shot.version}</small></td><td>{formatTime(shot.startSeconds)}-{formatTime(shot.endSeconds)}<small>{shot.durationSeconds}s</small></td><td><b>{shot.storyFunction}</b><p>{shot.description}</p></td><td><span>{shot.actionStart}</span><span>{shot.actionEnd}</span></td><td><span>{shot.shotSize} · {shot.cameraAngle}</span><span>{shot.cameraMove}</span></td><td><span>{shot.panels.length} 格</span><span>{shot.selectedCleanFrameUrl ? '干净帧已选' : '缺干净帧'}</span></td><td><StatusPill status={shot.status} /></td></tr>)}</tbody></table></div>
}

function FilmstripView({ storyboard, shot, panelId, setPanelId, frameMode, setFrameMode, onSelectShot, onPreview, onMutate }: {
  storyboard: Storyboard; shot: StoryboardShot; panelId: string; setPanelId: (id: string) => void; frameMode: 'annotated' | 'clean'; setFrameMode: (mode: 'annotated' | 'clean') => void;
  onSelectShot: (id: string) => void; onPreview: (asset: PreviewItem) => void; onMutate: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const panel = shot.panels.find(item => item.id === panelId) || shot.panels[0]
  const [feedback, setFeedback] = useState('')
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(() => shotForm(shot))
  const [candidates, setCandidates] = useState<PanelCandidate[]>([])
  const [candidateLoading, setCandidateLoading] = useState(false)
  useEffect(() => { setFeedback(''); setEditing(false); setForm(shotForm(shot)) }, [shot.id, shot.version])
  useEffect(() => {
    let active = true
    if (!panel) { setCandidates([]); return () => { active = false } }
    setCandidateLoading(true)
    api.panelCandidates(storyboard.id, panel.id).then(value => {
      if (!active) return
      setCandidates(arrayValue(value, 'candidates').map(item => {
        const body = record(item)
        return {
          id: String(body.id || ''), version: numberValue(body.revision || body.version, 1),
          cleanUrl: String(body.clean_url || ''), annotatedUrl: String(body.annotated_url || ''),
          isCurrent: Boolean(body.is_current),
        }
      }).filter(item => item.id))
    }).catch(() => { if (active) setCandidates([]) }).finally(() => { if (active) setCandidateLoading(false) })
    return () => { active = false }
  }, [storyboard.id, panel?.id, panel?.version])
  const displayedUrl = frameMode === 'clean' ? panel?.cleanUrl || shot.selectedCleanFrameUrl : panel?.annotatedUrl || panel?.thumbnailUrl
  const previewAsset: PreviewItem | undefined = displayedUrl ? { id: `${panel?.id || shot.id}-${frameMode}`, type: 'image', role: frameMode, name: `${shot.code} ${frameMode === 'clean' ? '干净参考帧' : '带标注故事板'}`, url: displayedUrl, shotId: shot.id, panelId: panel?.id } : undefined
  return <div className="fs-filmstrip-view" data-testid="filmstrip">
    <div className="fs-filmstrip-focus">
      <section className="fs-frame-stage">
        <header><div><b>{shot.code} · {shot.title}</b><span>{formatTime(shot.startSeconds)}-{formatTime(shot.endSeconds)} · {shot.durationSeconds}s · 镜头 r{shot.version}{panel ? ` · 画格 P${panel.order}-r${panel.version}` : ''}</span></div><div className="fs-frame-toggle"><button className={frameMode === 'annotated' ? 'is-active' : ''} onClick={() => setFrameMode('annotated')}>带标注故事板</button><button className={frameMode === 'clean' ? 'is-active' : ''} onClick={() => setFrameMode('clean')}>干净参考帧</button></div></header>
        <button className="fs-frame-preview" onClick={() => previewAsset && onPreview(previewAsset)} disabled={!previewAsset}>{displayedUrl ? <img src={displayedUrl} alt={`${shot.code} ${frameMode === 'clean' ? '干净参考帧' : '带标注故事板'}`} /> : <div><Film /><span>{frameMode === 'clean' ? '干净参考帧生成中' : '故事板画格生成中'}</span></div>}</button>
        {shot.panels.length > 1 && <div className="fs-panel-picker">{shot.panels.map(item => <button key={item.id} className={panel?.id === item.id ? 'is-active' : ''} onClick={() => setPanelId(item.id)}>{item.thumbnailUrl || item.cleanUrl ? <img src={item.thumbnailUrl || item.cleanUrl} alt={item.title} /> : <Film />}<span>P{item.order}</span></button>)}</div>}
        {panel && <section className="fs-candidate-strip" aria-label="画格版本候选"><header><span>版本候选</span><b>{candidateLoading ? '读取中' : `${candidates.length} 个`}</b></header><div>{candidates.map(candidate => <button key={candidate.id} className={candidate.isCurrent ? 'is-active' : ''} disabled={candidate.isCurrent} onClick={() => onMutate(() => api.selectPanelCandidate(storyboard.id, panel.id, candidate.id, storyboard.revision))}>{candidate.cleanUrl || candidate.annotatedUrl ? <img src={candidate.cleanUrl || candidate.annotatedUrl} alt={`画格候选 r${candidate.version}`} /> : <Film />}<span>r{candidate.version}{candidate.isCurrent ? ' · 当前' : ''}</span></button>)}</div></section>}
      </section>
      <section className="fs-shot-contract">
        <header><div><span>镜头合同</span><StatusPill status={shot.status} /></div><button onClick={() => setEditing(value => !value)}>{editing ? '取消编辑' : '编辑描述'}</button></header>
        {editing ? <form onSubmit={event => { event.preventDefault(); setEditing(false); onMutate(() => api.patchShot(storyboard.id, shot.id, { story_function: form.story_function, description: form.description, duration_seconds: numberValue(form.duration_seconds, shot.durationSeconds), camera_move: form.camera_move, action_start: form.action_start, action_result: form.action_end, sound: form.audio }, storyboard.revision)) }} className="fs-shot-form">
          <label>镜头功能<input value={form.story_function} onChange={event => setForm(current => ({ ...current, story_function: event.target.value }))} /></label>
          <label>完整画面<textarea value={form.description} onChange={event => setForm(current => ({ ...current, description: event.target.value }))} /></label>
          <div><label>镜头秒数<input type="number" min="4" max="15" value={form.duration_seconds} onChange={event => setForm(current => ({ ...current, duration_seconds: event.target.value }))} /></label><label>运镜<input value={form.camera_move} onChange={event => setForm(current => ({ ...current, camera_move: event.target.value }))} /></label></div>
          <label>动作起点<input value={form.action_start} onChange={event => setForm(current => ({ ...current, action_start: event.target.value }))} /></label>
          <label>动作终点<input value={form.action_end} onChange={event => setForm(current => ({ ...current, action_end: event.target.value }))} /></label>
          <label>声音<input value={form.audio} onChange={event => setForm(current => ({ ...current, audio: event.target.value }))} /></label>
          <button className="primary-action" type="submit"><Check />保存为新修订</button>
        </form> : <div className="fs-contract-fields">
          <ContractRow label="镜头功能" value={shot.storyFunction} />
          <ContractRow label="画面" value={shot.description} />
          <ContractRow label="主体与场景" value={`${shot.subject}；${shot.scene}`} />
          <ContractRow label="构图" value={shot.composition} />
          <ContractRow label="动作起止" value={`${shot.actionStart} → ${shot.actionEnd}`} />
          <ContractRow label="摄影" value={`${shot.shotSize} · ${shot.cameraAngle} · ${shot.lens}；${shot.cameraMove}`} />
          <ContractRow label="声音" value={shot.audio} />
          <ContractRow label="连续性" value={shot.continuity} />
          <ContractRow label="第一失败点" value={shot.firstFailureCue} tone="warn" />
        </div>}
        {!editing && <div className="fs-review-controls"><label>逐镜反馈<textarea value={feedback} onChange={event => setFeedback(event.target.value)} placeholder="指出要保留和要修改的画面、动作或机位" /></label><div>
          <button disabled={!panel} onClick={() => panel && onMutate(() => api.regeneratePanel(storyboard.id, panel.id, feedback || '按当前镜头合同重新生成本画格', storyboard.revision))}><RefreshCw />只重生成本画格</button>
          <button onClick={() => onMutate(() => api.regenerateShot(storyboard.id, shot.id, feedback || '按当前镜头合同重生成本镜头全部画格', storyboard.revision))}><Layers3 />重生成本镜头</button>
          <button disabled={!panel || !feedback.trim()} onClick={() => panel && onMutate(() => api.decideStoryboard(storyboard.id, { scope: 'panel', scopeId: panel.id, decision: 'revision_required', feedback, expectedVersion: storyboard.revision }))}><MessageSquareText />退回画格</button>
          <button disabled={!panel} onClick={() => panel && onMutate(() => api.decideStoryboard(storyboard.id, { scope: 'panel', scopeId: panel.id, decision: 'approved', expectedVersion: storyboard.revision }))}><Check />批准画格</button>
          <button className="primary-action" onClick={() => onMutate(() => api.decideStoryboard(storyboard.id, { scope: 'shot', scopeId: shot.id, decision: 'approved', expectedVersion: storyboard.revision }))}><BadgeCheck />批准本镜头</button>
        </div></div>}
      </section>
    </div>
    <div className="fs-shot-strip" aria-label="镜头顺序">{storyboard.shots.map(item => <button key={item.id} className={item.id === shot.id ? 'is-active' : ''} onClick={() => onSelectShot(item.id)}><span>{item.code}</span>{item.selectedCleanFrameUrl || item.imageUrl ? <img src={item.selectedCleanFrameUrl || item.imageUrl} alt={item.title} /> : <div><Film /></div>}<b>{item.title}</b><small>{item.durationSeconds}s · {statusText(item.status)}</small></button>)}</div>
  </div>
}

function AnimaticView({ storyboard, selectedShotId, onSelectShot, onMutate }: { storyboard: Storyboard; selectedShotId: string; onSelectShot: (id: string) => void; onMutate: (action: () => Promise<unknown>) => Promise<void> }) {
  return <div className="fs-animatic" data-testid="animatic-view">
    <section className="fs-animatic-player">{storyboard.animatic?.url ? <video src={storyboard.animatic.url} controls preload="metadata" /> : <div><Play /><b>动态预演为可选确认层</b><span>关键画面已经能说明预期时，可直接确认生产；需要核对节奏时再生成预演。</span></div>}</section>
    <div className="fs-animatic-meta"><div><b>动态预演 {storyboard.animatic ? `v${storyboard.animatic.version}` : ''}</b><span>{storyboard.totalDurationSeconds}s · {storyboard.shots.length} 镜 · 临时声音与节奏确认</span></div>{storyboard.animatic ? <button className={storyboard.animatic.confirmed ? 'is-confirmed' : 'primary-action'} disabled={storyboard.animatic.confirmed} onClick={() => onMutate(() => api.decideStoryboard(storyboard.id, { scope: 'animatic', scopeId: storyboard.animatic?.id || 'animatic', decision: 'approved', expectedVersion: storyboard.revision }))}>{storyboard.animatic.confirmed ? <><Check />已确认</> : <><CheckCircle2 />确认节奏</>}</button> : <button className="primary-action" onClick={() => onMutate(() => api.createAnimatic(storyboard.id, storyboard.revision))}><Play />生成预演</button>}</div>
    <div className="fs-timeline" aria-label="动态预演时间线"><div className="fs-timeline-ruler"><span>00:00</span><span>{formatTime(storyboard.totalDurationSeconds)}</span></div><div className="fs-timeline-track">{storyboard.shots.map(shot => <button key={shot.id} className={selectedShotId === shot.id ? 'is-active' : ''} style={{ flexGrow: Math.max(1, shot.durationSeconds) }} onClick={() => onSelectShot(shot.id)}><span>{shot.code}</span><b>{shot.storyFunction}</b><small>{shot.durationSeconds}s</small></button>)}</div><div className="fs-audio-track"><Volume2 /><span>临时 VO / 音乐 / 音效波形</span><i /></div></div>
  </div>
}

function ConversationMessage({ message, onPreview }: { message: ChatMessage; onPreview: (asset: PreviewItem) => void }) {
  return <article className={`fs-message ${message.role}`}><div className="message-author">{message.role === 'user' ? '你' : message.role === 'system' ? '系统' : 'Hook Studio'}<time>{new Date(message.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</time></div>{message.text && <div className="message-text">{message.text}</div>}{message.attachments.length > 0 && <div className="message-attachments">{message.attachments.map(item => <a key={item.id} href={item.url || undefined} target="_blank" rel="noreferrer"><AttachmentGlyph kind={item.kind} />{item.kind === 'image' && item.url ? <img src={item.thumbnailUrl || item.url} alt={item.name} /> : item.kind === 'video' && item.url ? <video src={item.url} muted preload="metadata" /> : null}<span>{item.name}<small>{item.extractedText ? '已解析' : '已接收'}</small></span></a>)}</div>}{message.assets.length > 0 && <div className="fs-message-assets">{message.assets.map(asset => <button key={asset.id} onClick={() => onPreview(asset)}>{asset.type === 'video' ? <video src={asset.url} muted preload="metadata" /> : <img src={asset.thumbnailUrl || asset.url} alt={asset.name} />}<span>{asset.name}</span></button>)}</div>}{message.storyboard && <div className="fs-board-handoff"><Film /><div><b>故事板 {message.storyboard.version} 已写入工作区</b><span>{message.storyboard.shots.length} 个镜头 · 请在下方逐镜确认</span></div></div>}</article>
}

function AssetLibrary({ assets, onPreview }: { assets: PreviewItem[]; onPreview: (asset: PreviewItem) => void }) {
  const groups = [
    { role: 'upload', label: '客户素材' }, { role: 'research', label: '研究证据' },
    { role: 'annotated', label: '带标注故事板' }, { role: 'clean', label: '干净参考帧' }, { role: 'animatic', label: '动态预演' },
  ]
  return <div className="fs-asset-library">{groups.map(group => { const rows = assets.filter(asset => asset.role === group.role || (group.role === 'upload' && !asset.role)); if (!rows.length) return null; return <section key={group.role}><header><span>{group.label}</span><b>{rows.length}</b></header><div>{rows.map(asset => <button key={asset.id} onClick={() => onPreview(asset)}>{asset.type === 'video' ? <video src={asset.url} muted preload="metadata" /> : asset.type === 'audio' ? <Volume2 /> : <img src={asset.thumbnailUrl || asset.url} alt={asset.name} />}<span>{asset.name}</span></button>)}</div></section>})}{!assets.length && <div className="fs-inspector-empty"><Archive /><span>素材会按职责出现在这里</span></div>}</div>
}

function PreviewPane({ preview, storyboard, selectedShotId, frameMode }: { preview?: PreviewItem; storyboard?: Storyboard; selectedShotId: string; frameMode: 'annotated' | 'clean' }) {
  const shot = storyboard?.shots.find(item => item.id === selectedShotId)
  const panel = shot?.panels[0]
  const fallbackUrl = frameMode === 'clean' ? panel?.cleanUrl || shot?.selectedCleanFrameUrl : panel?.annotatedUrl
  const fallback: PreviewItem | undefined = fallbackUrl ? { id: `${shot?.id}-${frameMode}`, type: 'image', name: `${shot?.code} ${frameMode === 'clean' ? '干净参考帧' : '带标注故事板'}`, url: fallbackUrl } : undefined
  const item = preview || fallback
  return <section className="fs-preview-pane"><header><div><span>选中预览</span><b>{item?.name || '尚未选择资产'}</b></div>{item && <a href={item.url} download title="下载"><Download /></a>}</header>{item ? <MediaPreview asset={item} /> : <div className="fs-inspector-empty"><Eye /><span>从资产库或分镜带选择内容</span></div>}{shot && <div className="fs-preview-shot"><span>{shot.code} · r{shot.version}</span><b>{shot.title}</b><p>{shot.description}</p></div>}</section>
}

function FinalLibrary({ assets, selected, setSelected, onPreview, onDownload }: { assets: PreviewItem[]; selected: Set<string>; setSelected: React.Dispatch<React.SetStateAction<Set<string>>>; onPreview: (asset: PreviewItem) => void; onDownload: () => void }) {
  function toggle(id: string) { setSelected(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next }) }
  return <section className="fs-final-library"><header><div><span>已批准成品</span><b>{assets.length} 项</b></div><button onClick={() => setSelected(selected.size === assets.length ? new Set() : new Set(assets.map(asset => asset.id)))}>{selected.size === assets.length && assets.length ? <CheckCircle2 /> : <CircleDashed />}{selected.size}/{assets.length}</button></header><div className="fs-final-grid">{assets.map(asset => <article key={asset.id} className={selected.has(asset.id) ? 'is-selected' : ''}><button onClick={() => onPreview(asset)}>{asset.type === 'video' ? <video src={asset.url} muted preload="metadata" /> : <img src={asset.thumbnailUrl || asset.url} alt={asset.name} />}</button><div><span>{asset.name}</span><button onClick={() => toggle(asset.id)} title="选择成品">{selected.has(asset.id) ? <CheckCircle2 /> : <CircleDashed />}</button></div></article>)}</div>{!assets.length && <div className="fs-inspector-empty"><PackageCheck /><span>通过质检的成品会进入这里</span></div>}<button className="batch-download" disabled={!selected.size} onClick={onDownload}><Download />批量下载 {selected.size ? `(${selected.size})` : ''}</button></section>
}

function ProductionConfirm({ storyboard, onCancel, onConfirm }: { storyboard: Storyboard; onCancel: () => void; onConfirm: () => void }) {
  return <div className="fs-modal-backdrop" role="presentation"><section className="fs-production-confirm" role="dialog" aria-modal="true" aria-labelledby="production-confirm-title"><header><LockKeyhole /><div><span>真实生产确认</span><h2 id="production-confirm-title">提交 {storyboard.shots.length} 个已批准镜头</h2></div></header><p>将按已冻结的干净参考帧和镜头合同进入生产，预计占用 {storyboard.estimatedVideoUnits} 条视频额度。失败提交不会扣除额度。</p><CoveragePills storyboard={storyboard} /><footer><button onClick={onCancel}>返回检查</button><button className="primary-action" onClick={onConfirm}><Check />确认并开始生产</button></footer></section></div>
}

function DurationQuestion({ onChoose, onCustom }: { onChoose: (seconds: number) => void; onCustom: () => void }) {
  return <article className="fs-message assistant duration-question"><div className="message-author">Hook Studio</div><div className="message-text">这支成片准备做多长？可直接填写 4-60 秒，系统会自动拆成 4-15 秒镜头，并按复杂度返回关键画面、动作序列或动态预演。</div><div className="duration-options">{[6, 10, 15, 30, 60].map(seconds => <button key={seconds} onClick={() => onChoose(seconds)}>{seconds}s</button>)}<button onClick={onCustom}>直接填写</button></div></article>
}

function StreamBadge({ state }: { state: StreamState }) {
  const labels: Record<StreamState, string> = { idle: '等待任务', connecting: '连接事件', live: '实时同步', recovering: '恢复快照' }
  return <em className={`fs-stream-badge is-${state}`}><i />{labels[state]}</em>
}

function StatusPill({ status }: { status: string }) { return <em className={`fs-status is-${status}`}>{statusText(status)}</em> }
function statusText(status: string) { return ({ queued: '排队中', running: '执行中', waiting_confirmation: '待确认', succeeded: '已完成', cancelled: '已取消', draft: '待绘制', drawing: '绘制中', generating: '生成中', review: '待审核', pending: '待审核', approved: '已批准', confirmed: '已确认', revision_required: '需修改', locked: '已锁定', producing: '生产中', qc: '质检中', completed: '已通过', failed: '可重试' } as Record<string, string>)[status] || '处理中' }

function taggedFile(file: File, role: 'source' | 'mask' | 'annotation') {
  return new File([file], `${role}-${file.name}`, { type: file.type, lastModified: file.lastModified })
}
function ContractRow({ label, value, tone }: { label: string; value: string; tone?: string }) { return <div className={tone ? `is-${tone}` : ''}><span>{label}</span><p>{value}</p></div> }
function shotForm(shot: StoryboardShot) { return { story_function: shot.storyFunction, description: shot.description, duration_seconds: String(shot.durationSeconds), camera_move: shot.cameraMove, action_start: shot.actionStart, action_end: shot.actionEnd, audio: shot.audio } }
function formatTime(seconds: number) { const safe = Math.max(0, Math.round(seconds)); return `${String(Math.floor(safe / 60)).padStart(2, '0')}:${String(safe % 60).padStart(2, '0')}` }
function formatDuration(seconds: number) { return seconds >= 60 ? `${Math.floor(seconds / 60)}分${String(seconds % 60).padStart(2, '0')}秒` : `${seconds}秒` }
function stageIndex(label: string) {
  if (/质检|交付|合成/.test(label)) return 7
  if (/预演|animatic/i.test(label)) return 6
  if (/参考帧|关键帧|绘图|图像/.test(label)) return 5
  if (/连续|锁定|校验/.test(label)) return 4
  if (/分镜|镜头/.test(label)) return 3
  if (/节拍|脚本|商业/.test(label)) return 2
  if (/研究|检索|搜索|参考/.test(label)) return 1
  return 0
}

function MediaPreview({ asset }: { asset: PreviewItem }) {
  if (asset.type === 'video') return <video className="preview-media" src={asset.url} poster={asset.thumbnailUrl} controls autoPlay muted />
  if (asset.type === 'audio') return <div className="audio-preview"><Volume2 /><audio src={asset.url} controls /></div>
  if (asset.type === 'document') return <a className="document-preview" href={asset.url} target="_blank" rel="noreferrer"><FileText /><span>{asset.name}</span></a>
  return <img className="preview-media" src={asset.url} alt={asset.name} />
}

function AttachmentGlyph({ kind }: { kind: AttachmentKind }) {
  if (kind === 'image') return <ImageIcon />
  if (kind === 'video') return <Film />
  if (kind === 'audio') return <Volume2 />
  if (kind === 'link') return <LinkIcon />
  return <FileText />
}

function QuotaLine({ icon, label, used, limit }: { icon: React.ReactNode; label: string; used: number; limit: number }) {
  const percent = Math.min(100, used / Math.max(1, limit) * 100)
  return <div className="quota-line"><div>{icon}<span>{label}</span><b>{used}/{limit}</b></div><i><span style={{ width: `${percent}%` }} /></i></div>
}

function EmptyConversation() { return <div className="empty-conversation"><div className="empty-mark">HS</div><h2>开始一个图片或视频任务</h2><p>上传素材或描述目标。系统会先确认需求，再按复杂度返回关键画面、动作序列或动态预演。</p><div><span><Paperclip />多格式素材</span><span><Film />镜头确认</span><span><Timer />可选动态预演</span></div></div> }
function SmallLoader({ label }: { label: string }) { return <div className="small-loader"><LoaderCircle className="spin" /><span>{label}</span></div> }
