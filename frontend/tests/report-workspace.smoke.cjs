// Run against the local report_ui_server.py fixture; never calls paid providers.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')

async function main() {
  const output = path.resolve('../artifacts/report-workspace')
  await fs.mkdir(output, { recursive: true })
  const browser = await chromium.launch({
    headless: true,
    channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome',
  })
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    })
    let patternCalls = 0
    let patternMode = 'normal'
    await context.route(
      /http:\/\/(localhost|127\.0\.0\.1):8000\//,
      async (route) => {
        const url = new URL(route.request().url())
        if (url.pathname.endsWith('/patterns/backtest')) {
          patternCalls += 1
          await new Promise((resolve) => setTimeout(resolve, 200))
          if (patternMode === 'error')
            return route.fulfill({
              status: 429,
              json: { detail: 'Synthetic provider rate limit' },
            })
          const response = await route.fetch({
            url: `http://127.0.0.1:8011${url.pathname}${url.search}`,
          })
          const data = await response.json()
          if (patternMode === 'stale') {
            data.latest_patterns.status = 'stale'
            data.latest_patterns.checks.forEach((check) => {
              check.detected = null
            })
          }
          if (patternMode === 'empty') data.completed_bar_count = 0
          return route.fulfill({ json: data })
        }
        if (url.pathname === '/market/watch')
          return route.fulfill({
            json: {
              generated_at: '2026-09-25T12:00:00Z',
              provider: 'synthetic',
              period_start: '2026-09-24T00:00:00Z',
              period_end: '2026-09-25T12:00:00Z',
              market_snapshot_at: '2026-09-25T12:00:00Z',
              market_data_freshness: 'provider_snapshot',
              market_session: 'premarket',
              snapshot_feed: 'iex',
              candidates: [],
              movers: [],
              news_catalysts: [],
              warnings: [],
            },
          })
        if (url.pathname === '/auth/config')
          return route.fulfill({
            json: { google_enabled: false, google_client_id: null },
          })
        if (url.pathname === '/auth/me')
          return route.fulfill({ status: 401, json: { detail: 'Test guest' } })
        const response = await route.fetch({
          url: `http://127.0.0.1:8011${url.pathname}${url.search}`,
        })
        await route.fulfill({ response })
      },
    )
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(process.env.APP_URL || 'http://localhost:5173')
    await page
      .getByRole('heading', { name: 'What are you researching?' })
      .waitFor()
    async function send(question) {
      await page
        .getByRole('textbox', { name: 'Message', exact: true })
        .fill(question)
      const response = page.waitForResponse((response) =>
        response.url().endsWith('/assistant/chat'),
      )
      await page.getByRole('button', { name: 'Send research question' }).click()
      await page.getByText(question, { exact: true }).last().waitFor()
      assert.equal(
        await page
          .getByRole('textbox', { name: 'Message', exact: true })
          .inputValue(),
        '',
      )
      assert.equal((await response).status(), 200)
      await page
        .getByRole('button', { name: 'Send research question' })
        .waitFor({ state: 'visible' })
      await page.waitForFunction(() => {
        const button = document.querySelector(
          '[aria-label="Send research question"]',
        )
        return button !== null && !button.disabled
      })
    }
    await send('Analyse NVDA for me')
    await page
      .getByRole('tab', { name: 'NVDA market analysis', exact: true })
      .click()
    await page
      .getByRole('heading', { name: 'NVIDIA Corporation', exact: true })
      .waitFor()
    assert.equal(patternCalls, 0, 'No pattern requests until its tab opens')
    await page.getByRole('tab', { name: 'Daily patterns', exact: true }).click()
    await page
      .getByText('Loading pattern history...', { exact: true })
      .waitFor()
    const patterns = page.getByRole('region', {
      name: 'NVDA daily patterns',
      exact: true,
    })
    await patterns.getByRole('table').first().waitFor()
    assert.equal(patternCalls, 1)
    await patterns.getByText('Detected', { exact: true }).first().waitFor()
    await patterns.getByRole('radio', { name: '5 bars', exact: true }).check()
    await patterns.getByText('Small sample', { exact: true }).first().waitFor()
    await page.screenshot({ path: path.join(output, 'desktop-patterns.png') })
    await page.getByRole('tab', { name: 'Overview', exact: true }).click()
    await page.getByRole('tab', { name: 'Daily patterns', exact: true }).click()
    assert.equal(patternCalls, 1, 'Section switches reuse loaded study')
    await patterns
      .getByRole('combobox', { name: 'Evidence and uncertainty', exact: true })
      .selectOption('falling_streak_low_rsi')
    await patterns.getByText('Dated outcomes (0)', { exact: true }).click()
    await patterns
      .getByText('No completed, non-overlapping events for this horizon.', {
        exact: true,
      })
      .waitFor()
    patternMode = 'error'
    await patterns
      .getByRole('button', { name: 'Refresh NVDA patterns', exact: true })
      .click()
    await patterns
      .getByRole('alert')
      .filter({ hasText: 'Synthetic provider rate limit' })
      .waitFor()
    patternMode = 'normal'
    await patterns
      .getByRole('button', { name: 'Retry pattern study', exact: true })
      .click()
    await patterns.getByRole('table').first().waitFor()
    patternMode = 'stale'
    await patterns
      .getByRole('button', { name: 'Refresh NVDA patterns', exact: true })
      .click()
    await patterns.getByText('Stale history:', { exact: false }).waitFor()
    patternMode = 'empty'
    await patterns
      .getByRole('button', { name: 'Refresh NVDA patterns', exact: true })
      .click()
    await patterns
      .getByText('No completed daily bars are available.', { exact: true })
      .waitFor()
    patternMode = 'normal'
    await patterns
      .getByRole('button', { name: 'Refresh NVDA patterns', exact: true })
      .click()
    await patterns.getByRole('table').first().waitFor()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({ path: path.join(output, 'mobile-patterns.png') })
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      'Pattern table must not overflow the page',
    )
    const tableRegion = patterns.getByRole('region', {
      name: 'Pattern history table',
      exact: true,
    })
    assert(
      await tableRegion.evaluate((node) => node.scrollWidth > node.clientWidth),
      'Wide pattern table scrolls independently',
    )
    await patterns
      .getByRole('combobox', { name: 'Evidence and uncertainty', exact: true })
      .selectOption('rising_streak_high_rsi')
    await patterns
      .getByRole('region', { name: 'Pattern evidence', exact: true })
      .scrollIntoViewIfNeeded()
    await page.screenshot({
      path: path.join(output, 'mobile-pattern-evidence.png'),
    })
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page
      .getByRole('tab', { name: 'Financial scores', exact: true })
      .click()
    await page
      .getByText('Unvalidated heuristic', { exact: false })
      .first()
      .waitFor()
    await page.screenshot({ path: path.join(output, 'desktop-financials.png') })
    await page.getByRole('tab', { name: 'Overview', exact: true }).click()
    await page.locator('.recharts-surface').first().waitFor()
    await page.screenshot({ path: path.join(output, 'desktop-report.png') })
    await page.getByText('Daily snapshot', { exact: false }).waitFor()
    assert.match(
      await page.getByText('Daily snapshot', { exact: false }).innerText(),
      /(?:12:00:00 am|00:00:00)/i,
      'Expiry is local midnight',
    )
    for (const label of [
      'Market report',
      'Market outlook',
      'Fundamentals',
      'Sentiment report',
      'News report',
      'Bull and bear case',
      'Investment plan',
      'Risk management',
    ]) {
      const tab = page
        .getByRole('tablist', { name: 'Report sections', exact: true })
        .getByRole('tab', { name: label, exact: true })
      await tab.click()
      assert.equal(await tab.getAttribute('aria-selected'), 'true')
      await page
        .getByRole('tabpanel')
        .getByText('This is deterministic test content.', { exact: false })
        .first()
        .waitFor()
      if (label === 'Market report')
        await page.locator('.recharts-surface').first().waitFor()
      if (label === 'Sentiment report') {
        await page
          .getByLabel('News sentiment chart')
          .getByRole('application')
          .waitFor()
        await page.screenshot({
          path: path.join(output, 'desktop-sentiment.png'),
        })
      }
      if (label === 'Market outlook') {
        await page
          .getByLabel('Direction probability chart')
          .getByRole('application')
          .waitFor()
        await page.screenshot({
          path: path.join(output, 'desktop-outlook.png'),
        })
      }
    }
    await page.getByRole('tab', { name: 'Market report', exact: true }).focus()
    await page.keyboard.press('ArrowRight')
    assert.equal(
      await page
        .getByRole('tab', { name: 'Market outlook', exact: true })
        .getAttribute('aria-selected'),
      'true',
    )
    await page.getByRole('tab', { name: 'Chat', exact: true }).click()
    await send('What is a good buy-in price?')
    assert.equal(
      await page
        .getByRole('tab', { name: 'NVDA market analysis', exact: true })
        .count(),
      1,
    )
    await send('Compare NVDA and AMD')
    assert.equal(
      await page
        .getByRole('tab', { name: 'AMD market analysis', exact: true })
        .count(),
      0,
    )
    await page.getByText('Peer comparison · quality', { exact: true }).waitFor()
    await send('Analyse AMD for me')
    assert.equal(
      await page
        .getByRole('tab', { name: 'AMD market analysis', exact: true })
        .count(),
      1,
    )
    await page.screenshot({ path: path.join(output, 'desktop-chat.png') })
    await page.reload()
    await page
      .getByRole('button', { name: 'Analyse NVDA for me', exact: true })
      .first()
      .click()
    await page
      .getByRole('tab', { name: 'AMD market analysis', exact: true })
      .waitFor()
    assert.equal(
      await page
        .getByRole('tab', { name: 'NVDA market analysis', exact: true })
        .count(),
      1,
    )
    await page
      .getByRole('tab', { name: 'AMD market analysis', exact: true })
      .click()
    const refreshed = page.waitForResponse((response) =>
      response.url().endsWith('/assistant/chat'),
    )
    await page
      .getByRole('button', { name: 'Refresh AMD report', exact: true })
      .click()
    assert.equal((await refreshed).status(), 200)
    await page.waitForFunction(() => {
      const button = document.querySelector(
        '[aria-label="Send research question"]',
      )
      return button !== null && !button.disabled
    })
    assert.equal(
      await page
        .getByRole('tab', { name: 'AMD market analysis', exact: true })
        .count(),
      1,
    )
    await page
      .getByRole('button', { name: 'New research', exact: true })
      .click()
    await send('Compare NVDA, AMD and INTC for growth')
    await page.getByText('Peer comparison · growth', { exact: true }).waitFor()
    assert.equal(
      await page.getByRole('tab', { name: /market analysis$/ }).count(),
      0,
      'Three-stock comparisons do not create individual reports',
    )
    await page.screenshot({ path: path.join(output, 'desktop-comparison.png') })
    await send('Compare NVDA, AMD and INTC and create separate reports')
    for (const symbol of ['NVDA', 'AMD', 'INTC']) {
      await page
        .getByRole('tab', { name: `${symbol} market analysis`, exact: true })
        .waitFor()
    }
    assert.equal(
      await page.getByRole('tab', { name: /market analysis$/ }).count(),
      3,
      'Explicit requests create the three selected report tabs',
    )
    await page.setViewportSize({ width: 390, height: 844 })
    await page
      .getByRole('tab', { name: 'NVDA market analysis', exact: true })
      .click()
    await page
      .getByRole('tab', { name: 'Financial scores', exact: true })
      .click()
    await page.screenshot({ path: path.join(output, 'mobile-report.png') })
    await page
      .getByRole('tab', { name: 'Sentiment report', exact: true })
      .click()
    await page
      .getByLabel('News sentiment chart')
      .getByRole('application')
      .waitFor()
    await page.getByLabel('News sentiment chart').scrollIntoViewIfNeeded()
    await page.mouse.move(0, 0)
    assert(
      (await page
        .getByLabel('News sentiment chart')
        .locator('.recharts-bar-rectangle path')
        .count()) > 0,
      'Sentiment bars are rendered',
    )
    await page.screenshot({ path: path.join(output, 'mobile-sentiment.png') })
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      'No horizontal page overflow',
    )
    assert(
      await page.evaluate(
        () => document.documentElement.scrollHeight <= window.innerHeight,
      ),
      'Only panel scrolls',
    )
    await page.getByRole('tab', { name: 'Chat', exact: true }).click()
    await page.screenshot({ path: path.join(output, 'mobile-chat.png') })
    await page
      .getByRole('button', { name: 'Open market watch', exact: true })
      .click()
    await page
      .getByRole('heading', { name: 'Movers and news catalysts', exact: true })
      .waitFor()
    await page
      .getByRole('tab', { name: 'Biggest movers', exact: true })
      .waitFor()
    const newsTab = page.getByRole('tab', {
      name: 'News catalysts',
      exact: true,
    })
    await newsTab.click()
    assert.equal(await newsTab.getAttribute('aria-selected'), 'true')
    assert.equal(
      await page
        .getByRole('button', { name: 'Rank watchlist', exact: true })
        .count(),
      0,
      'Watchlist ranking is not in Market Watch',
    )
    await page.screenshot({
      path: path.join(output, 'mobile-market-watch.png'),
    })
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      'No horizontal page overflow on Market Watch',
    )
    assert.deepEqual(errors, [])
    console.log(
      'PASS: saved reports, follow-up, comparison, second stock, reload, refresh, desktop/mobile, no browser errors',
    )
  } catch (error) {
    const failedPage = browser.contexts()[0]?.pages()[0]
    if (failedPage) {
      await failedPage.screenshot({ path: path.join(output, 'failure.png') })
      console.error(await failedPage.locator('body').innerText())
    }
    throw error
  } finally {
    await browser.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
