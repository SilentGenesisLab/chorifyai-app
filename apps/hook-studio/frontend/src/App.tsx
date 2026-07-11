import { useCallback, useEffect, useState } from 'react'
import { CircleAlert, Clock3, Download, FileText, Gauge, LoaderCircle, LogOut, RefreshCw, Settings2, ShieldCheck, Users } from 'lucide-react'
import { ApiError, api } from './api'
import FullStoryboardWorkspace from './components/FullStoryboardWorkspace'
import Login from './components/Login'
import { arrayValue, normalizeUsage, numberValue, record } from './storyboard'
import type { ClientUsage, Session, Usage } from './types'

const EMPTY_USAGE: Usage = {
  globalVideoUsed: 0, globalVideoLimit: 100, clientVideoUsed: 0, clientVideoLimit: 100,
  imageUsed: 0, imageLimit: 1000, resetAt: '',
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [checking, setChecking] = useState(true)
  useEffect(() => { api.session().then(setSession).catch(() => setSession(null)).finally(() => setChecking(false)) }, [])
  if (checking) return <FullLoader label="正在连接工作台" />
  if (!session) return <Login onLogin={setSession} />
  if (session.role === 'admin' || location.pathname.endsWith('/admin')) return <Admin session={session} onLogout={() => setSession(null)} />
  return <FullStoryboardWorkspace session={session} onLogout={() => setSession(null)} />
}

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
      const data = await api.admin()
      const raw = record(data)
      const healthData = record(raw.health)
      setClients(arrayValue(raw.clients).map(value => {
        const item = record(value)
        return {
          id: String(item.id || item.code_id), name: String(item.name || item.client_name), enabled: Boolean(item.enabled),
          videoUsed: numberValue(item.video_used), videoLimit: numberValue(item.video_limit || item.daily_video_limit, 100),
          imageUsed: numberValue(item.image_used), imageLimit: numberValue(item.image_limit || item.daily_image_limit, 1000), downloads: numberValue(item.downloads),
        }
      }))
      const backupData = healthData.backup || raw.backup
      const backupLabel = typeof backupData === 'string' ? backupData : record(backupData).verified ? `已验证 · ${String(record(backupData).created_at || '').slice(0, 10)}` : '暂无记录'
      setUsage(normalizeUsage(Array.isArray(raw.usage) ? raw.usage[0] : raw.usage))
      setHealth(String(healthData.database || raw.health || '正常'))
      setBackup(backupLabel)
      setTables(record(raw.tables) as Record<string, number>)
      setError('')
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
      <section className="admin-table-section data-assets"><header><div><h2>训练数据资产</h2><p>对话、附件、镜头、审批、编辑合同和结果均已结构化入库。</p></div><FileText /></header><div className="data-counts"><span>对话<b>{numberValue(tables.conversations)}</b></span><span>消息<b>{numberValue(tables.messages)}</b></span><span>素材<b>{numberValue(tables.assets)}</b></span><span>任务<b>{numberValue(tables.task_runs)}</b></span><span>镜头<b>{numberValue(tables.storyboard_shots)}</b></span><span>分镜画格<b>{numberValue(tables.storyboard_panels)}</b></span><span>图片编辑合同<b>{numberValue(tables.image_edit_contracts)}</b></span><span>资产版本<b>{numberValue(tables.asset_versions)}</b></span><span>审批<b>{numberValue(tables.approval_decisions)}</b></span><span>能力运行<b>{numberValue(tables.skill_runs)}</b></span><span>训练样本<b>{numberValue(tables.training_examples)}</b></span></div><div className="data-actions"><a href={api.dataExportUrl()}><Download />导出完整数据包</a><a href={api.trainingExportUrl()}><Download />导出训练 JSONL</a><a href={api.eventsExportUrl()}><Download />导出事件 JSONL</a></div></section>
    </main>
  </div>
}

function Metric({ icon, label, value, note }: { icon: React.ReactNode; label: string; value: string; note: string }) { return <article className="admin-metric"><div>{icon}<span>{label}</span></div><b>{value}</b><small>{note}</small></article> }
function QuotaEditor({ used, limit, max, onSave }: { used: number; limit: number; max: number; onSave: (value: number) => Promise<unknown> }) {
  const [value, setValue] = useState(String(limit))
  return <label className="quota-editor"><span>{used}/</span><input aria-label="每日额度" type="number" min="0" max={max} value={value} onChange={event => setValue(event.target.value)} onBlur={async () => { const next = Math.max(0, Math.min(max, numberValue(value, limit))); setValue(String(next)); if (next !== limit) await onSave(next) }} /></label>
}
function FullLoader({ label }: { label: string }) { return <div className="full-loader"><span>HS</span><LoaderCircle className="spin" /><p>{label}</p></div> }
function SmallLoader({ label }: { label: string }) { return <div className="small-loader"><LoaderCircle className="spin" /><span>{label}</span></div> }
