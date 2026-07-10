import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft, Check, ChevronRight, CircleAlert, Clock3, Download, Film, Gauge,
  Image as ImageIcon, LayoutGrid, LoaderCircle, LogOut, Play, Plus, RefreshCw,
  Settings2, ShieldCheck, Trash2, Upload, Users, X,
} from 'lucide-react'
import { ApiError, api } from './api'
import type { ClientUsage, Job, Mode, Preset, Session, Usage } from './types'

const FALLBACK_PRESETS: Preset[] = [
  { id: 'pain-point', name: '痛点直击', summary: '第一秒放大用户正在忍受的问题', costUnits: 1, accent: '#e05d3e' },
  { id: 'suspense', name: '悬念开场', summary: '先展示反常结果，再揭示产品', costUnits: 1, accent: '#d39a2d' },
  { id: 'contrast', name: '对比冲击', summary: '同画面呈现使用前后的强反差', costUnits: 1, accent: '#457e72' },
  { id: 'visual', name: '强视觉开场', summary: '用尺度、速度或材质制造停留', costUnits: 1, accent: '#486b9b' },
  { id: 'scenario', name: '真实使用场景', summary: '进入美区消费者熟悉的生活现场', costUnits: 1, accent: '#7b6755' },
  { id: 'handheld-proof', name: '手持动作证明', summary: '让手部动作直接证明核心卖点', costUnits: 1, accent: '#765d8c' },
]

const EMPTY_USAGE: Usage = { globalVideoUsed: 0, globalVideoLimit: 100, clientVideoUsed: 0, clientVideoLimit: 100, resetAt: '' }

function asRecord(value: unknown): Record<string, unknown> { return value && typeof value === 'object' ? value as Record<string, unknown> : {} }
function n(value: unknown, fallback = 0) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : fallback }
function normalizeUsage(raw: unknown): Usage {
  const r = asRecord(raw)
  return {
    globalVideoUsed: n(r.global_video_used ?? r.global_succeeded ?? r.video_used), globalVideoLimit: n(r.global_video_limit ?? r.global_limit ?? r.video_limit, 100),
    clientVideoUsed: n(r.client_video_used ?? r.client_succeeded ?? r.video_used), clientVideoLimit: n(r.client_video_limit ?? r.client_limit ?? r.video_limit, 100),
    resetAt: String(r.reset_at || ''),
  }
}
function normalizeJob(raw: unknown): Job {
  const r = asRecord(raw)
  return { id: String(r.id || r.job_id || ''), mode: r.mode === 'video' ? 'video' : 'image', presetId: String(r.preset_id || ''), presetName: String(r.preset_name || ''), status: (r.status || 'queued') as Job['status'], resultUrl: String(r.result_url || ''), thumbnailUrl: String(r.thumbnail_url || ''), queuePosition: n(r.queue_position) || undefined, etaSeconds: n(r.eta_seconds) || undefined, createdAt: String(r.created_at || new Date().toISOString()), errorMessage: String(r.error_message || '') }
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [checking, setChecking] = useState(true)
  useEffect(() => { api.session().then(setSession).catch(() => setSession(null)).finally(() => setChecking(false)) }, [])
  if (checking) return <FullLoader label="正在连接工作台" />
  if (!session) return <Login onLogin={setSession} />
  if (session.role === 'admin' || location.pathname.endsWith('/admin')) return <Admin session={session} onLogout={() => setSession(null)} />
  return <Studio session={session} onLogout={() => setSession(null)} />
}

function Login({ onLogin }: { onLogin: (s: Session) => void }) {
  const [code, setCode] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (!code.trim()) return setError('请输入访问码')
    setBusy(true); setError('')
    try { onLogin(await api.login(code.trim())) } catch (e) { setError(e instanceof ApiError ? e.message : '无法连接服务，请稍后重试') } finally { setBusy(false) }
  }
  return <main className="login-shell">
    <section className="login-panel">
      <div className="brand-mark"><span>HS</span></div>
      <div className="login-copy"><p className="eyebrow">创意生产工作台</p><h1>Hook Studio</h1><p>为美区 TikTok 快速制作 9:16 图片与视频钩子。</p></div>
      <form onSubmit={submit} className="login-form">
        <label htmlFor="access-code">访问码</label>
        <input id="access-code" name="access-code" type="password" autoComplete="current-password" value={code} onChange={e => setCode(e.target.value)} placeholder="请输入团队访问码" disabled={busy} />
        {error && <InlineError message={error} />}
        <button className="primary full" disabled={busy}>{busy ? <><LoaderCircle className="spin" />正在验证</> : <>进入工作台<ChevronRight /></>}</button>
      </form>
      <p className="security-note"><ShieldCheck />访问码仅用于服务端身份验证</p>
    </section>
    <aside className="login-visual" aria-hidden="true"><div className="frame-stack"><div className="frame frame-a"/><div className="frame frame-b"/><div className="frame frame-c"><span>9:16</span></div></div></aside>
  </main>
}

function Studio({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [mode, setMode] = useState<Mode>('image'); const [step, setStep] = useState(1); const [preset, setPreset] = useState('pain-point')
  const [prompt, setPrompt] = useState(''); const [reference, setReference] = useState<File>(); const [preview, setPreview] = useState('')
  const [presets, setPresets] = useState(FALLBACK_PRESETS); const [usage, setUsage] = useState(EMPTY_USAGE); const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true); const [submitting, setSubmitting] = useState(false); const [error, setError] = useState(''); const fileRef = useRef<HTMLInputElement>(null)
  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [boot, rawJobs] = await Promise.all([api.bootstrap(), api.jobs()]); const b = asRecord(boot)
      const sourcePresets = Array.isArray(b.presets) ? b.presets : []
      if (sourcePresets.length) setPresets(sourcePresets.map((p, i) => { const x = asRecord(p); const costs = asRecord(x.cost_units); return { id: String(x.id), name: String(x.name || x.label), summary: String(x.summary || FALLBACK_PRESETS[i % FALLBACK_PRESETS.length].summary), costUnits: n(costs[mode] ?? x.cost_units, 1), accent: FALLBACK_PRESETS[i % FALLBACK_PRESETS.length].accent } }))
      setUsage(normalizeUsage(b.usage)); setJobs((Array.isArray(rawJobs) ? rawJobs : []).map(normalizeJob)); setError('')
    } catch (e) { if (!silent) setError(e instanceof ApiError ? e.message : '工作台数据加载失败') } finally { setLoading(false) }
  }, [mode])
  useEffect(() => { load(); const timer = window.setInterval(() => load(true), 5000); return () => clearInterval(timer) }, [load])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  const active = jobs.filter(j => j.status === 'queued' || j.status === 'running')
  const gallery = jobs.filter(j => j.status === 'succeeded')
  const exhausted = mode === 'video' && (usage.globalVideoUsed >= usage.globalVideoLimit || usage.clientVideoUsed >= usage.clientVideoLimit)
  async function generate() {
    if (!prompt.trim()) return setError('请先用一句话描述产品和核心卖点')
    setSubmitting(true); setError('')
    try { const job = normalizeJob(await api.generate(mode, preset, prompt.trim(), reference)); setJobs(x => [job, ...x]); setStep(3) } catch (e) { setError(e instanceof ApiError ? `${e.message}${e.requestId ? `（请求 ${e.requestId}）` : ''}` : '提交失败，请稍后重试') } finally { setSubmitting(false) }
  }
  async function logout() { try { await api.logout() } finally { onLogout() } }
  async function jobAction(job: Job, action: 'regenerate' | 'delete') {
    try { if (action === 'delete') { await api.remove(job.id); setJobs(x => x.filter(j => j.id !== job.id)) } else { const next = normalizeJob(await api.action(job.id, 'regenerate')); setJobs(x => [next, ...x]) } } catch (e) { setError(e instanceof ApiError ? e.message : '操作失败，请重试') }
  }
  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="/hook-studio/"><span>HS</span><strong>Hook Studio</strong></a><div className="top-actions">
      <div className="quota"><Gauge/><div><b>今日视频 {usage.globalVideoUsed}/{usage.globalVideoLimit}</b><small>全站额度 · UTC+8 重置</small></div></div>
      <button className="icon-button" title="退出登录" onClick={logout}><LogOut/></button>
    </div></header>
    <main className="workspace">
      <div className="welcome"><div><p className="eyebrow">{session.clientName}</p><h1>制作一个新钩子</h1></div><div className="stepper">{['选择模式','配置创意','生成结果'].map((label, i) => <div key={label} className={step >= i + 1 ? 'step active' : 'step'}><span>{step > i + 1 ? <Check/> : i + 1}</span><b>{label}</b></div>)}</div></div>
      {error && <div className="banner-error"><CircleAlert/><span>{error}</span><button onClick={() => setError('')} title="关闭"><X/></button></div>}
      <section className="builder">
        <div className="builder-main">
          <div className="section-head"><span className="section-number">01</span><div><h2>选择生成模式</h2><p>图片和视频使用独立队列，互不占用并发。</p></div></div>
          <div className="mode-switch" role="radiogroup">
            <button role="radio" aria-checked={mode === 'image'} className={mode === 'image' ? 'mode-card selected' : 'mode-card'} onClick={() => { setMode('image'); setStep(Math.max(step, 1)) }}><ImageIcon/><div><b>图片钩子</b><small>9:16 高质首帧图 · 不限日量</small></div><span className="radio-dot"/></button>
            <button role="radio" aria-checked={mode === 'video'} className={mode === 'video' ? 'mode-card selected' : 'mode-card'} onClick={() => { setMode('video'); setStep(Math.max(step, 1)) }}><Film/><div><b>视频钩子</b><small>4-5 秒 · 原生动作与环境音</small></div><span className="radio-dot"/></button>
          </div>
          <div className="section-head"><span className="section-number">02</span><div><h2>选择钩子拍法</h2><p>预设内置完整拍摄结构，你只需补充产品信息。</p></div></div>
          <div className="preset-grid">{presets.map(p => <button key={p.id} className={preset === p.id ? 'preset selected' : 'preset'} onClick={() => { setPreset(p.id); setStep(2) }} style={{ '--accent': p.accent } as React.CSSProperties}><span className="preset-index">{String(presets.indexOf(p) + 1).padStart(2, '0')}</span><b>{p.name}</b><small>{p.summary}</small><em>{mode === 'video' ? '消耗 1 条视频额度' : '图片不限量'}</em><span className="preset-check"><Check/></span></button>)}</div>
          <div className="section-head"><span className="section-number">03</span><div><h2>描述你的产品</h2><p>写清产品、核心卖点和希望强调的动作。</p></div></div>
          <div className="input-zone"><label htmlFor="prompt">一句话产品描述</label><textarea id="prompt" value={prompt} maxLength={300} onChange={e => { setPrompt(e.target.value); setStep(2) }} placeholder="例如：一款可单手弹出卡片的金属钱包，重点展示快速取卡和小巧体积"/><span className="char-count">{prompt.length}/300</span></div>
          <div className="upload-row"><div><b>参考图</b><small>可选，上传清晰产品正面图效果更稳定</small></div><input ref={fileRef} hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={e => { const f = e.target.files?.[0]; setReference(f); if (preview) URL.revokeObjectURL(preview); setPreview(f ? URL.createObjectURL(f) : '') }}/>{preview ? <div className="upload-preview"><img src={preview} alt="参考图预览"/><button onClick={() => { setReference(undefined); setPreview(''); if (fileRef.current) fileRef.current.value = '' }} title="移除参考图"><X/></button></div> : <button className="secondary" onClick={() => fileRef.current?.click()}><Upload/>上传参考图</button>}</div>
          <div className="submit-row"><div className="submit-context"><ShieldCheck/><span>{mode === 'video' ? '提交前自动检查时长、画幅、动作因果与声音意图' : '图片任务进入独立队列，不占用视频额度'}</span></div><button className="primary generate" onClick={generate} disabled={submitting || exhausted || !prompt.trim()}>{submitting ? <><LoaderCircle className="spin"/>正在提交</> : exhausted ? '今日视频额度已用完' : <><Play/>开始生成</>}</button></div>
        </div>
        <aside className="queue-panel">
          <div className="queue-header"><div><h2>生成队列</h2><span>{active.length} 个任务进行中</span></div><button className="icon-button" onClick={() => load()} title="刷新队列"><RefreshCw/></button></div>
          {loading ? <SmallLoader label="读取队列"/> : active.length === 0 ? <EmptyState icon={<Clock3/>} title="队列空闲" text="提交生成后，可在这里查看位置和预计等待时间。"/> : <div className="queue-list">{active.map(j => <QueueItem key={j.id} job={j}/>)}</div>}
          <div className="queue-split"><div><ImageIcon/><span>图片队列</span><b>{active.filter(j => j.mode === 'image').length}</b></div><div><Film/><span>视频队列</span><b>{active.filter(j => j.mode === 'video').length}</b></div></div>
        </aside>
      </section>
      <section className="gallery-section"><div className="gallery-head"><div><p className="eyebrow">素材库</p><h2>最近生成</h2></div><span>{gallery.length} 个可用素材</span></div>
        {loading ? <SmallLoader label="加载素材"/> : gallery.length === 0 ? <EmptyState icon={<LayoutGrid/>} title="还没有生成结果" text="完成第一个钩子后，预览和下载会出现在这里。"/> : <div className="gallery-grid">{gallery.map(j => <GalleryCard key={j.id} job={j} onAction={jobAction}/>)}</div>}
      </section>
    </main>
  </div>
}

function QueueItem({ job }: { job: Job }) {
  const mins = job.etaSeconds ? Math.max(1, Math.ceil(job.etaSeconds / 60)) : null
  return <article className="queue-item"><div className={`queue-icon ${job.mode}`} >{job.mode === 'image' ? <ImageIcon/> : <Film/>}</div><div className="queue-body"><div><b>{job.presetName || (job.mode === 'image' ? '图片钩子' : '视频钩子')}</b><span className={`status ${job.status}`}>{job.status === 'running' ? '生成中' : '排队中'}</span></div><small>{job.status === 'queued' ? `前方 ${Math.max(0, (job.queuePosition || 1) - 1)} 个任务` : '模型正在处理素材'}</small><div className="progress"><span style={{ width: job.status === 'running' ? '62%' : '18%' }}/></div><em>{mins ? `预计约 ${mins} 分钟` : '正在估算等待时间'}</em></div></article>
}

function GalleryCard({ job, onAction }: { job: Job; onAction: (j: Job, a: 'regenerate' | 'delete') => void }) {
  const media = job.resultUrl || job.thumbnailUrl
  return <article className="gallery-card"><div className="media-frame">{media ? job.mode === 'video' ? <video src={media} poster={job.thumbnailUrl} controls preload="metadata"/> : <img src={media} alt={`${job.presetName || '钩子'}生成结果`}/> : <div className="media-placeholder"><ImageIcon/></div>}<span className="media-type">{job.mode === 'video' ? <><Film/>视频 9:16</> : <><ImageIcon/>图片 9:16</>}</span></div><div className="card-meta"><div><b>{job.presetName || '钩子素材'}</b><small>{new Date(job.createdAt).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</small></div><div className="card-actions"><a className="icon-button" href={api.downloadUrl(job.id)} title="下载"><Download/></a><button className="icon-button" onClick={() => onAction(job, 'regenerate')} title="重新生成"><RefreshCw/></button><button className="icon-button danger" onClick={() => onAction(job, 'delete')} title="从画廊删除"><Trash2/></button></div></div></article>
}

function Admin({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [clients, setClients] = useState<ClientUsage[]>([]); const [usage, setUsage] = useState(EMPTY_USAGE); const [health, setHealth] = useState('检查中'); const [backup, setBackup] = useState('检查中'); const [loading, setLoading] = useState(true); const [error, setError] = useState('')
  const load = useCallback(async () => { setLoading(true); try { const data = await api.admin(); const raw = asRecord(data); const healthData = asRecord(raw.health); const backupData = asRecord(healthData.backup || raw.backup); setClients((Array.isArray(raw.clients) ? raw.clients : []).map(x => { const c = asRecord(x); return { id: String(c.id || c.code_id), name: String(c.name || c.client_name), enabled: Boolean(c.enabled), videoUsed: n(c.video_used), videoLimit: n(c.video_limit ?? c.daily_video_limit, 100), downloads: n(c.downloads) } })); const usageSource = Array.isArray(raw.usage) ? asRecord(raw.usage[0]) : raw.usage; setUsage(normalizeUsage(usageSource)); setHealth(String(healthData.database || raw.health || '正常')); setBackup(String(backupData.archive || backupData.created_at || healthData.backup || raw.backup || '暂无记录')); setError('') } catch (e) { setError(e instanceof ApiError ? e.message : '管理数据加载失败') } finally { setLoading(false) } }, [])
  useEffect(() => { load() }, [load])
  async function patchClient(client: ClientUsage, patch: { enabled?: boolean; video_limit?: number }) { try { await api.updateClient(client.id, patch); await load() } catch (e) { setError(e instanceof ApiError ? e.message : '保存失败') } }
  async function logout() { try { await api.logout() } finally { onLogout() } }
  return <div className="app-shell admin-shell"><header className="topbar"><a className="brand" href="/hook-studio/"><span>HS</span><strong>Hook Studio</strong><em>管理后台</em></a><div className="top-actions"><span className="admin-name">{session.clientName}</span><button className="icon-button" title="退出登录" onClick={logout}><LogOut/></button></div></header><main className="admin-workspace">
    <div className="admin-title"><div><p className="eyebrow">运营控制台</p><h1>今日运行概览</h1></div><button className="secondary" onClick={load}><RefreshCw/>刷新数据</button></div>
    {error && <div className="banner-error"><CircleAlert/><span>{error}</span></div>}
    <div className="metric-grid"><Metric label="全站视频用量" value={`${usage.globalVideoUsed}/${usage.globalVideoLimit}`} note="UTC+8 每日重置" icon={<Gauge/>}/><Metric label="活跃客户" value={String(clients.filter(c => c.enabled).length)} note={`共 ${clients.length} 个访问码`} icon={<Users/>}/><Metric label="服务健康" value={health} note="队列与数据库" icon={<ShieldCheck/>}/><Metric label="最近备份" value={backup} note="SQLite 与事件日志" icon={<Clock3/>}/></div>
    <section className="admin-section"><div className="admin-section-head"><div><h2>客户访问码与配额</h2><p>用量由服务端强制扣减，停用后立即禁止新请求。</p></div><Settings2/></div>
      {loading ? <SmallLoader label="读取客户数据"/> : clients.length === 0 ? <EmptyState icon={<Users/>} title="暂无客户" text="在服务端访问码配置中添加客户后会显示在这里。"/> : <div className="table-wrap"><table><thead><tr><th>客户</th><th>今日视频</th><th>下载</th><th>日配额</th><th>访问状态</th></tr></thead><tbody>{clients.map(c => <tr key={c.id}><td><b>{c.name}</b><small>{c.id}</small></td><td><span className="usage-bar"><i style={{ width: `${Math.min(100, c.videoUsed / Math.max(1, c.videoLimit) * 100)}%` }}/></span><em>{c.videoUsed}/{c.videoLimit}</em></td><td>{c.downloads}</td><td><input className="quota-input" type="number" min="0" max="100" defaultValue={c.videoLimit} aria-label={`${c.name}日配额`} onBlur={e => { const value = Number(e.target.value); if (value !== c.videoLimit) patchClient(c, { video_limit: value }) }}/></td><td><button className={c.enabled ? 'toggle on' : 'toggle'} aria-pressed={c.enabled} onClick={() => patchClient(c, { enabled: !c.enabled })}><span/>{c.enabled ? '已启用' : '已停用'}</button></td></tr>)}</tbody></table></div>}
    </section>
    <section className="admin-section settings-row"><div><h2>全站视频日上限</h2><p>图片不受日量限制，图片与视频并发独立。</p></div><div className="global-setting"><input type="number" min="1" max="1000" value={usage.globalVideoLimit} onChange={e => setUsage(u => ({ ...u, globalVideoLimit: Number(e.target.value) }))}/><button className="primary" onClick={async () => { try { await api.updateGlobalLimit(usage.globalVideoLimit); await load() } catch (e) { setError(e instanceof ApiError ? e.message : '保存失败') } }}>保存上限</button></div></section>
  </main></div>
}

function Metric({ label, value, note, icon }: { label: string; value: string; note: string; icon: React.ReactNode }) { return <article className="metric"><div className="metric-icon">{icon}</div><span>{label}</span><b>{value}</b><small>{note}</small></article> }
function InlineError({ message }: { message: string }) { return <div className="inline-error" role="alert"><CircleAlert/>{message}</div> }
function FullLoader({ label }: { label: string }) { return <div className="full-loader"><div className="brand-mark"><span>HS</span></div><LoaderCircle className="spin"/><p>{label}</p></div> }
function SmallLoader({ label }: { label: string }) { return <div className="small-loader"><LoaderCircle className="spin"/><span>{label}</span></div> }
function EmptyState({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) { return <div className="empty-state"><div>{icon}</div><b>{title}</b><p>{text}</p></div> }
