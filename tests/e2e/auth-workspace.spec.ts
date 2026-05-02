import { expect, test } from '@playwright/test'

test('注册后进入中文工作台并显示团队空间和运行队列入口', async ({ page }) => {
  const username = `e2e-${Date.now()}`

  await page.goto('/')
  await page.getByRole('button', { name: '注册' }).click()
  await page.getByLabel('账号').fill(username)
  await page.getByLabel('密码').fill('password123')
  await page.getByRole('button', { name: '注册并登录' }).click()

  await expect(page.getByText('流程工坊').first()).toBeVisible()
  await expect(page.getByText('团队空间', { exact: true })).toBeVisible()
  await expect(page.getByLabel('当前团队空间')).toBeVisible()
  await expect(page.getByRole('button', { name: '异步入队' })).toBeVisible()
  await expect(page.getByText('异步队列空闲')).toBeVisible()
  await expect(page.getByText('版本与审计')).toBeVisible()
})
