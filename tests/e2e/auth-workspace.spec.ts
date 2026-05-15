import { expect, test } from '@playwright/test'

test('注册后进入中文工作台并显示团队空间和运行队列入口', async ({ page }) => {
  const username = `e2e-${Date.now()}`

  await page.goto('/')
  await page.getByRole('button', { name: '注册' }).click()
  await page.getByLabel('账号').fill(username)
  await page.getByLabel('密码').fill('password123')
  await page.getByRole('button', { name: '注册并登录' }).click()

  await expect(page.getByText('织流 AI').first()).toBeVisible()
  await expect(page.getByText('团队空间', { exact: true })).toBeVisible()
  await expect(page.getByLabel('当前团队空间')).toBeVisible()
  await expect(page.getByText('管理中心')).toBeVisible()
  await expect(page.getByRole('button', { name: '系统', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '团队', exact: true })).toBeVisible()
  await expect(page.getByText('节点配置')).toBeVisible()

  await page.getByRole('button', { name: '系统', exact: true }).click()
  await expect(page.getByText('系统概览', { exact: true })).toBeVisible()
  await expect(page.getByText('数据库')).toBeVisible()
  await expect(page.getByText('安全配置')).toBeVisible()

  await page.getByRole('button', { name: '运维', exact: true }).click()
  await expect(page.getByRole('button', { name: '异步入队' })).toBeVisible()
  await expect(page.getByText('异步队列空闲')).toBeVisible()
  await expect(page.getByText('版本与审计')).toBeVisible()

  await page.getByRole('button', { name: '模型', exact: true }).click()
  await expect(page.getByRole('button', { name: '文字转语音' })).toBeVisible()
  await expect(page.getByRole('button', { name: '图片生成' })).toBeVisible()
  await expect(page.getByText('阿里云百炼', { exact: true })).toBeVisible()
  await expect(page.getByText('默认 TTS 模型')).toBeVisible()
})
