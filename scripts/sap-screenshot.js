const { chromium } = require('playwright');

const SAP_URL = 'http://hnclvscs.chng.com.cn/irj/portal?sap-language=ZH';
const SAP_USER = '82031001';
const SAP_PASS = 'Ycjf1234';
const OUTPUT = '/tmp/sap-todo.png';

(async () => {
  const browser = await chromium.launch({
    headed: true,
    args: [
      '--disable-web-security',
      '--disable-features=IsolateOrigins,site-per-process',
    ],
  });
  const context = await browser.newContext({
    locale: 'zh-CN',
    ignoreHTTPSErrors: true,
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    extraHTTPHeaders: { 'Accept-Language': 'zh-CN,zh;q=0.9' },
  });
  const page = await context.newPage();

  // Block RTMF and other non-essential resources that cause 503 / slow loading
  await context.route('**/rtmfCommunicator/**', (route) => route.abort());
  await context.route('**/*RTMF*', (route) => route.abort());

  try {
    console.log('[1/5] Opening SAP Portal...');
    await page.goto(SAP_URL, { waitUntil: 'networkidle', timeout: 30000 });

    console.log('[2/5] Logging in...');
    await page.getByRole('textbox', { name: '用户 *' }).fill(SAP_USER);
    await page.getByRole('textbox', { name: '密码 *' }).fill(SAP_PASS);
    await page.getByRole('button', { name: '登录' }).click();
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});

    console.log('[3/5] Navigating to 个人工作...');
    await page.getByRole('link', { name: '个人工作' }).click({ timeout: 10000 });
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});

    console.log('[4/5] Navigating to 新待办工作...');
    await page.waitForSelector('iframe[name~="桌面内部页"]', { state: 'attached', timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.locator('iframe[name~="桌面内部页"]').contentFrame().getByRole('link', { name: '新待办工作' }).click({ timeout: 15000 });

    // Wait for inner content iframe to appear — indicates content finished loading
    const frame1 = page.locator('iframe[name~="桌面内部页"]').contentFrame();
    await frame1.locator('iframe[name="isolatedWorkArea"]').waitFor({ state: 'attached', timeout: 30000 });
    await page.waitForTimeout(2000);

    console.log('[5/5] Waiting for content and taking screenshot...');
    await page.waitForTimeout(3000);

    await page.screenshot({ path: OUTPUT, fullPage: true });
    console.log(`Screenshot saved to ${OUTPUT}`);

  } catch (err) {
    console.error(`Error: ${err.message}`);
    await page.screenshot({ path: '/tmp/sap-error.png' }).catch(() => {});
    console.log('Error screenshot saved to /tmp/sap-error.png');
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
