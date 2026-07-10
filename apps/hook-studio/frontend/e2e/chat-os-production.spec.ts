import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const CLIENT_CODE = process.env.HOOK_STUDIO_E2E_CLIENT_CODE || ''
const ADMIN_CODE = process.env.HOOK_STUDIO_E2E_ADMIN_CODE || ''

async function login(page: Page, code: string) {
  await page.goto('./')
  await page.getByLabel('访问码').fill(code)
  await page.getByRole('button', { name: '进入工作台' }).click()
}

test.beforeEach(({}, testInfo) => {
  test.skip(!process.env.PLAYWRIGHT_EXTERNAL_SERVERS, '仅用于已部署环境验收')
  test.skip(!CLIENT_CODE || !ADMIN_CODE, '需要从服务端 secret 注入访问码')
  testInfo.setTimeout(90_000)
})

test('公网客户工作台呈现真实结果、额度、任务和任意时长回问', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chrome')
  expect((await page.request.get('/hook-studio/api/studio/bootstrap')).status()).toBe(401)
  await login(page, CLIENT_CODE)
  await expect(page.getByRole('button', { name: '新建对话' })).toBeVisible()
  await expect(page.locator('.account-dock')).toContainText('图片额度')
  await expect(page.locator('.account-dock')).toContainText('视频额度')

  await page.locator('.conversation-list button', { hasText: '真实验收-视频生产' }).click()
  await expect(page.locator('.message-media video').first()).toBeVisible()
  await page.locator('.message-media button').first().click()
  await expect(page.locator('video.preview-media')).toBeVisible()
  await expect.poll(() => page.locator('video.preview-media').evaluate(video => Number((video as HTMLVideoElement).duration) || 0)).toBeGreaterThan(0)
  await expect(page.locator('.task-count')).toHaveCount(4)
  await page.getByTitle('选择用于批量下载').first().click()
  await expect(page.getByRole('button', { name: /^批量下载/ })).toBeEnabled()

  await page.getByLabel('创作需求').fill('制作一条三分钟的产品演示视频')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText(/这支视频准备做多长/)).toBeVisible()
  await page.getByRole('button', { name: '自定义时长' }).click()
  await page.getByLabel('视频时长（秒）').fill('180')
  await expect(page.getByLabel('视频时长（秒）')).toHaveValue('180')
  await page.screenshot({ path: testInfo.outputPath('customer-chat-os.png'), fullPage: true })
})

test('公网管理后台显示账号额度和训练数据资产', async ({ page }, testInfo) => {
  await login(page, ADMIN_CODE)
  await expect(page.getByRole('heading', { name: '今日运行概览' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '账号与额度' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '训练数据资产' })).toBeVisible()
  await expect(page.getByRole('link', { name: '导出训练 JSONL' })).toBeVisible()
  await expect(page.getByRole('link', { name: '导出事件 JSONL' })).toBeVisible()
  await expect(page.getByLabel('每日额度').first()).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('admin-data-assets.png'), fullPage: true })
})

test('移动端左右抽屉不越界且登录封面可见', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chrome')
  await page.goto('./')
  await expect(page.locator('.hs-login__visual')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('mobile-login.png'), fullPage: true })
  await page.getByLabel('访问码').fill(CLIENT_CODE)
  await page.getByRole('button', { name: '进入工作台' }).click()
  await page.getByTitle('打开对话列表').click()
  await expect(page.locator('.conversation-rail')).toHaveClass(/is-open/)
  await page.waitForTimeout(300)
  const left = await page.locator('.conversation-rail').boundingBox()
  expect(left && left.x >= 0 && left.x + left.width <= 390).toBeTruthy()
  await page.locator('.conversation-rail .rail-close').click()
  await expect(page.locator('.conversation-rail')).not.toHaveClass(/is-open/)
  await page.getByTitle('打开任务与预览').click()
  await expect(page.locator('.inspector')).toHaveClass(/is-open/)
  await page.waitForTimeout(300)
  const right = await page.locator('.inspector').boundingBox()
  expect(right && right.x >= 0 && right.x + right.width <= 390).toBeTruthy()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.screenshot({ path: testInfo.outputPath('mobile-drawers.png'), fullPage: true })
})
