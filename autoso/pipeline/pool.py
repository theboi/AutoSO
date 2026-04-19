"""Cross-source flattened comment pool with global citation numbers."""

from __future__ import annotations

from dataclasses import dataclass, field

from autoso.pipeline.flatten import FlatComment
from autoso.scraping.models import Post


@dataclass
class PoolItem:
    citation_number: int
    flat: FlatComment


@dataclass
class Pool:
    items: list[PoolItem] = field(default_factory=list)
    posts: list[Post] = field(default_factory=list)

    def lookup(self, citation_number: int) -> PoolItem | None:
        for item in self.items:
            if item.citation_number == citation_number:
                return item
        return None


def build_pool(posts: list[Post], flattened: list[list[FlatComment]]) -> Pool:
    items: list[PoolItem] = []
    citation_number = 1

    for flat_list in flattened:
        for flat in flat_list:
            items.append(PoolItem(citation_number=citation_number, flat=flat))
            citation_number += 1

    return Pool(items=items, posts=list(posts))
