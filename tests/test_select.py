"""筛选层测试：纯逻辑，不联网。"""
from mediafetch.select import Select


def _rec():
    return {
        'code': 'P1',
        'media': [{'type': 'image', 'url': 'https://cdn/a.jpg'},
                  {'type': 'video', 'url': 'https://cdn/b.mp4'}],
        'stickers': [{'id': 's1', 'sources': ['https://g/s1.gif']}],
        'quoted': [{'code': 'Q1', 'media': [], 'stickers': [{'id': 'q1'}]}],
    }


def test_stickers_only():
    s = Select.stickers_only()
    r = _rec()
    assert [x['id'] for x in s.pick_stickers(r)] == ['s1']
    assert s.pick_media(r) == []
    assert s.useful(r) is True


def test_media_only():
    s = Select.media_only()
    r = _rec()
    assert [m['type'] for m in s.pick_media(r)] == ['image', 'video']
    assert s.pick_stickers(r) == []


def test_all():
    s = Select.all()
    r = _rec()
    assert len(s.pick_media(r)) == 2
    assert len(s.pick_stickers(r)) == 1
    assert len(s.pick_quoted(r)) == 1


def test_no_quoted():
    s = Select.only('sticker', follow_quoted=False)
    assert s.pick_quoted(_rec()) == []


def test_useful_false_when_empty():
    s = Select.stickers_only()
    assert s.useful({'code': 'X', 'media': [{'type': 'image'}], 'stickers': []}) is False


def test_bad_kind_raises():
    try:
        Select.only('bogus')
    except ValueError as e:
        assert 'bogus' in str(e)
    else:
        raise AssertionError('应该抛 ValueError')
