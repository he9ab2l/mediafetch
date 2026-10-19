"""解析层单元测试：不联网，用固定页面片段验证抽取逻辑。"""
import json

from mediafetch.platforms import threads


def _sjs(payload):
    return ('<html><script type="application/json" data-sjs>'
            + json.dumps(payload) + '</script></html>')


def test_media_single_image():
    post = {
        'code': 'AAA',
        'media_type': 1,
        'original_width': 1440,
        'original_height': 960,
        'image_versions2': {'candidates': [
            {'width': 150, 'url': 'https://cdn/x_s150x150.jpg'},
            {'width': 1440, 'url': 'https://cdn/x_1440.jpg'},
        ]},
    }
    media = threads.media_of(post)
    assert len(media) == 1
    assert media[0]['url'] == 'https://cdn/x_1440.jpg'
    assert media[0]['type'] == 'image'


def test_media_video():
    post = {'code': 'BBB', 'media_type': 2,
            'video_versions': [{'url': 'https://cdn/v.mp4'}]}
    media = threads.media_of(post)
    assert media == [{'type': 'video', 'url': 'https://cdn/v.mp4',
                      'width': None, 'height': None}]


def test_media_carousel():
    post = {
        'code': 'CCC',
        'media_type': 8,
        'carousel_media': [
            {'image_versions2': {'candidates': [{'width': 800, 'url': 'https://cdn/1.jpg'}]}},
            {'video_versions': [{'url': 'https://cdn/2.mp4'}]},
        ],
    }
    media = threads.media_of(post)
    assert [m['type'] for m in media] == ['image', 'video']


def test_stickers_dedup():
    frag = lambda sid: {'inline_sticker_fragment': {'sticker_id': sid, 'sticker_url': f'https://g/{sid}.gif'}}
    post = {'code': 'DDD', 'text_post_app_info': {'text_fragments': {'fragments': [
        frag('s1'), {'plaintext': 'x'}, frag('s1'), frag('s2'),
    ]}}}
    stickers = threads.stickers_of(post)
    assert [s['id'] for s in stickers] == ['s1', 's2']


def test_unique_posts_dedup_and_junk_skip():
    payload = {'require': [['ScheduledServerJS', 'handle', None, [{'__bbox': {'x': [
        {'code': 'P1', 'image_versions2': {'candidates': []}},
        {'code': 'P1', 'image_versions2': {'candidates': []}},
        {'code': 'P2', 'video_versions': []},
    ]}}]]]}
    posts = threads.unique_posts(_sjs(payload))
    assert [p['code'] for p in posts] == ['P1', 'P2']


def test_caption_strips_newlines():
    assert threads.caption_of({'caption': {'text': 'a\nb'}}) == 'a b'


def test_biggest_image_skips_rsrc():
    post = {'image_versions2': {'candidates': [
        {'width': 9999, 'url': 'https://static/rsrc.php/avatar.jpg'},
        {'width': 800, 'url': 'https://cdn/real.jpg'},
    ]}}
    assert threads.media_of(post)[0]['url'] == 'https://cdn/real.jpg'


def test_record_flags_reply():
    root = {'code': 'R', 'image_versions2': {'candidates': []},
            'text_post_app_info': {'is_reply': False}}
    reply = {'code': 'X', 'image_versions2': {'candidates': []},
             'text_post_app_info': {'is_reply': True}}
    assert threads._record(root, 'u')['is_reply'] is False
    assert threads._record(reply, 'u')['is_reply'] is True


def test_replies_excludes_root_and_non_replies():
    nodes = [
        {'code': 'ROOT', 'image_versions2': {'candidates': []},
         'text_post_app_info': {'is_reply': False}},
        {'code': 'R1', 'image_versions2': {'candidates': [{'width': 800, 'url': 'https://cdn/r1.jpg'}]},
         'text_post_app_info': {'is_reply': True}},
        {'code': 'REC', 'image_versions2': {'candidates': [{'width': 800, 'url': 'https://cdn/rec.jpg'}]},
         'text_post_app_info': {'is_reply': False}},
    ]
    out = threads._replies(nodes, 'ROOT')
    assert [r['code'] for r in out] == ['R1']
    assert out[0]['media'][0]['url'] == 'https://cdn/r1.jpg'


def test_claimed_replies():
    assert threads._claimed_replies('..."direct_reply_count":26,...') == 26
    assert threads._claimed_replies('nothing here') is None
