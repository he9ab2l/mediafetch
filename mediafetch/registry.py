"""平台注册表。新增平台时：写 mediafetch/platforms/<name>.py，在此登记。"""
from .platforms import threads

# name -> (是否支持帖子链接, 是否支持账号, post 函数, profile 函数)
PLATFORMS = {
    'threads': {
        'hosts': ('threads.com', 'threads.net'),
        'post': threads.post,
        'profile': threads.profile,
    },
}

__all__ = ['PLATFORMS', 'detect']


def detect(url):
    """按域名判断平台名，返回 None 表示不支持。"""
    host = url.split('//', 1)[-1].split('/', 1)[0].lower().lstrip('www.')
    for name, spec in PLATFORMS.items():
        if any(host == h or host.endswith('.' + h) for h in spec['hosts']):
            return name
    return None
