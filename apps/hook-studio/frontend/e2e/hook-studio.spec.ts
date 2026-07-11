import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const CLIENT_CODE = process.env.HOOK_STUDIO_E2E_CLIENT_CODE || 'local-client-code'
const ADMIN_CODE = process.env.HOOK_STUDIO_E2E_ADMIN_CODE || 'local-admin-code'


async function login(page: Page, code: string) {
  await page.goto('./')
  await page.getByLabel('访问码').fill(code)
  await page.getByRole('button', { name: '进入工作台' }).click()
}


test('无码 API 为 401，客户进入新版全镜头工作台', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chrome')
  const unauthorized = await page.request.get('/hook-studio/api/studio/bootstrap')
  expect(unauthorized.status()).toBe(401)

  await login(page, CLIENT_CODE)
  await expect(page.getByRole('button', { name: '新建任务' })).toBeVisible()
  await expect(page.locator('.account-dock')).toContainText('图片额度')
  await expect(page.locator('.account-dock')).toContainText('视频额度')
  await expect(page.getByLabel('创作需求')).toBeVisible()
  await expect(page.getByRole('navigation', { name: '资产视图' })).toContainText('资产库')
  await expect(page.getByRole('navigation', { name: '资产视图' })).toContainText('预览板')
  await expect(page.getByRole('navigation', { name: '资产视图' })).toContainText('成品库')

  const health = await page.request.get('/hook-studio/api/health')
  expect(health.ok()).toBeTruthy()
  const payload = await health.json()
  expect(payload.queues.image.concurrency).toBe(2)
  expect(payload.queues.video.concurrency).toBe(2)

  await page.screenshot({ path: testInfo.outputPath('customer-workspace.png'), fullPage: true })
})


test('管理员可查看客户、用量和服务状态', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chrome')
  await login(page, ADMIN_CODE)
  await expect(page.getByRole('heading', { name: '今日运行概览' })).toBeVisible()
  await expect(page.locator('tbody tr').first()).toBeVisible()
  await expect(page.getByText('全站视频', { exact: true })).toBeVisible()
  await expect(page.getByText('服务健康')).toBeVisible()
  await expect(page.getByRole('link', { name: '导出完整数据包' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('admin-dashboard.png'), fullPage: true })
})
