"""页面解析工具：从 HTML 里挖服务端渲染的 JSON。平台无关。

Meta 系站点把整篇内容塞进 <script type="application/json" data-sjs>，
这里只负责把那些 blob 找出来、递归走一遍、收集成节点列表。
"""
import json
import re

SJS = re.compile(
    r'<script[^>]*type="application/json"[^>]*data-sjs>(.*?)</script>', re.S)


def sjs_objects(html):
    """逐个产出页面内嵌的 JSON 对象，坏掉的跳过。"""
    for blob in SJS.findall(html):
        try:
            yield json.loads(blob)
        except ValueError:
            continue


def walk(obj, want, out):
    """递归收集满足 want(dict) 的节点，保持出现顺序。"""
    if isinstance(obj, dict):
        if want(obj):
            out.append(obj)
        for v in obj.values():
            walk(v, want, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, want, out)


def unique_nodes(html, want, key='code'):
    """页面里所有满足条件的节点，按 key 去重保序。"""
    raw = []
    for blob in sjs_objects(html):
        walk(blob, want, raw)
    seen, out = set(), []
    for node in raw:
        k = node.get(key)
        if k and k not in seen:
            seen.add(k)
            out.append(node)
    return out
