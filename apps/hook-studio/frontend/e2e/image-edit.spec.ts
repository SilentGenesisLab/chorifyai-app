import { expect, test } from '@playwright/test'

const CLIENT_CODE = process.env.HOOK_STUDIO_E2E_CLIENT_CODE || 'local-client-code'
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+Z9er2QAAAABJRU5ErkJggg==',
  'base64',
)

test('局部修图完成合同、进度、预览与成品入库', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chrome')
  await page.goto('./')
  await page.getByLabel('访问码').fill(CLIENT_CODE)
  await page.getByRole('button', { name: '进入工作台' }).click()
  await page.getByRole('button', { name: '新建任务' }).click()

  await page.locator('.tool-select select').selectOption('edit_image')
  await expect(page.locator('.fs-header')).toContainText('局部修图')
  const imageInputs = page.locator('input[type="file"][accept="image/*"]')
  await imageInputs.nth(0).setInputFiles({ name: 'face-mask-product.png', mimeType: 'image/png', buffer: PNG })
  await page.locator('input[type="file"][accept="image/png"]').setInputFiles({ name: 'selection.png', mimeType: 'image/png', buffer: PNG })
  await expect(page.locator('.composer-files')).toContainText('source-face-mask-product.png')
  await expect(page.locator('.composer-files')).toContainText('mask-selection.png')

  await page.getByLabel('创作需求').fill('只把选区内卡片改成绿色，保持其他内容不变')
  await page.getByTitle('发送').click()
  await expect(page.getByRole('main').getByText('生产完成，结果已返回对话。')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('navigation', { name: '资产视图' }).getByRole('button', { name: '成品库' }).click()
  await expect(page.locator('.fs-final-library')).toContainText(/\d+ 项/)
  await expect(page.locator('.fs-final-library img')).toBeVisible()
  await expect(page.getByRole('button', { name: /批量下载/ })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('image-edit-complete.png') })
})
