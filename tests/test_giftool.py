"""GIF 工具测试：用合成 GIF，不联网。"""
import os
import tempfile

from PIL import Image, ImageDraw

from mediafetch import giftool


def _gif(tmp, name='a.gif', frames=3, size=(40, 40), color='white'):
    path = os.path.join(tmp, name)
    imgs = []
    for i in range(frames):
        im = Image.new('RGB', size, color)
        ImageDraw.Draw(im).rectangle((i * 3, 5, i * 3 + 8, 20), fill='black')
        imgs.append(im)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=100, loop=0)
    return path


def test_probe_static():
    with tempfile.TemporaryDirectory() as tmp:
        p = _gif(tmp, frames=1)
        r = giftool.probe(p)
        assert r['frames'] == 1
        assert r['animated'] is False
        assert r['width'] == 40


def test_probe_animated():
    with tempfile.TemporaryDirectory() as tmp:
        p = _gif(tmp, frames=4)
        r = giftool.probe(p)
        assert r['frames'] == 4
        assert r['animated'] is True
        assert r['duration_ms'] > 0


def test_frame_deltas_detects_motion():
    with tempfile.TemporaryDirectory() as tmp:
        p = _gif(tmp, frames=5)
        d = giftool.frame_deltas(p)
        assert len(d) > 0
        assert max(d) > 0


def test_frame_hashes_length():
    with tempfile.TemporaryDirectory() as tmp:
        p = _gif(tmp, frames=3)
        assert len(giftool.frame_hashes(p)) == 3


def test_first_frame_hash_stable():
    with tempfile.TemporaryDirectory() as tmp:
        a = _gif(tmp, 'a.gif', frames=3)
        b = _gif(tmp, 'b.gif', frames=3)
        assert giftool.first_frame_hash(a) == giftool.first_frame_hash(b)


def test_contact_sheet():
    with tempfile.TemporaryDirectory() as tmp:
        paths = [_gif(tmp, f'{i}.gif', frames=2) for i in range(4)]
        out = os.path.join(tmp, 'sheet.jpg')
        _, n = giftool.contact_sheet(paths, out, cols=2, cell=40)
        assert n == 4
        assert os.path.exists(out)


def test_survey_reports():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, 'stickers'))
        for i in range(3):
            _gif(os.path.join(tmp, 'stickers'), f'{i}.gif', frames=2)
        rep = giftool.survey(tmp)
        assert rep['count'] == 3
        assert rep['animated'] == 3
        assert rep['bytes'] > 0
