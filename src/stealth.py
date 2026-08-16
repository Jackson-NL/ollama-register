# -*- coding: utf-8 -*-
"""完整 stealth 注入: 补齐 chrome.runtime 等 Playwright 缺失特征。

基于抓包分析: Turnstile 600010 = 自动化环境检测失败。
根因: Playwright 浏览器 window.chrome.runtime === undefined (无扩展),
Cloudflare 因此拒绝渲染 Turnstile widget。

真实浏览器(带扩展)chrome.runtime 存在。此处补齐完整伪造。
"""
STEALTH_FULL = """
// ===== 1. navigator.webdriver =====
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// ===== 2. 清理 CDP 属性 =====
for (const k of Object.getOwnPropertyNames(window)) {
    if (k.startsWith('$cdc_') || k.startsWith('cdc_')) {
        try { delete window[k]; } catch (e) {}
    }
}
for (const k of Object.getOwnPropertyNames(document)) {
    if (k.startsWith('$cdc_') || k.startsWith('cdc_')) {
        try { delete document[k]; } catch (e) {}
    }
}

// ===== 3. 补齐 window.chrome (Playwright 缺失 runtime) =====
(() => {
    const chrome = window.chrome || {};
    const makeObj = () => {
        const o = {};
        try { o.loadTimes = () => ({
            commitLoadTime: 0, firstPaintAfterLoadTime: 0,
            firstPaintTime: 0, navigationType: 'Other', requestTime: 0,
            startLoadTime: 0, wasFetchedViaSpdy: true, wasNpnNegotiated: true,
            wasAlternateProtocolAvailable: false, wasFetchedViaSpdy: true,
        }); } catch (e) {}
        try { o.csi = () => ({ startE: 0, onloadT: Date.now(), pageT: Date.now() }); } catch (e) {}
        return o;
    };
    try {
        if (!chrome.runtime) {
            Object.defineProperty(chrome, 'runtime', {
                value: makeObj(),
                configurable: true, writable: true,
            });
        }
        if (!chrome.loadTimes) Object.defineProperty(chrome, 'loadTimes', { value: makeObj().loadTimes, configurable: true, writable: true });
        if (!chrome.csi) Object.defineProperty(chrome, 'csi', { value: makeObj().csi, configurable: true, writable: true });
        if (!chrome.app) Object.defineProperty(chrome, 'app', { value: {}, configurable: true, writable: true });
    } catch (e) {}
    window.chrome = chrome;
})();

// ===== 4. plugins 补足 =====
try {
    const pluginNames = [
        ['PDF Viewer', 'Portable Document Format', 'application/pdf', 'pdf'],
        ['Chrome PDF Viewer', 'Portable Document Format', 'application/pdf', 'pdf'],
        ['Chromium PDF Viewer', 'Portable Document Format', 'application/pdf', 'pdf'],
        ['Microsoft Edge PDF Viewer', 'Portable Document Format', 'application/pdf', 'pdf'],
        ['WebKit built-in PDF', 'Portable Document Format', 'application/pdf', 'pdf'],
    ];
    if (navigator.plugins && navigator.plugins.length < 5) {
        // plugins 是只读的, 直接 defineProperty 覆盖
        const fake = [];
        const PluginCtor = (function() { try { return navigator.plugins[0].constructor; } catch(e) { return null; } })();
        for (const [name, desc, type, suffix] of pluginNames) {
            try {
                const p = PluginCtor ? new PluginCtor() : { name: '', filename: '', description: '', length: 0 };
                try {
                    Object.defineProperty(p, 'name', { value: name, configurable: false });
                    Object.defineProperty(p, 'filename', { value: name + '.dll', configurable: false });
                    Object.defineProperty(p, 'description', { value: desc, configurable: false });
                } catch (e) {}
                fake.push(p);
            } catch (e) {}
        }
        try {
            Object.defineProperty(navigator, 'plugins', { get: () => fake, configurable: true });
        } catch (e) {}
    }
} catch (e) {}

// ===== 5. 其他 =====
try {
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
} catch (e) {}
try {
    // permissions.query 正常返回
} catch (e) {}
"""
