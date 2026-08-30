const test = require('node:test');
const assert = require('node:assert/strict');
const { createRunLogger, normalizeEvent } = require('./run_logger');

test('run logger emits stable structured lines and redacts sensitive values', () => {
  const lines = [];
  const logger = createRunLogger({
    scope: 'FULL',
    now: () => new Date('2026-08-26T00:00:00.000Z'),
    write: line => lines.push(line),
  });

  logger.log('sms code', '123456');
  logger.log('PHONE_RENTED', {
    email: 'ollamaauto@example.com',
    rawNumber: '+573159872610',
    api_key: 'secret-key',
    activationId: '123',
  });

  assert.match(lines[0], /^\[2026-08-26T00:00:00\.000Z\]\[INFO\]\[FULL\] SMS_CODE /);
  assert.equal(lines[0].includes('123456'), false);
  assert.match(lines[1], /oll\*\*\*@example\.com/);
  assert.match(lines[1], /\+\*+610/);
  assert.equal(lines[1].includes('secret-key'), false);

  logger.log('STATUS', { apiKey: true, tokenLikeCount: 2 });
  assert.match(lines[2], /"apiKey":true/);
  assert.match(lines[2], /"tokenLikeCount":2/);
  logger.log('SMSBOWER', { text: 'STATUS_OK:397030', url: 'https://example.test/?authorization_session_id=secret-session' });
  assert.equal(lines[3].includes('397030'), false);
  assert.equal(lines[3].includes('secret-session'), false);

  logger.log('BROWSER', 'warning', 'repeated warning');
  logger.log('BROWSER', 'warning', 'repeated warning');
  assert.equal(lines.filter(line => line.includes('repeated warning')).length, 1);
  assert.equal(normalizeEvent('phone rejected retry'), 'PHONE_REJECTED_RETRY');
});
