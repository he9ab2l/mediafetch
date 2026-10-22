"""媒体工具层测试：纯函数，不联网。"""
from mediafetch.media import biggest_image, guess_ext, is_junk


def test_guess_ext():
    assert guess_ext('https://x/o1/v/t16/a.mp4') == 'mp4'
    assert guess_ext('https://media.giphy.com/media/x/source.gif') == 'gif'
    assert guess_ext('https://cdn/a.webp') == 'webp'
    assert guess_ext('https://cdn/a.jpg') == 'jpg'


def test_is_junk():
    assert is_junk('https://static/rsrc.php/avatar.jpg') is True
    assert is_junk('https://cdn/profile_pic/x.jpg') is True
    assert is_junk('https://cdn/real.jpg') is False


def test_biggest_image_skips_junk():
    node = {'image_versions2': {'candidates': [
        {'width': 9999, 'url': 'https://static/rsrc.php/avatar.jpg'},
        {'width': 800, 'url': 'https://cdn/real.jpg'},
    ]}}
    assert biggest_image(node) == 'https://cdn/real.jpg'
    assert biggest_image({}) is None
