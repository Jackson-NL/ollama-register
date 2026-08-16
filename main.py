# -*- coding: utf-8 -*-
"""ollama 注册机 CLI 入口。

用法:
  python main.py --email user@example.com --password Secret123! --name "Display Name"
  python main.py -e user@mail.com -p Secret123! --headful
  python main.py -e user@mail.com -p Secret123! --captcha-service capsolver --captcha-key KEY
"""
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import parse_args
from src.registrar import Registrar


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    cfg = parse_args(sys.argv[1:])
    problems = cfg.validate()
    if problems:
        for p in problems:
            logging.error('配置错误: %s', p)
        print(__doc__)
        return 2

    reg = Registrar(cfg)
    try:
        result = reg.run()
        print(f'\n[OK] 注册流程完成: {result}')
        return 0
    except Exception as e:
        logging.error('注册失败: %s', e)
        return 1


if __name__ == '__main__':
    sys.exit(main())
