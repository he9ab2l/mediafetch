"""优化器测试：验证状态持久化与跳过规则，不实际跑 gifsicle。"""
import json
import os
import tempfile

from mediafetch.optimize import MAX_BYTES, Optimizer


def _touch(root, name, size):
    os.makedirs(os.path.join(root, 'stickers'), exist_ok=True)
    path = os.path.join(root, 'stickers', name)
    with open(path, 'wb') as f:
        f.write(b'x' * size)
    return path


def test_candidates_sorted_by_size():
    with tempfile.TemporaryDirectory() as tmp:
        _touch(tmp, 'small.gif', 200 * 1024)
        _touch(tmp, 'big.gif', 900 * 1024)
        o = Optimizer(tmp)
        c = o.candidates(min_bytes=100 * 1024)
        assert [n for _, n in c] == ['big.gif', 'small.gif']


def test_tiny_files_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        _touch(tmp, 'tiny.gif', 10 * 1024)
        assert Optimizer(tmp).candidates() == []


def test_oversized_files_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        _touch(tmp, 'huge.gif', MAX_BYTES + 1024)
        assert Optimizer(tmp).candidates() == []


def test_done_entries_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        _touch(tmp, 'a.gif', 200 * 1024)
        o = Optimizer(tmp)
        o.done['a.gif'] = {'status': 'ok'}
        assert o.candidates() == []


def test_state_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        o = Optimizer(tmp)
        o.done['a.gif'] = {'status': 'ok', 'before': 100, 'after': 50, 'saved': 0.5}
        o.save()
        o2 = Optimizer(tmp)
        assert o2.done['a.gif']['after'] == 50


def test_summary_aggregates():
    with tempfile.TemporaryDirectory() as tmp:
        o = Optimizer(tmp)
        o.done = {
            'a.gif': {'status': 'ok', 'before': 100, 'after': 50},
            'b.gif': {'status': 'ok', 'before': 200, 'after': 100},
            'c.gif': {'status': 'skip'},
        }
        s = o.summary()
        assert s['count'] == 2
        assert s['before'] == 300
        assert s['saved'] == 150
        assert s['ratio'] == 0.5
