import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

const FRAME_A = '/hook-studio/login/creative-workstation.jpg'
const FRAME_B = '/hook-studio/login/editor-workstation.jpg'

function makeBoard() {
  const shots = Array.from({ length: 8 }, (_, index) => {
    const ordinal = index + 1
    const approved = ordinal < 8
    return {
      id: `shot-${ordinal}`,
      shot_id: `shot-${ordinal}`,
      code: `S${String(ordinal).padStart(2, '0')}`,
      ordinal,
      version: 1,
      title: ordinal === 1 ? '痛点瞬间' : ordinal === 8 ? '产品定格与行动引导' : `产品证明 ${ordinal}`,
      story_function: ordinal === 1 ? '前三秒钩子' : ordinal === 8 ? '品牌收束' : '动作与结果证明',
      description: `美国居家场景中，主体位于画面中心，产品保持真实比例；镜头 ${ordinal} 清楚展示动作因果和可见结果。`,
      subject: '真实使用者与客户产品',
      scene: '自然光居家工作台，背景干净且空间关系明确',
      composition: '前景为手部动作，中景为产品，背景提供真实使用环境，视觉重心落在产品触点',
      action_start: '手部进入画面并接近产品',
      action_end: '动作完成，产品结果稳定可见',
      shot_size: ordinal % 2 ? '近景' : '中景',
      camera_angle: '平视略低机位',
      lens: '自然透视',
      camera_move: ordinal % 2 ? '缓慢推进至产品触点' : '固定机位保持证据可信',
      audio: '现场环境声、动作音效与简短英文口播',
      transition: ordinal === 1 ? '动作切入下一镜' : '结果匹配切换',
      continuity: '产品外观、手部方向、场景光线和屏幕方向保持连续',
      first_failure_cue: '产品比例漂移或动作终点不可见即退回',
      duration_seconds: 5,
      start_seconds: index * 5,
      end_seconds: ordinal * 5,
      status: approved ? 'approved' : 'review',
      approval: approved ? { id: `approval-shot-${ordinal}`, status: 'approved', version: 1 } : undefined,
      selected_clean_frame_url: ordinal % 2 ? FRAME_A : FRAME_B,
      panels: (['start', 'action', 'result'] as const).map((role, panelIndex) => ({
        id: `panel-${ordinal}-${panelIndex + 1}`, shot_id: `shot-${ordinal}`, ordinal: panelIndex + 1,
        logical_key: role, role, required: true,
        title: `${ordinal}${String.fromCharCode(65 + panelIndex)} ${role === 'start' ? '动作起点' : role === 'action' ? '关键动作' : '可见结果'}`,
        description: `${role === 'start' ? '动作起点' : role === 'action' ? '关键动作过程' : '动作结果'}、构图和摄影机方向均已标注`,
        moment: role === 'start' ? '动作起点' : role === 'action' ? '关键动作' : '动作结果',
        annotated_url: (ordinal + panelIndex) % 2 ? FRAME_B : FRAME_A,
        clean_url: (ordinal + panelIndex) % 2 ? FRAME_A : FRAME_B,
        selected_candidate_id: `candidate-${ordinal}-${panelIndex + 1}`, send_to_provider: approved,
        status: 'approved', version: 1,
        approval: { id: `approval-panel-${ordinal}-${panelIndex + 1}`, status: 'approved', version: 1 },
      })),
    }
  })
  return {
    id: 'board-1', storyboard_id: 'board-1', task_id: 'task-1', conversation_id: 'conversation-1',
    version: 3, revision: 3, status: 'review', board_approved: false, total_duration_seconds: 40, estimated_video_units: 8,
    brief: '为美区短视频制作 40 秒产品钩子，先确认完整故事板和动态预演，再进入真实生产。',
    summary: '痛点钩子、动作证明、结果展示和行动引导组成完整说服链。',
    coverage: { shot_total: 8, shot_ready: 8, panel_required: 24, panel_ready: 24, panels_total: 24, panels_approved: 24, clean_ready: 8, approved_shots: 7 },
    production_guard: { can_produce: false, blockers: ['仍有镜头等待批准', '整板尚未批准', '动态预演尚未确认'] },
    animatic: { id: 'animatic-1', status: 'review', duration_seconds: 40, version: 1, confirmed: false },
    skill_runs: [
      { id: 'skill-1', public_label: '素材理解', status: 'succeeded', output_count: 5, public_message: '素材职责已识别', provider: 'hidden-vendor-credential' },
      { id: 'skill-2', public_label: '联网研究', status: 'succeeded', output_count: 6, public_message: '公开参考已形成证据卡', model: 'hidden-model-identifier' },
      { id: 'skill-3', public_label: '商业节拍', status: 'succeeded', output_count: 8, public_message: '说服链与时长已分配' },
      { id: 'skill-4', public_label: '分镜设计', status: 'running', output_count: 8, public_message: '正在等待最后一个镜头确认' },
    ],
    shots,
  }
}

async function installMockApi(page: Page) {
  let loggedIn = false
  const board = makeBoard()
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  await page.route('**/hook-studio/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace('/hook-studio/api', '')
    const method = request.method()

    if (path === '/auth/session' || path === '/auth/me') return loggedIn ? json(route, { principal: { role: 'client', client_name: '北美剪辑组', code_id: 'client-demo' } }) : json(route, { detail: 'Unauthorized' }, 401)
    if (path === '/auth/login' && method === 'POST') { loggedIn = true; return json(route, { principal: { role: 'client', client_name: '北美剪辑组', code_id: 'client-demo' } }) }
    if (path === '/auth/logout') { loggedIn = false; return json(route, {}) }
    if (!loggedIn) return json(route, { detail: 'Unauthorized' }, 401)

    if (path === '/studio/bootstrap') return json(route, {
      usage: { client_video_used: 12, client_video_limit: 100, image_used: 86, image_limit: 1000, global_video_used: 22, global_video_limit: 100 },
      queues: {
        image_queued: 2, image_running: 1, image_succeeded: 11, image_failed: 1,
        video_queued: 3, video_running: 1, video_succeeded: 7, video_failed: 1,
        waiting_approval: 4, succeeded: 18, failed: 2,
      },
    })
    if (path === '/studio/conversations') return json(route, { items: [{ id: 'conversation-1', title: '便携照明产品 · 40秒', last_message: '等待最后确认', updated_at: '2026-07-11T10:00:00Z' }] })
    if (path === '/studio/conversations/conversation-1/messages') return json(route, { items: [
      { id: 'message-1', conversation_id: 'conversation-1', role: 'user', kind: 'text', text: '制作一条面向美区用户的产品钩子，强调动作证明和真实使用场景。', created_at: '2026-07-11T09:58:00Z', attachments: [] },
      { id: 'message-2', conversation_id: 'conversation-1', role: 'assistant', kind: 'storyboard', text: '已完成需求理解与全镜头规划，请逐镜确认。', task_id: 'task-1', storyboard: board, created_at: '2026-07-11T10:00:00Z' },
    ] })
    if (path === '/studio/tasks') return json(route, { items: [{ id: 'task-1', conversation_id: 'conversation-1', storyboard_id: 'board-1', title: '全镜头故事板', status: 'running', public_stage: '分镜设计', created_at: '2026-07-11T10:00:00Z', heartbeat_at: '2026-07-11T10:00:08Z' }] })
    if (path === '/studio/tasks/task-1') return json(route, { id: 'task-1', conversation_id: 'conversation-1', storyboard_id: 'board-1', title: '全镜头故事板', status: 'running', public_stage: '分镜设计', created_at: '2026-07-11T10:00:00Z' })
    if (path === '/studio/tasks/task-1/events') return route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no' },
      body: `id: event-1\nevent: hook.event.v1\ndata: ${JSON.stringify({ schema: 'hook.event.v1', id: 'event-1', task_id: 'task-1', type: 'provider.waiting', public_label: '分镜设计', message: '已完成 8/8 个镜头合同，等待确认', indeterminate: true, waited_seconds: 17, occurred_at: '2026-07-11T10:00:08Z', heartbeat_at: '2026-07-11T10:00:08Z' })}\n\n`,
    })
    if (path === '/studio/storyboards/board-1' && method === 'GET') return json(route, board)

    if (path.includes('/shots/') && path.endsWith('/regenerate') && method === 'POST') {
      const shotId = path.split('/').at(-2)
      const shot = board.shots.find(item => item.id === shotId)
      if (shot) {
        shot.version += 1
        shot.status = 'review'
        shot.approval = undefined
        shot.panels.forEach(panel => { panel.version += 1; panel.status = 'review'; panel.approval = undefined })
      }
      board.coverage.approved_shots = board.shots.filter(item => item.status === 'approved').length
      board.coverage.panels_approved = board.shots.flatMap(item => item.panels).filter(item => item.status === 'approved').length
      board.revision += 1; board.version = board.revision
      return json(route, board)
    }
    if (path.includes('/panels/') && path.endsWith('/regenerate') && method === 'POST') {
      const panelId = path.split('/').at(-2)
      for (const shot of board.shots) {
        const panel = shot.panels.find(item => item.id === panelId)
        if (panel) { panel.version += 1; panel.status = 'review'; panel.approval = undefined }
      }
      board.coverage.panels_approved = board.shots.flatMap(item => item.panels).filter(item => item.status === 'approved').length
      board.revision += 1; board.version = board.revision
      return json(route, board)
    }
    if (path.includes('/panels/') && path.endsWith('/candidates') && method === 'GET') {
      const panelId = path.split('/panels/')[1].split('/')[0]
      const current = board.shots.flatMap(item => item.panels).find(item => item.id === panelId)
      if (!current) return json(route, { detail: 'Not found' }, 404)
      const candidates = [{ ...current, revision: current.version, clean_url: current.clean_url, annotated_url: current.annotated_url, is_current: true }]
      if (current.version > 1) candidates.push({ ...current, id: `${current.id}-history-r1`, revision: 1, clean_url: current.annotated_url, annotated_url: current.clean_url, is_current: false })
      return json(route, { current_panel_id: current.id, logical_key: current.logical_key, candidates })
    }
    if (path.includes('/candidates/') && path.endsWith('/select') && method === 'POST') {
      const panelId = path.split('/panels/')[1].split('/')[0]
      const current = board.shots.flatMap(item => item.panels).find(item => item.id === panelId)
      if (!current) return json(route, { detail: 'Not found' }, 404)
      current.version += 1; current.status = 'review'; current.approval = undefined
      board.coverage.panels_approved = board.shots.flatMap(item => item.panels).filter(item => item.status === 'approved').length
      board.revision += 1; board.version = board.revision
      return json(route, board)
    }
    if (path.endsWith('/decisions') && method === 'POST') {
      const input = request.postDataJSON() as { scope: string; target_id: string; scope_id: string; approved: boolean }
      const targetId = input.target_id || input.scope_id
      if (input.scope === 'shot') {
        const shot = board.shots.find(item => item.id === targetId)
        if (shot) { shot.status = 'approved'; shot.approval = { id: `approved-${shot.id}`, status: 'approved', version: shot.version } }
        board.coverage.approved_shots = board.shots.filter(item => item.status === 'approved').length
      }
      if (input.scope === 'panel') {
        for (const shot of board.shots) {
          const panel = shot.panels.find(item => item.id === targetId)
          if (panel) panel.status = input.approved ? 'approved' : 'revision_required'
        }
        board.coverage.panels_approved = board.shots.flatMap(item => item.panels).filter(item => item.status === 'approved').length
      }
      if (input.scope === 'storyboard') board.board_approved = true
      if (input.scope === 'animatic') { board.animatic.status = 'confirmed'; board.animatic.confirmed = true }
      board.production_guard.can_produce = board.coverage.approved_shots === 8 && board.coverage.panels_approved === board.coverage.panels_total && board.board_approved && board.animatic.confirmed
      board.production_guard.blockers = board.production_guard.can_produce ? [] : [
        ...(board.coverage.approved_shots < 8 ? ['仍有镜头等待批准'] : []),
        ...(board.coverage.panels_approved < board.coverage.panels_total ? ['仍有必需画格等待批准'] : []),
        ...(!board.board_approved ? ['整板尚未批准'] : []),
        ...(!board.animatic.confirmed ? ['动态预演尚未确认'] : []),
      ]
      return json(route, board)
    }
    if (path.endsWith('/animatic') && method === 'POST') return json(route, board)
    if (path.endsWith('/produce') && method === 'POST') { board.status = 'producing'; return json(route, board) }
    if (path.includes('/shots/') && method === 'PATCH') {
      const shotId = path.split('/').at(-1)
      const shot = board.shots.find(item => item.id === shotId)
      if (shot) { Object.assign(shot, request.postDataJSON()); shot.version += 1 }
      board.revision += 1; board.version = board.revision
      return json(route, board)
    }
    if (path === '/studio/assets/batch-download') return json(route, { download_url: FRAME_A })
    return json(route, { items: [] })
  })
}

async function login(page: Page) {
  await page.goto('./')
  await page.getByLabel('访问码').fill('local-client-code')
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page.getByTestId('storyboard-workbench')).toBeVisible()
}

test.beforeEach(async ({ page }) => installMockApi(page))

test('全镜头故事板三视图同步、逐镜修订、审批与生产门禁', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chrome')
  await login(page)

  await expect(page.getByTestId('coverage-summary').first()).toContainText('镜头 8/8')
  await expect(page.getByTestId('coverage-summary').first()).toContainText('干净帧 8/8')
  await expect(page.getByTestId('production-button')).toBeDisabled()
  await expect(page.getByTestId('execution-card')).toContainText('实时同步')
  await expect(page.getByTestId('execution-card')).toContainText('已完成 8/8 个镜头合同')
  await expect(page.getByLabel('任务等待中，无虚假百分比')).toBeVisible()
  await expect(page.getByTestId('queue-snapshot')).toContainText('图片队列等待 2执行 1')
  await expect(page.getByTestId('queue-snapshot')).toContainText('视频队列等待 3执行 1')
  await expect(page.getByTestId('queue-snapshot')).toContainText('图片队列等待 2执行 1成功 11失败 1')
  await expect(page.getByTestId('queue-snapshot')).toContainText('视频队列等待 3执行 1成功 7失败 1')
  await expect(page.getByTestId('queue-snapshot')).toContainText('待确认 4成功 18失败 2')

  await page.getByRole('button', { name: '镜头表' }).click()
  await expect(page.getByTestId('shot-table')).toBeVisible()
  await page.getByTestId('shot-table').getByText('S04').click()
  await page.getByRole('button', { name: '分镜带' }).click()
  await expect(page.getByTestId('filmstrip')).toContainText('S04')
  await page.getByTestId('filmstrip').locator('.fs-frame-toggle').getByRole('button', { name: '干净参考帧' }).click()
  await expect(page.getByTestId('filmstrip').getByAltText('S04 干净参考帧')).toBeVisible()

  await page.getByLabel('逐镜反馈').fill('保持产品外观，只把动作终点展示得更清楚')
  await page.getByRole('button', { name: '只重生成本画格' }).click()
  await expect(page.getByTestId('filmstrip')).toContainText('画格 P1-r2')
  await expect(page.locator('.fs-candidate-strip')).toContainText('r1')
  await page.locator('.fs-candidate-strip button', { hasText: /^r1$/ }).click()
  await expect(page.getByTestId('filmstrip')).toContainText('画格 P1-r3')
  await page.getByLabel('逐镜反馈').fill('')
  await page.getByRole('button', { name: '批准画格' }).click()

  await page.locator('.fs-shot-strip button', { hasText: 'S08' }).click()
  await page.getByRole('button', { name: '批准本镜头' }).click()
  await expect(page.getByTestId('coverage-summary').first()).toContainText('已批准 8/8')
  await expect(page.getByTestId('production-button')).toBeDisabled()
  await page.getByRole('button', { name: '批准整板' }).click()
  await expect(page.getByTestId('production-button')).toBeDisabled()

  await page.getByTestId('storyboard-workbench').getByRole('button', { name: '动态预演', exact: true }).click()
  await expect(page.getByTestId('animatic-view')).toBeVisible()
  await page.getByRole('button', { name: '确认节奏' }).click()
  await expect(page.getByTestId('production-button')).toBeEnabled()

  await page.getByTestId('production-button').click()
  await expect(page.getByRole('dialog', { name: '提交 8 个已批准镜头' })).toBeVisible()
  await expect(page.getByRole('dialog')).toContainText('预计占用 8 条视频额度')
  await page.screenshot({ path: 'test-results/full-storyboard-production-confirm.png', fullPage: true })

  await expect(page.getByRole('navigation', { name: '资产视图' })).toContainText('资产库')
  await expect(page.getByRole('navigation', { name: '资产视图' })).toContainText('预览板')
  await expect(page.getByRole('navigation', { name: '资产视图' })).toContainText('成品库')
  await expect(page.locator('body')).not.toContainText(/hidden-vendor-credential|hidden-model-identifier/i)
  await page.getByRole('button', { name: '返回检查' }).click()
  await page.getByTestId('storyboard-workbench').getByRole('button', { name: '分镜带', exact: true }).click()
  await page.screenshot({ path: 'test-results/full-storyboard-desktop.png', fullPage: true })
  await page.getByTitle('退出登录').click()
})

test('移动端工作台、分镜带和左右抽屉无横向溢出', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chrome')
  await login(page)
  await expect(page.getByTestId('filmstrip')).toBeVisible()

  await page.getByTitle('打开对话列表').click()
  await expect(page.locator('.fs-rail')).toHaveClass(/is-open/)
  await page.waitForTimeout(250)
  const left = await page.locator('.fs-rail').boundingBox()
  expect(left && left.x >= 0 && left.x + left.width <= 390).toBeTruthy()
  await page.locator('.fs-rail .rail-close').click()

  await page.getByTitle('打开资产与预览').click()
  await expect(page.locator('.fs-inspector')).toHaveClass(/is-open/)
  await page.waitForTimeout(250)
  const right = await page.locator('.fs-inspector').boundingBox()
  expect(right && right.x >= 0 && right.x + right.width <= 390).toBeTruthy()
  await page.locator('.fs-inspector .rail-close').click()

  await page.getByTestId('storyboard-workbench').getByRole('button', { name: '动态预演', exact: true }).click()
  await expect(page.getByTestId('animatic-view')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.screenshot({ path: 'test-results/full-storyboard-mobile.png', fullPage: true })
  await page.getByTitle('打开对话列表').click()
  await page.getByTitle('退出登录').click()
})
