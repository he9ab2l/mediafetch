"""发现层测试：不联网，用固定节点验证过滤逻辑。"""
import datetime

from mediafetch.discover import Discoverer, _age_days


def _node(code, author, stickers, taken_at=None):
    frags = [{'inline_sticker_fragment': {'sticker_id': s, 'sticker_url': f'https://g/{s}.gif'}}
             for s in stickers]
    return {'code': code,
            'user': {'username': author},
            'taken_at': taken_at,
            'text_post_app_info': {'text_fragments': {'fragments': frags}}}


def test_age_days():
    now = 1000000.0
    assert _age_days({'taken_at': now - 86400}, now) == 1.0
    assert _age_days({}, now) is None


def test_keeps_recent_post_with_sticker():
    d = Discoverer(days=30)
    now = d.now
    p = _node('C1', 'alice', ['s1', 's2'], now - 86400)
    assert d._consider(p) is True
    assert len(d.posts) == 1
    assert d.posts['C1']['author'] == 'alice'
    assert len(d.posts['C1']['stickers']) == 2
    assert 'alice' in d.authors


def test_rejects_old_post():
    d = Discoverer(days=30)
    p = _node('C2', 'bob', ['s1'], d.now - 40 * 86400)
    assert d._consider(p) is False
    assert d.stats['too_old'] == 1
    # 老帖的作者仍然收进池子，可能还有新帖
    assert 'bob' in d.authors


def test_rejects_post_without_sticker():
    d = Discoverer(days=30)
    p = _node('C3', 'carol', [], d.now - 86400)
    assert d._consider(p) is False
    assert d.stats['no_sticker'] == 1


def test_ignores_duplicate_code():
    d = Discoverer(days=30)
    p = _node('C4', 'dan', ['s1'], d.now - 86400)
    assert d._consider(p) is True
    assert d._consider(p) is False
    assert len(d.posts) == 1


def test_sticker_count_sums_records():
    d = Discoverer(days=30)
    d._consider(_node('C5', 'e', ['a', 'b'], d.now - 86400))
    d._consider(_node('C6', 'f', ['c'], d.now - 86400))
    assert d.sticker_count() == 3
