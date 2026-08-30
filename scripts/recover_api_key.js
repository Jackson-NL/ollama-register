const fs = require('fs');
const path = require('path');
const { Camoufox } = require('camoufox');
const { extractOllamaApiKey, loadDotEnvFile } = require('./lib/auto_helpers');

const root = process.cwd();
loadDotEnvFile(path.resolve(root, '.env'));
const runId = process.env.OLLAMA_RUN_ID || 'recover-key-' + new Date().toISOString().replace(/[:.]/g, '-');
const outDir = path.resolve(root, 'output/playwright/recover-key', runId);
fs.mkdirSync(outDir, { recursive: true });
const email = process.env.OLLAMA_EMAIL;
const password = process.env.OLLAMA_PASSWORD;
if (!email || !password) throw new Error('OLLAMA_EMAIL/OLLAMA_PASSWORD required');
function log(...args){ const line='['+new Date().toISOString()+'] '+args.join(' '); console.log(line); fs.appendFileSync(path.join(outDir,'recover.log'), line+'\n'); }
function sleep(ms){ return new Promise(r=>setTimeout(r,ms)); }
async function clickByText(page, re){
  const locs=[page.getByRole('button',{name:re}).first(), page.locator('button[type="submit"]').first(), page.locator('input[type="submit"]').first()];
  for(const loc of locs){ try{ if(await loc.count()){ await loc.click({timeout:8000, force:true}); return true; }}catch{} }
  return false;
}
async function finishLogin(page){
  const start = Date.now();
  let emailDone = false;
  while(Date.now() - start < 180000){
    const url = page.url();
    if(/^https:\/\/ollama\.com/.test(url)) return true;
    const emailInput = page.locator('input[name="email"], input[type="email"]').first();
    if(!emailDone && await emailInput.count().catch(()=>0)){
      await emailInput.fill(email).catch(()=>{});
      await clickByText(page,/continue|sign in|next/i);
      emailDone = true;
      await sleep(2500);
      continue;
    }
    const pwInput = page.locator('input[type="password"], input[name*="password" i]').first();
    if(await pwInput.count().catch(()=>0)){
      await pwInput.fill(password).catch(()=>{});
      await clickByText(page,/continue|sign in|log in/i);
      await sleep(5000);
      continue;
    }
    await sleep(1500);
  }
  return /^https:\/\/ollama\.com/.test(page.url());
}
async function createApiKeyInPage(page, name){
  await page.goto('https://ollama.com/settings/keys', {waitUntil:'domcontentloaded', timeout:60000});
  await sleep(1000);
  const out = await page.evaluate(async (keyName) => {
    const res = await fetch('/settings/keys/generate', {
      method:'POST', credentials:'include',
      headers:{'content-type':'application/x-www-form-urlencoded','hx-trigger':'api-key-add-form','hx-target':'add-api-key','hx-current-url':'https://ollama.com/settings/keys','hx-request':'true'},
      body:new URLSearchParams({'api-key-name':keyName}).toString(),
    });
    return {status:res.status, text:await res.text()};
  }, name);
  fs.writeFileSync(path.join(outDir,'api_response.html'), out.text);
  const key = extractOllamaApiKey(out.text);
  fs.writeFileSync(path.join(outDir,'api_key_result.json'), JSON.stringify({status:out.status, got:!!key, keyName:name, key:key||null}, null, 2));
  return key;
}
(async()=>{
  let browser;
  try{
    browser = await Camoufox({headless: process.env.CAMOUFOX_HEADLESS === '1', os:'windows', locale:['en-US'], defaultViewport:null});
    const ctx = await browser.newContext({viewport:null});
    const page = await ctx.newPage();
    await page.setViewportSize({width:1365,height:900}).catch(()=>{});
    await page.goto('https://ollama.com/signin', {waitUntil:'domcontentloaded', timeout:60000});
    await sleep(1500);
    log('URL', page.url());
    await finishLogin(page);
    log('AFTER_LOGIN_URL', page.url());
    if(!/^https:\/\/ollama\.com/.test(page.url())){
      await page.screenshot({path:path.join(outDir,'login_not_done.png'), fullPage:false}).catch(()=>{});
      throw new Error('login did not reach ollama.com: '+page.url());
    }
    const name=process.env.OLLAMA_KEY_NAME || ('auto' + Date.now().toString(36)).slice(0, 20);
    const key = await createApiKeyInPage(page, name);
    log('KEY', key ? key.slice(0,12)+'...' : '(none)');
    if(key){
      fs.appendFileSync(path.join(root,'accounts_auto.jsonl'), JSON.stringify({ts:new Date().toISOString(), provider:'ollama', status:'api_key_recovered', email, api_key:key, api_key_sha256:require('crypto').createHash('sha256').update(key).digest('hex'), keyName:name})+'\n');
    }
  } finally { if(browser) await browser.close().catch(()=>{}); }
})().catch(e=>{ fs.writeFileSync(path.join(outDir,'error.txt'), String(e.stack||e)); console.error(e); process.exit(1); });
