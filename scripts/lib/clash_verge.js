const fs = require('fs');
const os = require('os');
const path = require('path');

function firstDefined(...values) {
  return values.find(value => value !== undefined && value !== null && String(value).trim() !== '');
}

function discoverConfigPath(env = process.env) {
  const explicit = firstDefined(env.CLASH_CONFIG_PATH);
  if (explicit) return path.resolve(String(explicit));
  if (process.platform !== 'win32') return null;
  const appData = env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming');
  const candidates = [
    path.join(appData, 'io.github.clash-verge-rev.clash-verge-rev', 'config.yaml'),
    path.join(appData, 'clash-verge-rev', 'config.yaml'),
  ];
  return candidates.find(file => fs.existsSync(file)) || null;
}

function readLocalConfig(file) {
  if (!file) return {};
  try {
    const text = fs.readFileSync(file, 'utf8');
    const secret = /^secret:\s*["']?([^"'\r\n]+)["']?\s*$/mi.exec(text)?.[1]?.trim();
    const mixedPort = /^mixed-port:\s*(\d+)\s*$/mi.exec(text)?.[1];
    const controller = /^external-controller:\s*["']?([^"'\r\n]+)["']?\s*$/mi.exec(text)?.[1]?.trim();
    return { secret, mixedPort: mixedPort ? Number(mixedPort) : null, controller };
  } catch {
    return {};
  }
}

function resolveClashSettings(env = process.env) {
  const configPath = discoverConfigPath(env);
  const local = readLocalConfig(configPath);
  let controller = String(firstDefined(env.CLASH_CONTROLLER_URL, local.controller, 'http://127.0.0.1:9090'));
  if (!/^https?:\/\//i.test(controller)) controller = `http://${controller}`;
  const proxyPort = Number(firstDefined(env.CLASH_PROXY_PORT, local.mixedPort, 7890));
  return {
    controllerUrl: controller.replace(/\/$/, ''),
    proxyUrl: String(firstDefined(env.CLASH_PROXY_URL, `http://127.0.0.1:${proxyPort}`)),
    secret: firstDefined(env.CLASH_SECRET, local.secret) || '',
    configPath,
  };
}

function makeHeaders(secret) {
  return secret ? { Authorization: `Bearer ${secret}`, 'content-type': 'application/json' } : { 'content-type': 'application/json' };
}

function isSelectableNode(name) {
  const value = String(name || '').trim();
  if (!value) return false;
  if (/^(剩余流量|距离下次重置|套餐到期|建议[:：]|放丢失官网)/.test(value)) return false;
  if (/^(DIRECT|REJECT|GLOBAL|AUTO)$/i.test(value)) return false;
  return true;
}

function makeNodeExcludeMatcher(pattern) {
  if (!pattern) return () => false;
  if (pattern instanceof RegExp) return value => pattern.test(String(value || ''));
  const raw = String(pattern);
  try {
    const rx = new RegExp(raw, 'i');
    return value => rx.test(String(value || ''));
  } catch {
    return value => String(value || '').toLowerCase().includes(raw.toLowerCase());
  }
}

function chooseNextNode(status, options = {}) {
  const groupName = String(options.group || status?.preferredGroup || 'SELECT');
  const group = (status?.groups || []).find(item => item.name === groupName);
  if (!group) return null;
  const isExcluded = makeNodeExcludeMatcher(options.excludePattern || process.env.CLASH_ROTATE_EXCLUDE || '香港|Hong Kong|HK|🇭🇰');
  const candidates = (group.candidates || []).filter(name => isSelectableNode(name) && !isExcluded(name));
  if (!candidates.length) return null;
  const current = String(group.now || '');
  const currentIndex = candidates.indexOf(current);
  const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % candidates.length : 0;
  return { group: group.name, node: candidates[nextIndex], previous: group.now || null, candidates };
}

function createClashController(options = {}) {
  const settings = { ...resolveClashSettings(), ...options };
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== 'function') throw new Error('global fetch is unavailable');

  async function request(endpoint, init = {}) {
    const response = await fetchImpl(`${settings.controllerUrl}${endpoint}`, {
      ...init,
      headers: { ...makeHeaders(settings.secret), ...(init.headers || {}) },
    });
    const text = await response.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = text; }
    if (!response.ok) throw new Error(`Clash controller ${response.status}: ${typeof body === 'string' ? body.slice(0, 200) : body?.message || 'request failed'}`);
    return body;
  }

  async function status() {
    const [version, proxyData] = await Promise.all([request('/version'), request('/proxies')]);
    const proxies = proxyData?.proxies || {};
    const groups = Object.entries(proxies)
      .filter(([, value]) => value?.type === 'Selector' && Array.isArray(value.all) && value.all.length)
      .map(([name, value]) => ({ name, type: value.type, now: value.now || null, candidates: value.all.filter(isSelectableNode) }));
    const root = groups.find(group => group.name === 'GLOBAL') || groups[0] || null;
    const path = [];
    let current = root;
    const visited = new Set();
    while (current?.name && !visited.has(current.name) && path.length < 8) {
      visited.add(current.name);
      path.push({ group: current.name, node: current.now || null });
      const next = proxies[current.now];
      current = next?.type === 'Selector' ? { name: current.now, now: next.now || null } : null;
    }
    return {
      version: version?.version || null,
      groups,
      preferredGroup: root?.name || null,
      activeRoute: path,
      proxyUrl: settings.proxyUrl,
    };
  }

  async function select(group, node) {
    const groupName = String(group || '').trim();
    const nodeName = String(node || '').trim();
    if (!groupName || !nodeName) throw new Error('proxy group and node are required');
    const current = await status();
    const target = current.groups.find(item => item.name === groupName);
    if (!target) throw new Error(`proxy group not found: ${groupName}`);
    if (!target.candidates.includes(nodeName)) throw new Error(`proxy node not found in group: ${nodeName}`);
    await request(`/proxies/${encodeURIComponent(groupName)}`, {
      method: 'PUT',
      body: JSON.stringify({ name: nodeName }),
    });
    return { ...(await status()), selected: { group: groupName, node: nodeName } };
  }

  async function rotate(options = {}) {
    const current = await status();
    const plan = chooseNextNode(current, options);
    if (!plan) return { rotated: false, reason: 'no_candidate', status: current };
    const after = await select(plan.group, plan.node);
    return { rotated: true, group: plan.group, previous: plan.previous, node: plan.node, candidateCount: plan.candidates.length, status: after };
  }

  return { settings, request, status, select, rotate };
}

module.exports = {
  createClashController,
  discoverConfigPath,
  readLocalConfig,
  resolveClashSettings,
  isSelectableNode,
  chooseNextNode,
};
