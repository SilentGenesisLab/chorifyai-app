import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, CircleAlert, LoaderCircle, ShieldCheck } from 'lucide-react'
import { ApiError, api } from '../api'
import type { Session } from '../types'

const SLIDES = [
  {
    src: '/hook-studio/login/creative-workstation.jpg',
    alt: '带有多块显示器的创意剪辑工作台',
    label: '创意拆解',
    copy: '从参考到可执行生产方案',
  },
  {
    src: '/hook-studio/login/editor-workstation.jpg',
    alt: '剪辑师正在专业工作台上制作视频',
    label: '视频生产',
    copy: '分镜确认后再进入批量生产',
  },
  {
    src: '/hook-studio/login/editing-timeline.jpg',
    alt: '视频剪辑软件中的多轨时间线',
    label: '交片管理',
    copy: '任务、素材与结果留在同一工作流',
  },
] as const

export interface LoginProps {
  onLogin: (session: Session) => void
}

export default function Login({ onLogin }: LoginProps) {
  const [active, setActive] = useState(0)
  const [failed, setFailed] = useState<Set<number>>(() => new Set())
  const [paused, setPaused] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const available = useMemo(() => SLIDES.map((_, index) => index).filter(index => !failed.has(index)), [failed])

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReducedMotion(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    if (reducedMotion || paused || available.length < 2) return
    const timer = window.setInterval(() => {
      setActive(current => {
        const position = Math.max(0, available.indexOf(current))
        return available[(position + 1) % available.length]
      })
    }, 6500)
    return () => window.clearInterval(timer)
  }, [available, paused, reducedMotion])

  useEffect(() => {
    if (failed.has(active) && available.length) setActive(available[0])
  }, [active, available, failed])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!code.trim()) {
      setError('请输入访问码')
      return
    }
    setBusy(true)
    setError('')
    try {
      onLogin(await api.login(code.trim()))
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '无法连接服务，请稍后重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="hs-login">
      <style>{LOGIN_STYLES}</style>
      <section
        className="hs-login__visual"
        aria-label="Hook Studio 创意生产场景"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onFocusCapture={() => setPaused(true)}
        onBlurCapture={() => setPaused(false)}
      >
        <div className="hs-login__fallback" aria-hidden="true" />
        {SLIDES.map((slide, index) => !failed.has(index) && (
          <img
            key={slide.src}
            className={index === active ? 'hs-login__slide is-active' : 'hs-login__slide'}
            src={slide.src}
            alt={slide.alt}
            loading={index === 0 ? 'eager' : 'lazy'}
            fetchPriority={index === 0 ? 'high' : 'auto'}
            onError={() => setFailed(current => new Set(current).add(index))}
          />
        ))}
        <div className="hs-login__veil" aria-hidden="true" />
        <div className="hs-login__brand">
          <span className="hs-login__monogram">HS</span>
          <span>Hook Studio</span>
        </div>
        <div className="hs-login__story" aria-live="polite">
          <p>{SLIDES[active]?.label ?? '创意生产'}</p>
          <h1>{SLIDES[active]?.copy ?? '把创意变成可交付素材'}</h1>
        </div>
        {available.length > 1 && (
          <div className="hs-login__pagination" aria-label="切换封面">
            {available.map(index => (
              <button
                key={SLIDES[index].src}
                className={index === active ? 'is-active' : ''}
                type="button"
                aria-label={`查看第 ${index + 1} 张封面`}
                aria-current={index === active ? 'true' : undefined}
                onClick={() => setActive(index)}
              />
            ))}
          </div>
        )}
      </section>

      <section className="hs-login__entry">
        <div className="hs-login__entry-inner">
          <div className="hs-login__mobile-brand"><span>HS</span><b>Hook Studio</b></div>
          <p className="hs-login__eyebrow">创意生产工作台</p>
          <h2>欢迎回来</h2>
          <p className="hs-login__intro">使用团队访问码进入工作台。</p>
          <form onSubmit={submit} className="hs-login__form">
            <label htmlFor="hook-studio-access-code">访问码</label>
            <input
              id="hook-studio-access-code"
              name="access-code"
              type="password"
              autoComplete="current-password"
              value={code}
              onChange={event => setCode(event.target.value)}
              placeholder="请输入团队访问码"
              disabled={busy}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? 'hook-studio-login-error' : undefined}
              autoFocus
            />
            {error && <div id="hook-studio-login-error" className="hs-login__error" role="alert"><CircleAlert />{error}</div>}
            <button type="submit" disabled={busy}>
              {busy ? <><LoaderCircle className="hs-login__spin" />正在验证</> : <>进入工作台<ArrowRight /></>}
            </button>
          </form>
          <p className="hs-login__security"><ShieldCheck />访问码只在服务端完成验证</p>
        </div>
      </section>
    </main>
  )
}

const LOGIN_STYLES = `
  .hs-login { min-height: 100dvh; display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(390px, .55fr); background: #f9fafb; color: #111827; letter-spacing: 0; }
  .hs-login * { box-sizing: border-box; letter-spacing: 0; }
  .hs-login__visual { position: relative; min-height: 100dvh; overflow: hidden; isolation: isolate; background: #18181b; }
  .hs-login__fallback { position: absolute; inset: 0; z-index: -3; background: #27272a; }
  .hs-login__slide { position: absolute; inset: 0; z-index: -2; width: 100%; height: 100%; object-fit: cover; object-position: center; opacity: 0; transform: scale(1.015); transition: opacity 850ms ease, transform 7s ease; }
  .hs-login__slide.is-active { opacity: 1; transform: scale(1); }
  .hs-login__veil { position: absolute; inset: 0; z-index: -1; background: rgba(9, 12, 17, .48); }
  .hs-login__brand { position: absolute; top: 32px; left: 36px; display: flex; align-items: center; gap: 12px; color: #fff; font-size: 15px; font-weight: 650; }
  .hs-login__monogram, .hs-login__mobile-brand span { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid rgba(255, 255, 255, .55); background: rgba(17, 24, 39, .72); color: #fff; border-radius: 8px; font-size: 12px; font-weight: 750; }
  .hs-login__story { position: absolute; left: clamp(36px, 6vw, 88px); right: clamp(36px, 8vw, 120px); bottom: clamp(76px, 12vh, 132px); color: #fff; max-width: 690px; }
  .hs-login__story p { margin: 0 0 14px; color: rgba(255, 255, 255, .78); font-size: 13px; font-weight: 650; }
  .hs-login__story h1 { margin: 0; max-width: 15ch; font-size: clamp(34px, 4.6vw, 68px); line-height: 1.08; font-weight: 650; }
  .hs-login__pagination { position: absolute; left: clamp(36px, 6vw, 88px); bottom: 42px; display: flex; gap: 8px; }
  .hs-login__pagination button { width: 30px; height: 12px; padding: 0; border: 0; background: transparent; cursor: pointer; position: relative; }
  .hs-login__pagination button::after { content: ''; position: absolute; inset: 5px 0; background: rgba(255,255,255,.38); transition: background-color 180ms ease; }
  .hs-login__pagination button.is-active::after { background: #fff; }
  .hs-login__pagination button:focus-visible { outline: 2px solid #fff; outline-offset: 3px; }
  .hs-login__entry { display: grid; align-items: center; min-width: 0; padding: 48px clamp(30px, 4vw, 64px); background: #fff; border-left: 1px solid #e5e7eb; }
  .hs-login__entry-inner { width: min(100%, 390px); margin: 0 auto; }
  .hs-login__mobile-brand { display: none; align-items: center; gap: 10px; margin-bottom: 44px; }
  .hs-login__mobile-brand span { border-color: #d1d5db; background: #111827; }
  .hs-login__eyebrow { margin: 0 0 10px; color: #4f46e5; font-size: 12px; font-weight: 700; }
  .hs-login__entry h2 { margin: 0; font-size: 32px; line-height: 1.2; font-weight: 650; }
  .hs-login__intro { margin: 12px 0 32px; color: #6b7280; font-size: 14px; }
  .hs-login__form { display: grid; gap: 10px; }
  .hs-login__form label { font-size: 13px; font-weight: 650; }
  .hs-login__form input { width: 100%; height: 48px; padding: 0 14px; border: 1px solid #d1d5db; border-radius: 8px; background: #fff; color: #111827; font: inherit; font-size: 14px; outline: none; }
  .hs-login__form input:focus { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79, 70, 229, .13); }
  .hs-login__form input[aria-invalid='true'] { border-color: #dc2626; }
  .hs-login__form button { height: 48px; margin-top: 6px; border: 0; border-radius: 8px; display: flex; align-items: center; justify-content: center; gap: 9px; background: #111827; color: #fff; font: inherit; font-size: 14px; font-weight: 650; cursor: pointer; }
  .hs-login__form button:hover:not(:disabled) { background: #4f46e5; }
  .hs-login__form button:focus-visible { outline: 3px solid rgba(79, 70, 229, .25); outline-offset: 2px; }
  .hs-login__form button:disabled { opacity: .62; cursor: wait; }
  .hs-login__form svg, .hs-login__security svg, .hs-login__error svg { width: 17px; height: 17px; flex: 0 0 auto; }
  .hs-login__error { min-height: 34px; display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 8px; background: #fef2f2; color: #b91c1c; font-size: 12px; }
  .hs-login__security { margin: 18px 0 0; display: flex; align-items: center; gap: 7px; color: #6b7280; font-size: 12px; }
  .hs-login__spin { animation: hs-login-spin 900ms linear infinite; }
  @keyframes hs-login-spin { to { transform: rotate(360deg); } }
  @media (max-width: 860px) {
    .hs-login { grid-template-columns: 1fr; }
    .hs-login__visual { min-height: 38dvh; }
    .hs-login__brand { top: 22px; left: 22px; }
    .hs-login__story { left: 22px; right: 22px; bottom: 48px; }
    .hs-login__story h1 { max-width: 19ch; font-size: clamp(27px, 8vw, 42px); }
    .hs-login__pagination { left: 22px; bottom: 18px; }
    .hs-login__entry { min-height: 62dvh; padding: 38px 24px 46px; border-left: 0; border-top: 1px solid #e5e7eb; align-items: start; }
  }
  @media (max-width: 520px) {
    .hs-login__visual { min-height: 31dvh; }
    .hs-login__brand { display: none; }
    .hs-login__story { bottom: 40px; }
    .hs-login__story p { margin-bottom: 8px; }
    .hs-login__story h1 { font-size: 27px; }
    .hs-login__pagination { bottom: 14px; }
    .hs-login__entry { min-height: 69dvh; padding-top: 28px; }
    .hs-login__mobile-brand { display: flex; margin-bottom: 30px; }
    .hs-login__entry h2 { font-size: 28px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .hs-login__slide, .hs-login__pagination button::after { transition: none; transform: none; }
    .hs-login__spin { animation-duration: 1.8s; }
  }
`
