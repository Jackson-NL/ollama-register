# -*- coding: utf-8 -*-
"""浏览器启动 + 反检测初始化。"""
import logging

log = logging.getLogger('registrar')

# WorkOS Radar 检测的自动化标记, 在页面加载前注入清理
STEALTH_INIT = """
// 清理 CDP/DevTools 相关自动化指纹
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
// 清理 puppeteer 检测 (chunk-5 检查 window/document 的 $cdc_ 前缀属性)
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
// playwright 检测: __playwright__binding__ / __pwInitScripts
try { delete window.__playwright__binding__; } catch (e) {}
// chrome 检测 (playwright 暴露 window.chrome 不完整时可补充)
"""


def launch_browser(playwright, cfg):
    """启动真实浏览器 (headful 默认, 过 Cloudflare TLS 指纹)。

    用系统安装的 Edge/Chrome (channel), 避免下载新浏览器。
    """
    browser_type = getattr(playwright, cfg.browser_type, None)
    if browser_type is None:
        raise RuntimeError(f'不支持的浏览器类型: {cfg.browser_type}')

    launch_opts = {
        'headless': cfg.headless,
        'args': [
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-popup-blocking',
            '--disable-blink-features=AutomationControlled',
            '--lang=en-US',
        ],
    }
    if cfg.proxy:
        launch_opts['proxy'] = {'server': cfg.proxy}
    # 优先使用系统 Edge/Chrome 通道
    if cfg.browser_type == 'edge':
        launch_opts['channel'] = 'msedge'
    elif cfg.browser_type == 'chrome':
        launch_opts['channel'] = 'chrome'

    log.info('启动浏览器: %s (headless=%s)', cfg.browser_type, cfg.headless)
    browser = browser_type.launch(**launch_opts)
    context = browser.new_context(
        viewport={'width': 1707, 'height': 1067},
        locale='en-US',
        timezone_id='Asia/Shanghai',
    )
    # 注入 stealth
    context.add_init_script(STEALTH_INIT)
    page = context.new_page()
    return browser, context, page
