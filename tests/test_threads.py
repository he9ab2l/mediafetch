"""解析层单元测试：不联网，用固定页面片段验证抽取逻辑。"""
import json

from mediafetch.page import unique_nodes
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
    assert len(media) == 1
    assert media[0]['type'] == 'video'
    assert media[0]['url'] == 'https://cdn/v.mp4'
    # 无 dash manifest 时两个字段为 None，下载回退 progressive
    assert media[0]['dash_video'] is None
    assert media[0]['dash_audio'] is None


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
    posts = unique_nodes(_sjs(payload), threads._is_post_node)
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


def test_quoted_post_extracted():
    quoted = {'code': 'Q1', 'media_type': 8, 'caption': {'text': 'q'},
              'carousel_media': [
                  {'image_versions2': {'candidates': [{'width': 900, 'url': 'https://cdn/q1.jpg'}]}},
                  {'video_versions': [{'url': 'https://cdn/q2.mp4'}]},
              ]}
    post = {'code': 'R1', 'text_post_app_info': {'share_info': {'quoted_post': quoted}}}
    out = threads.quoted_of(post)
    assert len(out) == 1
    assert out[0]['kind'] == 'quoted_post'
    assert [m['type'] for m in out[0]['media']] == ['image', 'video']


def test_quoted_skips_empty():
    post = {'code': 'R2', 'text_post_app_info': {'share_info': {'quoted_post': {'code': None}}}}
    assert threads.quoted_of(post) == []


def test_next_cursor_only_from_direct_replies():
    payload = {'data': {'media': {'text_post_app_info': {
        'direct_replies': {'page_info': {'end_cursor': 'CUR', 'has_next_page': True}}}}}}
    assert threads._next_cursor(payload) == 'CUR'
    assert threads._next_cursor({'data': {'media': {}}}) is None


def test_claimed_replies():
    assert threads._claimed_replies('..."direct_reply_count":26,...') == 26
    assert threads._claimed_replies('nothing here') is None


def test_sticker_has_sources_priority():
    post = {'code': 'S', 'text_post_app_info': {'text_fragments': {'fragments': [
        {'inline_sticker_fragment': {'sticker_id': 'abc', 'sticker_url': 'https://cdn/abc/200.gif'}},
    ]}}}
    st = threads.stickers_of(post)[0]
    assert st['sources'][0].endswith('/abc/source.gif')
    assert st['sources'][1] == 'https://i.giphy.com/abc.gif'


def test_guess_ext():
    from mediafetch.media import guess_ext
    assert guess_ext('https://x/o1/v/t16/a.mp4') == 'mp4'
    assert guess_ext('https://media.giphy.com/media/x/source.gif') == 'gif'
    assert guess_ext('https://cdn/a.webp') == 'webp'
    assert guess_ext('https://cdn/a.jpg') == 'jpg'


def test_dash_tracks_picks_best_video_and_audio():
    manifest = '''<MPD><Period><AdaptationSet id="0" contentType="video">
      <Representation id="a" bandwidth="128176" width="640" height="1136">
        <BaseURL>https://cdn/low.mp4?a=1&amp;b=2</BaseURL></Representation>
      <Representation id="b" bandwidth="490468" width="720" height="1280">
        <BaseURL>https://cdn/high.mp4?a=1&amp;b=2</BaseURL></Representation>
      </AdaptationSet><AdaptationSet id="1" contentType="audio">
      <Representation id="c" bandwidth="75783">
        <BaseURL>https://cdn/aud.m4a?a=1&amp;b=2</BaseURL></Representation>
    </AdaptationSet></Period></MPD>'''
    video, audio = threads.dash_tracks(manifest)
    assert video == 'https://cdn/high.mp4?a=1&b=2'
    assert audio == 'https://cdn/aud.m4a?a=1&b=2'


def test_dash_tracks_empty():
    assert threads.dash_tracks(None) == (None, None)
    assert threads.dash_tracks('') == (None, None)


def test_video_media_carries_dash_urls():
    post = {'code': 'V1', 'media_type': 2,
            'video_versions': [{'url': 'https://cdn/prog.mp4'}],
            'video_dash_manifest': (
                '<AdaptationSet contentType="video"><Representation bandwidth="1">'
                '<BaseURL>https://cdn/v.mp4</BaseURL></Representation></AdaptationSet>'
                '<AdaptationSet contentType="audio"><Representation bandwidth="1">'
                '<BaseURL>https://cdn/a.m4a</BaseURL></Representation></AdaptationSet>')}
    item = threads.media_of(post)[0]
    assert item['url'] == 'https://cdn/prog.mp4'
    assert item['dash_video'] == 'https://cdn/v.mp4'
    assert item['dash_audio'] == 'https://cdn/a.m4a'


def test_author_of():
    assert threads.author_of({'user': {'username': 'a_b'}}) == 'a_b'
    assert threads.author_of({}) == ''
    rec = threads._record({'code': 'C', 'user': {'username': 'u1'},
                           'image_versions2': {'candidates': []}}, 'url')
    assert rec['author'] == 'u1'
