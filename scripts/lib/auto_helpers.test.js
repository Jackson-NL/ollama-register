const test = require('node:test');
const assert = require('node:assert/strict');

const {
  summarizeCfChallengeBody,
  chooseStableWidgetTarget,
  redactAutomationConfig,
} = require('./auto_helpers');

test('summarizeCfChallengeBody detects token-like fields without exposing secret values', () => {
  const body = JSON.stringify({
    status: 'pass',
    token: '0.' + 'A'.repeat(80),
    cf_clearance: 'secret-cookie-value',
    nested: { bot_detection_token: 'bdt_' + 'b'.repeat(40) },
  });

  const summary = summarizeCfChallengeBody(body, 'application/json');

  assert.equal(summary.looksLikeJson, true);
  assert.equal(summary.hasPassSignal, true);
  assert.equal(summary.hasFailSignal, false);
  assert.equal(summary.tokenLikeCount, 3);
  assert.deepEqual(summary.tokenFieldNames.sort(), ['bot_detection_token', 'cf_clearance', 'token']);
  assert.match(summary.sha256, /^[a-f0-9]{64}$/);
  assert.equal(JSON.stringify(summary).includes('secret-cookie-value'), false);
  assert.equal(JSON.stringify(summary).includes('bdt_'), false);
});

test('chooseStableWidgetTarget ignores jumping rects and returns checkbox point after stable centered samples', () => {
  const samples = [
    { rect: { x: 533, y: 475, w: 300, h: 72 }, ox: 10, oy: 80 },
    { rect: { x: 48, y: 114, w: 300, h: 72 }, ox: 10, oy: 80 },
    { rect: { x: 534, y: 476, w: 300, h: 72 }, ox: 10, oy: 80 },
    { rect: { x: 535, y: 475, w: 300, h: 72 }, ox: 10, oy: 80 },
  ];

  const target = chooseStableWidgetTarget(samples, { minCenteredX: 300, tolerancePx: 3, checkboxOffsetX: 45 });

  assert.equal(target.stable, true);
  assert.deepEqual(target.viewport, { x: 580, y: 511 });
  assert.deepEqual(target.screen, { x: 590, y: 591 });
});

test('redactAutomationConfig removes API keys and preserves non-secret run settings', () => {
  const config = {
    runId: 'fa-test',
    smsbowerApiKey: 'K2secret',
    SMSBOWER_API_KEY: 'env-secret',
    CAMOUFOX_PROXY: 'http://127.0.0.1:7890',
    maxTotalMs: 120000,
  };

  assert.deepEqual(redactAutomationConfig(config), {
    runId: 'fa-test',
    smsbowerApiKey: '[redacted]',
    SMSBOWER_API_KEY: '[redacted]',
    CAMOUFOX_PROXY: 'http://127.0.0.1:7890',
    maxTotalMs: 120000,
  });
});

const { shouldSubmitPasswordDuringChallenge } = require('./auto_helpers');

test('shouldSubmitPasswordDuringChallenge submits after prefill when widget is invisible instead of waiting forever', () => {
  const decision = shouldSubmitPasswordDuringChallenge({
    hasPasswordInput: true,
    passwordFilled: true,
    challengeVisible: false,
    tokenLen: 0,
    challengeElapsedSec: 9,
    submitAttempts: 0,
  });

  assert.deepEqual(decision, { submit: true, reason: 'password_challenge_invisible_widget_retry' });
});

test('shouldSubmitPasswordDuringChallenge backs off repeated password challenge submissions', () => {
  assert.equal(shouldSubmitPasswordDuringChallenge({
    hasPasswordInput: true,
    passwordFilled: true,
    challengeVisible: false,
    tokenLen: 0,
    challengeElapsedSec: 20,
    submitAttempts: 1,
  }).submit, false);

  assert.equal(shouldSubmitPasswordDuringChallenge({
    hasPasswordInput: true,
    passwordFilled: true,
    challengeVisible: false,
    tokenLen: 0,
    challengeElapsedSec: 35,
    submitAttempts: 1,
  }).submit, true);
});

test('shouldSubmitPasswordDuringChallenge submits immediately when token appears', () => {
  const decision = shouldSubmitPasswordDuringChallenge({
    hasPasswordInput: true,
    passwordFilled: true,
    challengeVisible: true,
    tokenLen: 123,
    challengeElapsedSec: 2,
    submitAttempts: 0,
  });

  assert.deepEqual(decision, { submit: true, reason: 'password_challenge_token_ready' });
});

test('shouldSubmitPasswordDuringChallenge treats non-centered password widget as non-interactive', () => {
  const decision = shouldSubmitPasswordDuringChallenge({
    hasPasswordInput: true,
    passwordFilled: true,
    challengeVisible: true,
    challengeCentered: false,
    tokenLen: 0,
    challengeElapsedSec: 45,
    submitAttempts: 0,
  });

  assert.deepEqual(decision, { submit: true, reason: 'password_challenge_noninteractive_widget_retry' });
});

const { parseDotEnvText } = require('./auto_helpers');

test('parseDotEnvText parses quoted values and ignores comments without exposing dotenv dependency', () => {
  const parsed = parseDotEnvText(`
# comment
SMSBOWER_API_KEY="abc=123"
SMSBOWER_COUNTRY=33
EMPTY=
BAD LINE
`);

  assert.deepEqual(parsed, {
    SMSBOWER_API_KEY: 'abc=123',
    SMSBOWER_COUNTRY: '33',
    EMPTY: '',
  });
});

const { buildPhoneFieldValues } = require('./auto_helpers');

test('buildPhoneFieldValues splits Colombia full number into country and local fields', () => {
  assert.deepEqual(buildPhoneFieldValues('573159872610', '+57'), {
    countryCode: '+57',
    countryDigits: '57',
    localNumber: '3159872610',
    full: '+573159872610',
    fullDigits: '573159872610',
  });
});

const { isPhoneRejectedText, isPhoneHardBlockedText, isPhoneSmsCodePromptText, isPhoneSmsChallengeText } = require('./auto_helpers');

test('phone text classifier does not treat send button label as sms sent', () => {
  const text = 'Verify your phone number\nPhone number\nSend verification code\nYou must have a valid mobile phone number to sign up.';
  assert.equal(isPhoneSmsCodePromptText(text), false);
  assert.equal(isPhoneRejectedText(text), false);
});

test('phone text classifier detects rejection and sms code prompts', () => {
  assert.equal(isPhoneRejectedText('Too many challenges sent for this phone number, please contact your admin.'), true);
  assert.equal(isPhoneHardBlockedText('Too many challenges sent for this phone number, please contact your admin.'), true);
  assert.equal(isPhoneHardBlockedText('phone number is invalid'), false);
  assert.equal(isPhoneSmsCodePromptText('Enter the verification code sent to your phone'), true);
});

test('phone sms challenge is separated from email verification code page', () => {
  assert.equal(isPhoneSmsChallengeText('Check your messages\nEnter the code sent to +573181837780'), true);
  assert.equal(isPhoneSmsChallengeText('Verify your email\nEnter the code sent to user@example.com'), false);
  assert.equal(isPhoneSmsChallengeText('', 'https://signin.ollama.com/radar-challenge/verify?x=1'), true);
});

test('shouldSubmitPasswordDuringChallenge retries filled password even when widget remains centered', () => {
  const decision = shouldSubmitPasswordDuringChallenge({
    hasPasswordInput: true,
    passwordFilled: true,
    challengeVisible: true,
    challengeCentered: true,
    tokenLen: 0,
    challengeElapsedSec: 35,
    submitAttempts: 1,
  });

  assert.deepEqual(decision, { submit: true, reason: 'password_challenge_backoff_retry' });
});

const { extractOllamaApiKey } = require('./auto_helpers');

test('extractOllamaApiKey finds generated key in HTML', () => {
  const html = '<div><code>0123456789abcdef0123456789abcdef.Abcdefghijklmnopqrstuvwxyz_123</code></div>';
  assert.equal(extractOllamaApiKey(html), '0123456789abcdef0123456789abcdef.Abcdefghijklmnopqrstuvwxyz_123');
});

const { isPriceOverLimit } = require('./auto_helpers');

test('isPriceOverLimit treats the SMS rental cap as an exclusive upper bound', () => {
  assert.equal(isPriceOverLimit('0.021', '0.02'), true);
  assert.equal(isPriceOverLimit('0.020', '0.02'), false);
  assert.equal(isPriceOverLimit('not-a-price', '0.02'), false);
});

test('email challenge unresolved signup form should keep waiting instead of treating unknown as passed', () => {
  const { shouldKeepWaitingForEmailChallenge } = require('./auto_helpers');
  const decision = shouldKeepWaitingForEmailChallenge({
    stateName: 'unknown',
    url: 'https://signin.ollama.com/sign-up?client_id=x',
    hasEmailInput: true,
    hasPasswordInput: false,
    tokenLen: 0,
    text: 'Sign up\nEmail\nContinue\nOR\nContinue with Google\nContinue with GitHub',
  });

  assert.deepEqual(decision, { keepWaiting: true, reason: 'email_signup_form_without_progress' });
});

test('Cloudflare click plan defaults to Playwright click before OS fallback', () => {
  const { shouldUsePlaywrightCfMouse } = require('./auto_helpers');

  assert.equal(shouldUsePlaywrightCfMouse(undefined), true);
  assert.equal(shouldUsePlaywrightCfMouse(''), true);
  assert.equal(shouldUsePlaywrightCfMouse('1'), true);
  assert.equal(shouldUsePlaywrightCfMouse('0'), false);
});

test('buildProxyCurlArgs routes SMSBower HTTP request through configured proxy', () => {
  const { buildProxyCurlArgs } = require('./auto_helpers');
  assert.deepEqual(
    buildProxyCurlArgs('https://smsbower.page/stubs/handler_api.php?action=getCountries', 'http://127.0.0.1:7890'),
    ['-fsSL', '--max-time', '30', '--retry', '1', '--retry-delay', '1', '-A', 'Mozilla/5.0', '-x', 'http://127.0.0.1:7890', 'https://smsbower.page/stubs/handler_api.php?action=getCountries'],
  );
});

test('verification code wait defaults are short bounded polling values', () => {
  const { codeSubmitTiming } = require('./auto_helpers');
  assert.deepEqual(codeSubmitTiming({}), { pollMs: 500, timeoutMs: 10000 });
  assert.deepEqual(codeSubmitTiming({ CODE_SUBMIT_POLL_MS: '250', CODE_SUBMIT_WAIT_MS: '3000' }), { pollMs: 250, timeoutMs: 3000 });
});

test('API key generation defaults to current-page fetch without navigating to keys page', () => {
  const { apiKeyGenerationOptions } = require('./auto_helpers');
  assert.deepEqual(apiKeyGenerationOptions({}), { navigateFirst: false });
  assert.deepEqual(apiKeyGenerationOptions({ API_KEY_GOTO_KEYS: '1' }), { navigateFirst: true });
});

test('Chile phone candidate requires mobile local number starting with 9', () => {
  const { isLikelyMobilePhoneForDialCode } = require('./auto_helpers');
  assert.equal(isLikelyMobilePhoneForDialCode({ dialCode: '+56', localNumber: '912345678' }), true);
  assert.equal(isLikelyMobilePhoneForDialCode({ dialCode: '+56', localNumber: '612345678' }), false);
  assert.equal(isLikelyMobilePhoneForDialCode({ dialCode: '+56', localNumber: '' }), false);
  assert.equal(isLikelyMobilePhoneForDialCode({ dialCode: '+62', localNumber: '8123456789' }), true);
});

test('phone submit force plan does not write hidden phone_number because React mask can clear local_number', () => {
  const { phoneSubmitForcePlan } = require('./auto_helpers');
  assert.deepEqual(phoneSubmitForcePlan({ countryDigits: '56', localNumber: '912345678', full: '+56912345678' }), {
    writeCountry: true,
    writeLocal: true,
    writeHidden: false,
  });
});

test('expired WorkOS authorization state is classified as a hard error', () => {
  const { isInvalidAuthorizationState } = require('./auto_helpers');
  assert.equal(isInvalidAuthorizationState('Sign in\nYour authentication session has expired. Please sign in again.', 'https://signin.ollama.com/?error=invalid_authorization_state'), true);
  assert.equal(isInvalidAuthorizationState('Verify your email', 'https://signin.ollama.com/email-verification'), false);
});

test('verification code submit strategy prefers UI button click over direct form requestSubmit', () => {
  const { codeSubmitStrategy } = require('./auto_helpers');
  assert.deepEqual(codeSubmitStrategy({}), { primary: 'ui_click', fallback: 'request_submit' });
});

test('mail verification code submit strategy disables requestSubmit fallback', () => {
  const { codeSubmitStrategy } = require('./auto_helpers');
  assert.deepEqual(codeSubmitStrategy({ CODE_SUBMIT_CONTEXT: 'mail_code' }), { primary: 'ui_click', fallback: 'none' });
});

test('OS click fallback is opt-in to avoid multi-window coordinate drift', () => {
  const { shouldUseOsClickFallback } = require('./auto_helpers');
  assert.equal(shouldUseOsClickFallback(undefined), false);
  assert.equal(shouldUseOsClickFallback(''), false);
  assert.equal(shouldUseOsClickFallback('0'), false);
  assert.equal(shouldUseOsClickFallback('1'), true);
});
