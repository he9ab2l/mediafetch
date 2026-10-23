"""流水线状态测试：验证持久化与续跑，不联网。"""
import json
import os
import tempfile

from mediafetch.pipeline import Pipeline


def _seed(pipe, code='C1', author='alice', stickers=2):
    pipe.d.posts[code] = {
        'code': code, 'author': author, 'taken_at': 0, 'caption': '',
        'stickers': [{'id': f's{i}', 'sources': [f'https://g/s{i}.gif']}
                     for i in range(stickers)],
    }
    pipe.d.authors.add(author)


def test_save_and_reload():
    with tempfile.TemporaryDirectory() as tmp:
        p = Pipeline(tmp)
        _seed(p)
        p.queries_done.add('sticker')
        p.profiles_done.add('alice')
        p.save()

        p2 = Pipeline(tmp)
        assert 'C1' in p2.d.posts
        assert p2.d.sticker_count() == 2
        assert 'sticker' in p2.queries_done
        assert 'alice' in p2.profiles_done


def test_export_codes_sorted_by_sticker_count():
    with tempfile.TemporaryDirectory() as tmp:
        p = Pipeline(tmp)
        _seed(p, 'C1', 'alice', stickers=1)
        _seed(p, 'C2', 'bob', stickers=5)
        out = p.export_codes()
        assert [c for c, _, _ in out] == ['C2', 'C1']
        assert out[0][1] == 'https://www.threads.com/@bob/post/C2'


def test_state_file_is_valid_json():
    with tempfile.TemporaryDirectory() as tmp:
        p = Pipeline(tmp)
        _seed(p)
        p.save()
        with open(p.path, encoding='utf-8') as f:
            s = json.load(f)
        assert s['posts']['C1']['author'] == 'alice'
        assert s['stats']['kept'] == 0


def test_search_round_skips_done_queries():
    with tempfile.TemporaryDirectory() as tmp:
        p = Pipeline(tmp)
        p.queries_done.add('a')
        assert p.search_round(['a']) == 0
