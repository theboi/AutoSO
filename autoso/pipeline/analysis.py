"""Shared analysis result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CitationRecord:
    citation_number: int
    text: str
    comment_id: str
    position: int
    source_index: int


@dataclass
class AnalysisResult:
    output_cited: str
    output_clean: str
    citations: list[CitationRecord] = field(default_factory=list)
