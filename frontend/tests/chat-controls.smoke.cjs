// Uses the synthetic report_ui_server, never live market/LLM providers.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')

async function main() {
  const output = path.resolve('../artifacts/chat-controls')
  await fs.mkdir(output, { recursive: true })
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    })
    let holdChat = false
    let heldRoute = null
    const chatRequests = []
    await context.route(
      /http:\/\/(localhost|127\.0\.0\.1):8000\//,
      async (route) => {
        const url = new URL(route.request().url())
        if (url.pathname === '/market/watch')
          return route.fulfill({
            status: 503,
            json: { detail: 'Synthetic offline market feed' },
          })
        if (holdChat && url.pathname === '/assistant/chat') {
          heldRoute = route
          return
        }
        if (url.pathname === '/assistant/chat') {
          chatRequests.push(route.request().postDataJSON())
          if (chatRequests.length === 1)
            return route.fulfill({
              status: 503,
              json: {
                detail:
                  'Gemini is temporarily unavailable. Your question is still here; try again shortly.',
              },
            })
        }
        const response = await route.fetch({
          url: `http://127.0.0.1:8011${url.pathname}${url.search}`,
        })
        await route.fulfill({ response })
      },
    )
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto('http://localhost:5173')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await page
      .getByRole('button', { name: 'Create an account', exact: true })
      .click()
    const username = `test_${Date.now()}`
    await page.getByLabel('Username', { exact: true }).fill(username)
    await page
      .getByLabel('Password', { exact: true })
      .fill('Synthetic test passphrase!')
    await page.screenshot({ path: path.join(output, 'desktop-signup.png') })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({ path: path.join(output, 'mobile-signup.png') })
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    )
    const registered = page.waitForResponse((response) =>
      response.url().endsWith('/auth/register'),
    )
    await page
      .getByRole('button', { name: 'Create account', exact: true })
      .click()
    assert.equal((await registered).status(), 201)
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    // The account form retains its last mode; switch back to sign-in.
    await page
      .getByRole('button', { name: 'Already have an account? Sign in' })
      .click()
    await page.getByLabel('Username', { exact: true }).fill(username)
    await page.getByLabel('Password', { exact: true }).fill('incorrect')
    await page
      .getByRole('button', { name: 'Sign in', exact: true })
      .last()
      .click()
    await page
      .getByRole('alert')
      .filter({ hasText: 'Incorrect username or password.' })
      .waitFor()
    await page
      .getByLabel('Password', { exact: true })
      .fill('Synthetic test passphrase!')
    await page
      .getByRole('button', { name: 'Sign in', exact: true })
      .last()
      .click()
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
    await page.setViewportSize({ width: 1440, height: 1000 })
    const message = page.getByRole('textbox', { name: 'Message', exact: true })
    await message.fill('Show me an NVDA price chart')
    const response = page.waitForResponse((response) =>
      response.url().endsWith('/assistant/chat'),
    )
    await page.getByRole('button', { name: 'Send research question' }).click()
    assert.equal((await response).status(), 503)
    await page.getByRole('button', { name: 'Retry question' }).waitFor()
    await page.screenshot({ path: path.join(output, 'desktop-retry.png') })
    const retried = page.waitForResponse((response) =>
      response.url().endsWith('/assistant/chat'),
    )
    await page.getByRole('button', { name: 'Retry question' }).click()
    assert.equal((await retried).status(), 200)
    assert.deepEqual(
      chatRequests[0],
      chatRequests[1],
      'Retry preserves the question, chat, request ID and report context',
    )
    await page
      .getByRole('tab', { name: 'NVDA market analysis', exact: true })
      .waitFor()
    await page.locator('.recharts-surface').first().waitFor()
    assert.equal(
      await page
        .getByText('This title must not be displayed in chat', { exact: true })
        .count(),
      0,
    )
    assert.equal(
      await page.getByText('Direct answer', { exact: true }).count(),
      0,
    )
    await page.screenshot({ path: path.join(output, 'desktop-chart-chat.png') })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.locator('[aria-label="Conversation"]').evaluate((element) => {
      element.scrollTop = 0
      element.dispatchEvent(new Event('scroll'))
    })
    await page.getByRole('button', { name: 'Jump to latest message' }).click()
    await page.waitForFunction(() => {
      const panel = document.querySelector('[aria-label="Conversation"]')
      return panel.scrollHeight - panel.scrollTop - panel.clientHeight < 100
    })
    await page.screenshot({ path: path.join(output, 'mobile-chart-chat.png') })
    assert(
      await page.evaluate(
        () => document.documentElement.scrollHeight <= innerHeight,
      ),
    )
    holdChat = true
    await message.fill('Should I chase the jump?')
    await page.getByRole('button', { name: 'Send research question' }).click()
    await page.getByRole('button', { name: 'Stop generating' }).waitFor()
    await page.getByText('Should I chase the jump?', { exact: true }).waitFor()
    while (!heldRoute) await new Promise((resolve) => setTimeout(resolve, 10))
    const stopped = page.waitForResponse((response) =>
      response.url().endsWith('/cancel'),
    )
    await page.getByRole('button', { name: 'Stop generating' }).click()
    assert.equal((await stopped).status(), 200)
    await page.getByText('Generation stopped.', { exact: true }).waitFor()
    assert.equal(await message.inputValue(), 'Should I chase the jump?')
    await heldRoute.abort().catch(() => {})
    assert.equal(
      await page
        .getByRole('region', { name: 'Conversation' })
        .getByText('Should I chase the jump?', { exact: true })
        .count(),
      0,
    )
    await page.screenshot({ path: path.join(output, 'mobile-stopped.png') })
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.reload()
    await page
      .getByRole('button', { name: 'Show me an NVDA price chart', exact: true })
      .first()
      .click()
    await page
      .getByRole('tab', { name: 'NVDA market analysis', exact: true })
      .waitFor()
    assert.equal(
      await page.getByText('Should I chase the jump?', { exact: true }).count(),
      0,
    )
    assert.deepEqual(errors, [])
    console.log(
      'PASS: password signup/login, inline chart, title removal, scroll arrow, stop and persistence, desktop/mobile',
    )
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
