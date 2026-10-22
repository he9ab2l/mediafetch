"""存档层测试：不联网，验证两级去重、目录布局、manifest 记账。"""
import json
import os
import tempfile

from mediafetch.store import Store, safe_name


def test_safe_name():
    assert safe_name('DduyhhvGWfl') == 'DduyhhvGWfl'
    assert safe_name('a/b c') == 'a_b_c'
    assert safe_name('') == 'x'
    assert safe_name('__..') == 'x'


def test_content_dedup_same_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        s = Store(tmp)
        p1, new1 = s._write(b'GIF89a', os.path.join(tmp, 'a', 'x.gif'), 'k1',
                            kind='sticker')
        p2, new2 = s._write(b'GIF89a', os.path.join(tmp, 'b', 'y.gif'), 'k2',
                            kind='sticker')
        assert new1 is True and new2 is False
        assert p1 == p2 == os.path.join('a', 'x.gif')
        assert s.count == 1 and s.skipped == 1
        assert not os.path.exists(os.path.join(tmp, 'b', 'y.gif'))


def test_manifest_records_duplicate_of():
    with tempfile.TemporaryDirectory() as tmp:
        s = Store(tmp)
        s._write(b'x', os.path.join(tmp, 'a', '1.jpg'), 'k1',
                 kind='image', source='post:P1')
        s._write(b'x', os.path.join(tmp, 'b', '1.jpg'), 'k2',
                 kind='image', source='post:P2')
        rows = [json.loads(l) for l in open(os.path.join(tmp, 'manifest.jsonl'))]
        assert rows[0]['source'] == 'post:P1'
        assert rows[1]['duplicate_of'] == os.path.join('b', '1.jpg')
        assert rows[1]['path'] == os.path.join('a', '1.jpg')


def test_task_level_skip_after_restart():
    """任务级去重：manifest 记过 key，续跑直接跳过，不再发请求。"""
    with tempfile.TemporaryDirectory() as tmp:
        s = Store(tmp)
        s._write(b'data', os.path.join(tmp, 'a', 'x.gif'), 'a/x', kind='sticker')
        s2 = Store(tmp)
        assert s2.is_done('a/x') is True
        assert s2.is_done('a/y') is False


def test_resume_loads_hash_and_keys():
    with tempfile.TemporaryDirectory() as tmp:
        Store(tmp)._write(b'payload', os.path.join(tmp, 'a', '1.jpg'), 'k1',
                          kind='image')
        s2 = Store(tmp)
        assert list(s2.by_hash.values()) == [os.path.join('a', '1.jpg')]
        _, new = s2._write(b'payload', os.path.join(tmp, 'a', '2.jpg'), 'k2',
                           kind='image')
        assert new is False


def test_save_json_and_index():
    with tempfile.TemporaryDirectory() as tmp:
        s = Store(tmp)
        rel, new = s.save_json({'a': 1}, os.path.join('posts', 'P1', 'post.json'),
                               'posts/P1/post.json', 'post:u')
        assert new and rel == os.path.join('posts', 'P1', 'post.json')
        assert json.load(open(os.path.join(tmp, rel))) == {'a': 1}
        idx = s.write_index({'scene': 'full'})
        assert json.load(open(idx)) == {'scene': 'full'}


def test_sticker_pool_flat_layout():
    """贴图进池：文件名就是 id，不带来源前缀。"""
    with tempfile.TemporaryDirectory() as tmp:
        s = Store(tmp)
        sticker = {'id': 'abc', 'sources': ['https://x/abc.gif']}
        # 不走网络：直接模拟落盘这一步
        dest = os.path.join(tmp, 'stickers', 'abc.gif')
        rel, new = s._write(b'GIF89a', dest, 'stickers/abc', kind='sticker')
        assert new and rel == os.path.join('stickers', 'abc.gif')
        assert s.is_done('stickers/abc')
        assert sticker['id'] in os.path.basename(rel)
