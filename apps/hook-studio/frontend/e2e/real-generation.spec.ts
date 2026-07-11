import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'

const CLIENT_CODE = process.env.HOOK_STUDIO_E2E_CLIENT_CODE || ''
const API = '/hook-studio/api/studio'

type JsonRecord = Record<string, any>

async function login(page: Page) {
  await page.goto('./')
  await page.getByLabel('访问码').fill(CLIENT_CODE)
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page.getByRole('button', { name: '新建任务' })).toBeVisible()
}

async function waitTask(request: APIRequestContext, taskId: string, wanted: Set<string>, timeoutMs: number) {
  const deadline = Date.now() + timeoutMs
  let task: JsonRecord = {}
  while (Date.now() < deadline) {
    try {
      const response = await request.get(`${API}/tasks/${taskId}`, { timeout: 30_000 })
      if (response.status() === 200) {
        task = await response.json()
        if (wanted.has(String(task.status))) return task
      } else if (response.status() < 500) {
        expect(response.status()).toBe(200)
      }
    } catch (error) {
      task = { ...task, transient_poll_error: String(error) }
    }
    await new Promise(resolve => setTimeout(resolve, 5_000))
  }
  throw new Error(`任务 ${taskId} 等待超时，最后状态 ${JSON.stringify(task)}`)
}

async function createTask(page: Page, tool: 'create_image' | 'create_video', duration?: number) {
  const title = `MVP真实验收-${tool}-${duration || 'image'}-${Date.now()}`
  const conversationResponse = await page.request.post(`${API}/conversations`, { data: { title } })
  expect(conversationResponse.status()).toBe(200)
  const conversation = await conversationResponse.json()
  const response = await page.request.post(`${API}/conversations/${conversation.id}/messages`, {
    multipart: {
      text: tool === 'create_image'
        ? '美区家居场景中的便携桌面灯产品首帧，真实商业摄影，清晰展示手指触碰开关和灯光结果'
        : '美区家居工作台中的便携桌面灯广告，保持产品比例，清楚展示手指接触、灯光亮起和桌面被照亮的动作因果，原生环境声和动作音',
      tool,
      links: '[]',
      ...(duration ? { duration_seconds: String(duration) } : {}),
    },
    headers: { 'Idempotency-Key': `acceptance-${conversation.id}` },
    timeout: 60_000,
  })
  expect(response.status()).toBe(202)
  return { conversationId: String(conversation.id), task: (await response.json()).task as JsonRecord }
}

async function reusableAcceptanceTasks(page: Page) {
  const response = await page.request.get(`${API}/conversations`)
  expect(response.status()).toBe(200)
  const conversations = ((await response.json()).items || []) as JsonRecord[]
  const matching = conversations.filter(item => String(item.title || '').startsWith('MVP真实验收-'))
  const groups = await Promise.all(matching.map(async conversation => {
    const tasks = await page.request.get(`${API}/tasks?conversation_id=${conversation.id}`)
    expect(tasks.status()).toBe(200)
    return ((await tasks.json()).items || []) as JsonRecord[]
  }))
  return groups.flat().filter(task => task.status !== 'failed')
}

async function approveAndProduce(page: Page, task: JsonRecord) {
  let current = await waitTask(
    page.request, String(task.id), new Set(['queued', 'running', 'waiting_confirmation', 'succeeded', 'failed']), 30_000,
  )
  if (current.status === 'succeeded' || current.status === 'failed') return current
  if (current.storyboard_id && current.status !== 'waiting_confirmation' && current.stage !== '等待确认') {
    return waitTask(page.request, String(task.id), new Set(['succeeded', 'failed']), 900_000)
  }
  const planned = current.status === 'waiting_confirmation' ? current : await waitTask(
    page.request, String(task.id), new Set(['waiting_confirmation', 'succeeded', 'failed']), 900_000,
  )
  if (planned.status === 'succeeded' || planned.status === 'failed') return planned
  expect(planned.status, JSON.stringify(planned)).toBe('waiting_confirmation')
  const boardId = String(planned.storyboard_id || planned.storyboardId)
  expect(boardId).toBeTruthy()
  let response = await page.request.get(`${API}/storyboards/${boardId}`)
  expect(response.status()).toBe(200)
  let board = await response.json() as JsonRecord
  const revision = Number(board.revision)

  for (const shot of board.shots as JsonRecord[]) {
    for (const panel of shot.panels as JsonRecord[]) {
      response = await page.request.post(`${API}/storyboards/${boardId}/decisions`, {
        data: {
          expected_version: revision, scope: 'panel', target_id: panel.id,
          decision: 'approved', feedback: '真实验收批准', idempotency_key: `accept-panel-${panel.id}-r${revision}`,
        },
      })
      expect(response.status()).toBe(200)
    }
    response = await page.request.post(`${API}/storyboards/${boardId}/decisions`, {
      data: {
        expected_version: revision, scope: 'shot', target_id: shot.id,
        decision: 'approved', feedback: '真实验收批准', idempotency_key: `accept-shot-${shot.id}-r${revision}`,
      },
    })
    expect(response.status()).toBe(200)
  }
  response = await page.request.post(`${API}/storyboards/${boardId}/decisions`, {
    data: {
      expected_version: revision, scope: 'storyboard', target_id: boardId,
      decision: 'approved', idempotency_key: `accept-board-${boardId}-r${revision}`,
    },
  })
  expect(response.status()).toBe(200)
  response = await page.request.post(`${API}/storyboards/${boardId}/animatic`, {
    data: { expected_version: revision, confirm: true }, timeout: 240_000,
  })
  expect(response.status(), await response.text()).toBe(200)
  board = await response.json()
  expect(board.animatic?.confirmed || board.animatic?.status === 'confirmed').toBeTruthy()
  response = await page.request.post(`${API}/storyboards/${boardId}/produce`, {
    data: { expected_version: revision }, timeout: 60_000,
  })
  expect(response.status(), await response.text()).toBe(202)
  return waitTask(page.request, String(task.id), new Set(['succeeded', 'failed']), 900_000)
}

test('公网新 MVP 真实图片三次、视频三次并含多镜拼接与结构化质检', async ({ page }, testInfo) => {
  test.skip(!process.env.PLAYWRIGHT_REAL_ACCEPTANCE || !CLIENT_CODE || testInfo.project.name !== 'desktop-chrome')
  test.setTimeout(1_000_000)

  expect((await page.request.get(`${API}/bootstrap`)).status()).toBe(401)
  await login(page)

  const reusable = await reusableAcceptanceTasks(page)
  const imageSubmissions: Array<{ task: JsonRecord; conversationId?: string }> = reusable.filter(task => task.tool === 'create_image').slice(0, 3).map(task => ({ task }))
  const videoSubmissions: Array<{ task: JsonRecord; conversationId?: string }> = reusable.filter(task => task.tool === 'create_video').slice(0, 3).map(task => ({ task }))
  while (imageSubmissions.length < 3) imageSubmissions.push(await createTask(page, 'create_image'))
  const missingDurations = [4, 4, 16].filter(duration => !videoSubmissions.some(item => Number(item.task.params?.duration_seconds) === duration))
  while (videoSubmissions.length < 3) videoSubmissions.push(await createTask(page, 'create_video', missingDurations.shift() || 4))

  const images = await Promise.all(imageSubmissions.map(item => waitTask(
    page.request, String(item.task.id), new Set(['succeeded', 'failed']), 600_000,
  )))
  expect(images.every(item => item.status === 'succeeded'), JSON.stringify(images, null, 2)).toBeTruthy()

  const videos = await Promise.all(videoSubmissions.map(item => approveAndProduce(page, item.task)))
  expect(videos.every(item => item.status === 'succeeded'), JSON.stringify(videos, null, 2)).toBeTruthy()
  for (const task of videos) {
    const assets = (task.result?.assets || []) as JsonRecord[]
    expect(assets.length).toBeGreaterThan(0)
    expect(assets[0].metadata?.qc?.passed).toBeTruthy()
  }
  const multiShot = videos.find(item => Number(item.params?.duration_seconds) === 16) || videos[2]
  expect((multiShot.result?.assets?.[0]?.metadata?.segments || []).length).toBeGreaterThanOrEqual(2)

  await page.reload()
  await expect(page.getByTestId('storyboard-workbench')).toBeVisible({ timeout: 30_000 })
  await page.screenshot({ path: testInfo.outputPath('public-real-full-storyboard-mvp.png'), fullPage: true })
})
