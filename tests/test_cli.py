"""CLI 层去重逻辑测试。"""
from mediafetch.__main__ import Seen


def test_media_dedup_by_url():
    s = Seen()
    a = {'type': 'video', 'url': 'https://cdn/x.mp4'}
    b = {'type': 'video', 'url': 'https://cdn/x.mp4'}
    c = {'type': 'image', 'url': 'https://cdn/y.jpg'}
    assert s.media(a) is True
    assert s.media(b) is False   # 同 URL，回复与其引用块常见
    assert s.media(c) is True


def test_sticker_dedup_by_id():
    s = Seen()
    assert s.sticker({'id': 'abc'}) is True
    assert s.sticker({'id': 'abc'}) is False
    assert s.sticker({'id': 'def'}) is True


def test_urls_and_stickers_independent():
    s = Seen()
    assert s.media({'url': 'https://cdn/a.gif'}) is True
    assert s.sticker({'id': 'https://cdn/a.gif'}) is True
