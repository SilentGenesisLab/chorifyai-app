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

test('公网客户工作台呈现全镜头确认链、双队列和三类资产视图', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chrome')
  expect((await page.request.get('/hook-studio/api/studio/bootstrap')).status()).toBe(401)
  await login(page, CLIENT_CODE)

  await expect(page.getByRole('button', { name: '新建任务' })).toBeVisible()
  await expect(page.locator('.account-dock')).toContainText('图片额度')
  await expect(page.locator('.account-dock')).toContainText('视频额度')
  await expect(page.getByRole('navigation', { name: '资产视图' })).toContainText('资产库')
  await expect(page.getByRole('navigation', { name: '资产视图' })).toContainText('预览板')
  await expect(page.getByRole('navigation', { name: '资产视图' })).toContainText('成品库')
  await expect(page.locator('.fs-queue-snapshot').first()).toContainText('图片队列')
  await expect(page.locator('.fs-queue-snapshot').first()).toContainText('视频队列')

  const workbench = page.getByTestId('storyboard-workbench')
  if (await workbench.count()) {
    await expect(workbench).toBeVisible()
    await expect(workbench.getByRole('button', { name: '镜头表' })).toBeVisible()
    await expect(workbench.getByRole('button', { name: '分镜带' })).toBeVisible()
    await expect(workbench.getByRole('button', { name: '动态预演', exact: true })).toBeVisible()
  }

  await page.getByLabel('创作需求').fill('制作一条产品演示视频')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText(/这支成片准备做多长/)).toBeVisible()
  await page.getByRole('button', { name: '直接填写' }).click()
  await page.getByLabel('成片时长（秒）').fill('60')
  await expect(page.getByLabel('成片时长（秒）')).toHaveValue('60')
  await page.screenshot({ path: testInfo.outputPath('customer-full-storyboard-mvp.png'), fullPage: true })
})

test('公网管理后台显示账号额度、全镜头运行表和训练数据资产', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chrome')
  await login(page, ADMIN_CODE)
  await expect(page.getByRole('heading', { name: '今日运行概览' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '账号与额度' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '训练数据资产' })).toBeVisible()
  await expect(page.getByText('分镜画格')).toBeVisible()
  await expect(page.getByText('审批记录')).toBeVisible()
  await expect(page.getByText('能力运行')).toBeVisible()
  await expect(page.getByRole('link', { name: '导出训练 JSONL' })).toBeVisible()
  await expect(page.getByRole('link', { name: '导出事件 JSONL' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('admin-full-storyboard-mvp.png'), fullPage: true })
})

test('移动端登录封面和左右抽屉均在视口内', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chrome')
  await page.goto('./')
  await expect(page.locator('.hs-login__visual')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('mobile-login.png'), fullPage: true })
  await page.getByLabel('访问码').fill(CLIENT_CODE)
  await page.getByRole('button', { name: '进入工作台' }).click()
  await page.getByTitle('打开对话列表').click()
  await expect(page.locator('.fs-rail')).toHaveClass(/is-open/)
  const left = await page.locator('.fs-rail').boundingBox()
  expect(left && left.x >= 0 && left.x + left.width <= 390).toBeTruthy()
  await page.locator('.fs-rail .rail-close').click()
  await page.getByTitle('打开资产与预览').click()
  await expect(page.locator('.fs-inspector')).toHaveClass(/is-open/)
  const right = await page.locator('.fs-inspector').boundingBox()
  expect(right && right.x >= 0 && right.x + right.width <= 390).toBeTruthy()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.screenshot({ path: testInfo.outputPath('mobile-drawers.png'), fullPage: true })
})
