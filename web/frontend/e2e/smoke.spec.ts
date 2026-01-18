import { test, expect } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000'

test.describe('Smoke Tests', () => {
  test('homepage loads with vitals', async ({ page }) => {
    await page.goto(BASE_URL)
    
    // App bar should be visible
    await expect(page.getByRole('heading', { name: /straight outta colington/i })).toBeVisible()
    
    // Vitals grid should show temperature values
    await expect(page.getByText(/inside/i)).toBeVisible()
    await expect(page.getByText(/outside/i)).toBeVisible()
    await expect(page.getByText(/°F/)).toBeVisible()
  })

  test('narrative card displays content', async ({ page }) => {
    await page.goto(BASE_URL)
    
    // Captain's Log header should be visible
    await expect(page.getByText(/captain's log/i)).toBeVisible()
    
    // Wait for narrative to load (may take a moment)
    await expect(page.locator('article, [role="article"]').or(page.getByText(/updated at/i))).toBeVisible({ timeout: 10000 })
  })

  test('bottom sheet opens with charts', async ({ page }) => {
    await page.goto(BASE_URL)
    
    // Click FAB to open bottom sheet
    await page.getByRole('button', { name: /more options/i }).click()
    
    // Charts tab should be visible
    await expect(page.getByRole('tab', { name: /charts/i })).toBeVisible()
    
    // Toggle buttons for range should be present
    await expect(page.getByRole('button', { name: /24h/i })).toBeVisible()
  })

  test('bottom sheet has timelapse tab', async ({ page }) => {
    await page.goto(BASE_URL)
    
    // Open bottom sheet
    await page.getByRole('button', { name: /more options/i }).click()
    
    // Switch to timelapse tab
    await page.getByRole('tab', { name: /timelapse/i }).click()
    
    // Should show timelapse content or "unavailable" message
    await expect(
      page.getByText(/timelapse/i).or(page.getByText(/no timelapse/i))
    ).toBeVisible()
  })

  test('leaderboard tab shows content', async ({ page }) => {
    await page.goto(BASE_URL)
    
    // Open bottom sheet
    await page.getByRole('button', { name: /more options/i }).click()
    
    // Switch to leaderboard tab
    await page.getByRole('tab', { name: /leaderboard/i }).click()
    
    // Should show leaderboard or "no scores" message
    await expect(
      page.getByText(/no scores yet/i).or(page.getByRole('list'))
    ).toBeVisible()
  })

  test('API health check', async ({ request }) => {
    const response = await request.get(`${BASE_URL}/api/health`)
    expect(response.ok()).toBeTruthy()
    
    const body = await response.json()
    expect(body.status).toBe('healthy')
  })

  test('API status endpoint returns sensor data', async ({ request }) => {
    const response = await request.get(`${BASE_URL}/api/status`)
    expect(response.ok()).toBeTruthy()
    
    const body = await response.json()
    expect(body).toHaveProperty('sensors')
    expect(body).toHaveProperty('stale')
  })
})
