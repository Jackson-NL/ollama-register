# -*- coding: utf-8 -*-
"""Turnstile 处理: 半自动(人工点击)或打码平台自动。"""
import logging
import time

log = logging.getLogger('registrar.captcha')


class TurnstileError(Exception):
    pass


def wait_and_handle_turnstile(page, cfg, timeout=120):
    """等待/处理 Cloudflare Turnstile 人机验证。

    返回 True 表示验证通过(拿到 bot_detection_token 或页面已跳转)。
    半自动模式: 弹出提示等人工点击。
    打码模式: 调用对应服务(capsolver/2captcha)。
    """
    start = time.time()
    while time.time() - start < timeout:
        # 页面已离开(验证通过并提交)
        url = page.url
        if 'signin.ollama.com' not in url:
            log.info('页面已跳转: %s', url[:120])
            return True

        # 检查 bot_detection_token 是否已注入
        token = page.evaluate("""(() => {
            const el = document.querySelector('input[name="bot_detection_token"]');
            return el ? el.value : '';
        })()""")
        if token:
            log.info('Turnstile token 已获得: %s...', token[:20])
            return True

        # 检查是否出现验证框
        has_widget = page.evaluate("""(() => {
            return !!document.getElementById('cf-turnstile') ||
                   !!document.querySelector('iframe[src*="challenges.cloudflare.com"]');
        })()""")
        if has_widget:
            log.warning('检测到 Turnstile 人机验证, 请在浏览器窗口中完成验证...')
            if cfg.captcha_service and cfg.captcha_api_key:
                log.info('使用打码平台: %s', cfg.captcha_service)
                # TODO: 接打码平台 (capsolver createTask: TurnstileTaskProxyless)
                # siteKey: 0x4AAAAAAAMNIvC45A4Wjjln
                # 需要 page.url 作为 pageUrl 参数
                # 成功后 window.turnstile 注入 token 并提交
                raise TurnstileError('打码平台接入待实现, 请配置半自动模式')
            # 半自动: 等待人工
            time.sleep(3)
            continue

        time.sleep(1.5)

    log.warning('Turnstile 等待超时')
    return False
