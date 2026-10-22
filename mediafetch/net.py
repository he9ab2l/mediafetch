"""HTTP 层：只管发请求、重试、取字节。不含任何平台知识。

所有网络行为集中在这里，方便统一加代理 / 限速 / UA 策略。
"""
import time
import urllib.request

CRAWLER_UA = ('Mozilla/5.0 (compatible; Googlebot/2.1; '
              '+http://www.google.com/bot.html)')
BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

RETRIES = 3
BACKOFF = 1.0   # 秒，按 attempt 线性增长


def fetch(url, ua=CRAWLER_UA, timeout=60, retries=RETRIES, encoding='utf-8'):
    """GET 一个页面，返回 (最终 URL, 文本)。跟随重定向，失败重试。

    并发下 Meta 边缘节点偶发 SSL EOF；不重试会把整条回复链断在那里。
    """
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url, headers={'User-Agent': ua, 'Accept-Language': 'en-US,en;q=0.9'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.geturl(), r.read().decode(encoding, 'replace')
        except Exception as e:
            last = e
            if attempt + 1 < retries:
                time.sleep(BACKOFF * (attempt + 1))
    raise last


def get_bytes(url, ua=BROWSER_UA, timeout=180, retries=2):
    """取一份原始字节。"""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': ua})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            if attempt + 1 < retries:
                time.sleep(BACKOFF)
    raise last


def get_first(urls, ua=BROWSER_UA, timeout=180, retries=2):
    """按优先级尝试多个候选地址，返回 (命中的 URL, bytes)。"""
    last = None
    for u in urls:
        try:
            return u, get_bytes(u, ua, timeout, retries)
        except Exception as e:
            last = e
    raise last
