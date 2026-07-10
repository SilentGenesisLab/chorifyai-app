import { expect, test } from '@playwright/test'

const CLIENT_CODE = process.env.HOOK_STUDIO_E2E_CLIENT_CODE || ''

test('公网真实模型各生成三次并通过 skill 与视频 QC', async ({ page }, testInfo) => {
  test.skip(!process.env.PLAYWRIGHT_REAL_ACCEPTANCE || testInfo.project.name !== 'desktop-chrome')
  test.setTimeout(950_000)

  expect((await page.request.get('/hook-studio/api/studio/bootstrap')).status()).toBe(401)
  await page.goto('./')
  await page.getByLabel('访问码').fill(CLIENT_CODE)
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page.getByRole('heading', { name: '制作一个新钩子' })).toBeVisible()

  const created: Array<{ id: string; mode: 'image' | 'video' }> = []
  const prompts = [
    ['pain-point', '便携桌面灯，手指按下触摸开关，随后灯光亮起并照亮键盘'],
    ['visual-impact', '便携桌面灯，手掌拿起产品，随后触摸开关并展示柔和灯光'],
    ['handheld-proof', '便携桌面灯，单手按下开关，随后光线覆盖桌面并展示小巧体积'],
  ] as const
  for (const mode of ['image', 'video'] as const) {
    for (const [preset_id, prompt_user] of prompts) {
      const response = await page.request.post('/hook-studio/api/studio/jobs', {
        multipart: { mode, preset_id, prompt_user, ...(mode === 'video' ? { duration: '5' } : {}) },
      })
      expect(response.status()).toBe(202)
      created.push({ id: (await response.json()).job.id, mode })
    }
  }

  let jobs: Array<Record<string, unknown>> = []
  await expect.poll(async () => {
    jobs = (await (await page.request.get('/hook-studio/api/studio/jobs')).json()).items
    const ids = new Set(created.map(item => item.id))
    return jobs.filter(job => ids.has(String(job.id)) && ['succeeded', 'failed'].includes(String(job.status))).length
  }, { timeout: 900_000, intervals: [5_000, 10_000, 10_000] }).toBe(6)

  const ids = new Set(created.map(item => item.id))
  const accepted = jobs.filter(job => ids.has(String(job.id)))
  expect(accepted.filter(job => job.mode === 'image' && job.status === 'succeeded'), JSON.stringify(accepted, null, 2)).toHaveLength(3)
  const videos = accepted.filter(job => job.mode === 'video' && job.status === 'succeeded')
  expect(videos, JSON.stringify(accepted, null, 2)).toHaveLength(3)
  for (const video of videos) {
    expect((video.skill_trace as { passed?: boolean }).passed).toBeTruthy()
    expect((video.result_meta as { qc?: { passed?: boolean } }).qc?.passed).toBeTruthy()
  }
  await page.reload()
  await expect(page.locator('.gallery-card').first()).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('public-real-gallery.png'), fullPage: true })
})
