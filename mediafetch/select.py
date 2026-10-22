"""筛选：决定「这次任务要哪些东西」。和抓取、存档完全解耦。

一条记录里有 media（图片/视频）、stickers（inline 贴图）、quoted（引用块）。
不同场景要不同的子集，这里用纯函数表达，不联网、不落盘。

    Select.only('sticker')        只要表情，图片视频一律不要
    Select.only('media')          只要图片视频，不要贴图
    Select.all()                  全都要
"""
from dataclasses import dataclass, field

KINDS = ('sticker', 'image', 'video', 'json')


@dataclass
class Select:
    kinds: frozenset = field(default_factory=lambda: frozenset(KINDS))
    follow_quoted: bool = True    # 引用块里的内容算不算
    follow_replies: bool = True   # 回复里的内容算不算
    follow_profiles: bool = True  # 作者/评论者主页算不算

    # ---------- 预设 ----------

    @classmethod
    def all(cls):
        return cls()

    @classmethod
    def only(cls, *kinds, **kw):
        bad = set(kinds) - set(KINDS)
        if bad:
            raise ValueError(f'未知类型 {bad}，可选 {KINDS}')
        return cls(kinds=frozenset(kinds), **kw)

    @classmethod
    def stickers_only(cls, **kw):
        """只要表情：帖子正文 + 回复 + 主页，全部只留 gif 贴图。"""
        return cls(kinds=frozenset({'sticker'}), **kw)

    @classmethod
    def media_only(cls, **kw):
        """只要图片和视频。"""
        return cls(kinds=frozenset({'image', 'video'}), **kw)

    # ---------- 判定 ----------

    def wants(self, kind):
        return kind in self.kinds

    def pick_media(self, rec):
        """从记录的 media 列表里挑出这次要的。"""
        return [m for m in rec.get('media') or [] if self.wants(m['type'])]

    def pick_stickers(self, rec):
        return list(rec.get('stickers') or []) if self.wants('sticker') else []

    def pick_quoted(self, rec):
        return list(rec.get('quoted') or []) if self.follow_quoted else []

    def useful(self, rec):
        """这条记录有没有值得落盘的东西。"""
        return bool(self.pick_media(rec) or self.pick_stickers(rec)
                    or (self.follow_quoted and self.pick_quoted(rec)))

    def __repr__(self):
        return (f"Select({sorted(self.kinds)}, quoted={self.follow_quoted}, "
                f"replies={self.follow_replies}, profiles={self.follow_profiles})")
