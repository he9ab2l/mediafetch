"""下载层测试：用假 Store 替身，验证去重与失败记录。"""
import tempfile

from mediafetch import download as dlmod


class _FakeStore:
    """最小 Store 替身：只记调用，不落盘、不联网。"""

    def __init__(self):
        self.written = {}
        self.skipped = 0
        self.count = 0
        self.fail_next = None

    def is_done(self, key):
        return key in self.written

    def save_sticker(self, sticker, source):
        if self.fail_next:
            raise self.fail_next
        key = 'stickers/' + sticker['id']
        if key in self.written:
            self.skipped += 1
            return None, False
        self.written[key] = sticker
        self.count += 1
        return key, True

    def stats(self):
        return {'files': self.count, 'dupes': self.skipped,
                'unique': len(self.written)}


def test_same_sticker_id_downloaded_once():
    with tempfile.TemporaryDirectory() as tmp:
        d = dlmod.Downloader(tmp, workers=2)
        d.store = _FakeStore()
        posts = {
            'P1': {'code': 'P1', 'author': 'a',
                   'stickers': [{'id': 'same', 'sources': ['https://g/same.gif']}]},
            'P2': {'code': 'P2', 'author': 'b',
                   'stickers': [{'id': 'same', 'sources': ['https://g/same.gif']}]},
        }
        r = d.run(posts, log=lambda *_: None)
        assert r['new'] == 1
        # run() 内部先按 id 去重，第二个根本不会进 store
        assert d.store.count == 1
        assert d.store.skipped == 0


def test_duplicate_id_within_one_post():
    with tempfile.TemporaryDirectory() as tmp:
        d = dlmod.Downloader(tmp, workers=2)
        d.store = _FakeStore()
        posts = {'P1': {'code': 'P1', 'author': 'a', 'stickers': [
            {'id': 'x', 'sources': ['https://g/x.gif']},
            {'id': 'x', 'sources': ['https://g/x.gif']},
        ]}}
        r = d.run(posts, log=lambda *_: None)
        assert r['new'] == 1
        assert d.store.count == 1


def test_failure_is_recorded_not_raised():
    with tempfile.TemporaryDirectory() as tmp:
        d = dlmod.Downloader(tmp, workers=2)
        store = _FakeStore()
        store.fail_next = OSError('network down')
        d.store = store
        posts = {'P1': {'code': 'P1', 'author': 'a',
                        'stickers': [{'id': 'x', 'sources': ['https://g/x.gif']}]}}
        r = d.run(posts, log=lambda *_: None)
        assert r['new'] == 0
        assert len(d.failed) == 1
        assert 'network down' in d.failed[0][1]
