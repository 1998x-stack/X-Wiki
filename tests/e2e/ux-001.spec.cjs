const { test, expect } = require('@playwright/test');

async function moveToEvidence(page) {
  await page.goto('/demo/');
  for (let step = 0; step < 4; step += 1) {
    await page.getByRole('button', { name: /Continue/ }).click();
  }
  await expect(page.locator('#demo-app')).toHaveAttribute('data-step', '4');
}

async function moveToDecision(page) {
  await moveToEvidence(page);
  await page.getByRole('button', { name: /Inspect both sources/ }).click();
  await page.getByRole('button', { name: /Continue/ }).click();
  await expect(page.locator('#demo-app')).toHaveAttribute('data-step', '5');
}

test('discovery from the Wiki homepage leads into a working static demo', async ({ page }) => {
  await page.goto('/');
  const entry = page.getByRole('link', { name: /体验 X-Wiki 的 90 秒交互演示/ });
  await expect(entry).toHaveAttribute('href', 'demo/');
  await entry.click();
  await expect(page).toHaveURL(/\/demo\/$/);
  await expect(page.getByRole('heading', { name: /Your ideas deserve/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Every idea starts somewhere/ })).toBeVisible();
  await expect(page.getByText(/No signup\. No uploads/)).toBeVisible();
});

test('source review is mandatory before final approval and changes knowledge', async ({ page }) => {
  await moveToEvidence(page);
  const next = page.getByRole('button', { name: /Continue/ });
  await expect(next).toBeDisabled();
  await expect(page.locator('#demo-app')).toHaveAttribute('data-reviewed', 'false');

  await page.getByRole('button', { name: /Inspect both sources/ }).click();
  await expect(page.locator('#evidence-panel')).toBeVisible();
  await expect(page.getByText('SOURCE 01 / AUG 12, 2026')).toBeVisible();
  await expect(page.getByText('SOURCE 02 / OCT 28, 2026')).toBeVisible();
  await expect(page.locator('#demo-app')).toHaveAttribute('data-reviewed', 'true');
  await expect(next).toBeEnabled();
  await next.click();

  const node = page.locator('#knowledge-text');
  await expect(node).toContainText('A fixed schedule');
  await page.getByRole('button', { name: /Approve revision/ }).click();
  await expect(page.locator('#demo-app')).toHaveAttribute('data-decision', 'approved');
  await expect(node).toContainText('leaving flexible time');
  await expect(page.locator('#knowledge-version')).toContainText('REVISION 02');
  await expect(page.getByText('Your knowledge has evolved.')).toBeVisible();

  await page.getByRole('button', { name: /Undo this decision/ }).click();
  await expect(page.locator('#demo-app')).toHaveAttribute('data-decision', 'pending');
  await expect(node).toContainText('A fixed schedule');
  await expect(page.locator('#knowledge-version')).toContainText('REVISION 01');
});

test('reject keeps the original knowledge and reset clears all progress', async ({ page }) => {
  await moveToDecision(page);
  await page.getByRole('button', { name: /Keep the old idea/ }).click();
  await expect(page.locator('#demo-app')).toHaveAttribute('data-decision', 'rejected');
  await expect(page.locator('#knowledge-text')).toContainText('A fixed schedule');
  await expect(page.getByText('You kept your original idea.')).toBeVisible();
  await page.getByRole('button', { name: /Start over/ }).click();
  await expect(page.locator('#demo-app')).toHaveAttribute('data-step', '0');
  await expect(page.locator('#demo-app')).toHaveAttribute('data-reviewed', 'false');
  await expect(page.locator('#demo-app')).toHaveAttribute('data-decision', 'pending');
  await expect(page.locator('#evidence-panel')).toBeHidden();
  await expect(page.getByRole('heading', { name: /Every idea starts somewhere/ })).toBeFocused();
});

test('back and keyboard navigation work without bypassing the review gate', async ({ page }) => {
  await page.goto('/demo/');
  const next = page.getByRole('button', { name: /Continue/ });
  await next.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#demo-app')).toHaveAttribute('data-step', '1');
  await expect(page.getByRole('heading', { name: /But then you think differently/ })).toBeFocused();
  await page.getByRole('button', { name: /Back/ }).click();
  await expect(page.locator('#demo-app')).toHaveAttribute('data-step', '0');
  await moveToEvidence(page);
  await expect(next).toBeDisabled();
  await next.press('Enter', { noWaitAfter: true }).catch(() => {});
  await expect(page.locator('#demo-app')).toHaveAttribute('data-step', '4');
});

test('demo never calls third-party services or persists personal data', async ({ page, context }) => {
  const thirdParty = [];
  page.on('request', (request) => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith('http://127.0.0.1:8765/')) {
      thirdParty.push(request.url());
    }
  });
  await moveToDecision(page);
  await page.getByRole('button', { name: /Approve revision/ }).click();
  const storage = await page.evaluate(() => ({
    local: localStorage.length,
    session: sessionStorage.length,
    inputs: document.querySelectorAll('input[type=file],input[type=email],input[type=password]').length
  }));
  expect(storage).toEqual({ local: 0, session: 0, inputs: 0 });
  expect(await context.cookies()).toEqual([]);
  expect(thirdParty).toEqual([]);
});

test('demo is usable on narrow screens without horizontal document overflow', async ({ page }) => {
  await page.goto('/demo/');
  await page.getByRole('link', { name: /Explore the 90-second demo/ }).click();
  await expect(page.getByRole('heading', { name: /Every idea starts somewhere/ })).toBeVisible();
  const widths = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport + 2);
});
