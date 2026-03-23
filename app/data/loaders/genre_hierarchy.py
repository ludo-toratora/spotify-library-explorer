"""Genre hierarchy loader and mapper."""

import json
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class GenreMapping:
    """Result of mapping a genre to parent categories."""

    genre: str
    parents: list[str]
    method: str  # "explicit", "keyword", "fuzzy", "none"
    confidence: float = 1.0


@dataclass
class GenreHierarchy:
    """Genre hierarchy with parent categories and mappings."""

    parent_genres: list[str]
    keyword_patterns: dict[str, list[str]]
    explicit_mappings: dict[str, list[str]]
    _compiled_patterns: dict[str, list[re.Pattern]] = field(
        default_factory=dict, repr=False
    )

    def __post_init__(self):
        """Compile regex patterns for keyword matching."""
        for parent, keywords in self.keyword_patterns.items():
            self._compiled_patterns[parent] = [
                re.compile(rf"\b{k.replace('-?', '-?')}\b", re.IGNORECASE)
                for k in keywords
            ]

    def map_genre(self, genre: str) -> GenreMapping:
        """
        Map a Spotify genre to parent category(ies).

        Priority:
        1. Explicit mapping (exact match)
        2. Keyword pattern matching
        3. Return empty list if no match

        Args:
            genre: The Spotify genre string

        Returns:
            GenreMapping with parents and method used
        """
        normalized = genre.lower().strip()

        # 1. Check explicit mappings first
        if normalized in self.explicit_mappings:
            return GenreMapping(
                genre=genre,
                parents=self.explicit_mappings[normalized],
                method="explicit",
                confidence=1.0
            )

        # 2. Try keyword pattern matching
        matches = []
        for parent, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(normalized):
                    if parent not in matches:
                        matches.append(parent)
                    break

        if matches:
            return GenreMapping(
                genre=genre,
                parents=matches,
                method="keyword",
                confidence=0.8
            )

        # 3. No match found
        return GenreMapping(
            genre=genre,
            parents=[],
            method="none",
            confidence=0.0
        )

    def map_genres(self, genres: list[str]) -> list[str]:
        """
        Map a list of genres to unique parent categories.

        Args:
            genres: List of Spotify genre strings

        Returns:
            Deduplicated list of parent genres
        """
        parents = []
        for genre in genres:
            mapping = self.map_genre(genre)
            for parent in mapping.parents:
                if parent not in parents:
                    parents.append(parent)
        return parents

    def get_primary_parent(self, genres: list[str]) -> Optional[str]:
        """
        Get the primary (most common) parent genre for a list of genres.

        Args:
            genres: List of Spotify genre strings

        Returns:
            The most frequently mapped parent, or None
        """
        if not genres:
            return None

        parent_counts: dict[str, int] = {}
        for genre in genres:
            mapping = self.map_genre(genre)
            for parent in mapping.parents:
                parent_counts[parent] = parent_counts.get(parent, 0) + 1

        if not parent_counts:
            return None

        return max(parent_counts.keys(), key=lambda p: parent_counts[p])


def load_genre_hierarchy(file_path: Optional[Path | str] = None) -> GenreHierarchy:
    """
    Load genre hierarchy from JSON file.

    Args:
        file_path: Path to hierarchy JSON file.
                   Defaults to app/data/genre_hierarchy.json

    Returns:
        GenreHierarchy instance
    """
    if file_path is None:
        # Default to bundled hierarchy
        file_path = Path(__file__).parent.parent / "genre_hierarchy.json"

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Genre hierarchy file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return GenreHierarchy(
        parent_genres=data.get("parent_genres", []),
        keyword_patterns=data.get("keyword_patterns", {}),
        explicit_mappings=data.get("explicit_mappings", {})
    )


# Module-level singleton for convenience
_default_hierarchy: Optional[GenreHierarchy] = None


def get_hierarchy() -> GenreHierarchy:
    """Get the default genre hierarchy (lazy loaded singleton)."""
    global _default_hierarchy
    if _default_hierarchy is None:
        _default_hierarchy = load_genre_hierarchy()
    return _default_hierarchy
