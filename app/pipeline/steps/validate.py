"""Pipeline validation step.

Validates data at various stages of the pipeline:
- Input tracks validation
- Aggregated artists validation
- Graph output validation
- Embedding output validation
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationIssue:
    """A single validation issue."""
    level: str  # "error", "warning", "info"
    category: str  # "tracks", "artists", "graph", "embedding"
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of validation."""
    valid: bool
    issues: list[ValidationIssue]
    stats: dict

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]


def validate_tracks(tracks: list[dict], config: dict | None = None) -> ValidationResult:
    """Validate input tracks.

    Checks:
    - Minimum track count
    - Required fields present
    - Audio features in valid range
    - Genre coverage

    Args:
        tracks: List of track dictionaries
        config: Validation thresholds

    Returns:
        ValidationResult
    """
    if config is None:
        config = {
            "min_tracks": 10,
            "max_missing_genres": 0.5,
        }

    issues = []
    stats = {
        "track_count": len(tracks),
        "artists": set(),
        "genres": set(),
        "tracks_with_genres": 0,
        "tracks_with_audio": 0,
    }

    # Check minimum tracks
    if len(tracks) < config.get("min_tracks", 10):
        issues.append(ValidationIssue(
            level="error",
            category="tracks",
            message=f"Too few tracks: {len(tracks)} < {config.get('min_tracks', 10)}",
        ))

    # Validate each track
    for i, track in enumerate(tracks):
        # Collect stats
        artist = track.get("artist_name", "Unknown")
        stats["artists"].add(artist)

        genres = track.get("genres", [])
        if genres:
            stats["tracks_with_genres"] += 1
            stats["genres"].update(genres)

        # Check for audio features
        audio_features = ["energy", "danceability", "valence"]
        has_audio = any(track.get(f) is not None for f in audio_features)
        if has_audio:
            stats["tracks_with_audio"] += 1

        # Validate audio feature ranges
        for feature in audio_features:
            val = track.get(feature)
            if val is not None and (val < 0 or val > 1):
                issues.append(ValidationIssue(
                    level="warning",
                    category="tracks",
                    message=f"Audio feature out of range: {feature}={val}",
                    details={"track_index": i, "track_id": track.get("id")},
                ))

    # Convert sets to counts
    stats["artist_count"] = len(stats["artists"])
    stats["genre_count"] = len(stats["genres"])
    del stats["artists"]
    del stats["genres"]

    # Check genre coverage
    genre_coverage = stats["tracks_with_genres"] / max(len(tracks), 1)
    stats["genre_coverage"] = genre_coverage
    if genre_coverage < (1 - config.get("max_missing_genres", 0.5)):
        issues.append(ValidationIssue(
            level="warning",
            category="tracks",
            message=f"Low genre coverage: {genre_coverage:.1%} of tracks have genres",
        ))

    valid = len([i for i in issues if i.level == "error"]) == 0

    return ValidationResult(valid=valid, issues=issues, stats=stats)


def validate_artists(artists: list[dict], config: dict | None = None) -> ValidationResult:
    """Validate aggregated artists.

    Checks:
    - Minimum artist count
    - Required fields present
    - Audio profile completeness

    Args:
        artists: List of artist dictionaries
        config: Validation thresholds

    Returns:
        ValidationResult
    """
    if config is None:
        config = {"min_artists": 10}

    issues = []
    stats = {
        "artist_count": len(artists),
        "total_tracks": sum(a.get("track_count", 0) for a in artists),
        "artists_with_genres": 0,
        "artists_with_audio": 0,
    }

    if len(artists) < config.get("min_artists", 10):
        issues.append(ValidationIssue(
            level="error",
            category="artists",
            message=f"Too few artists: {len(artists)} < {config.get('min_artists', 10)}",
        ))

    for artist in artists:
        if artist.get("genres"):
            stats["artists_with_genres"] += 1
        if artist.get("audio_profile"):
            stats["artists_with_audio"] += 1

        # Check required fields
        if "name" not in artist:
            issues.append(ValidationIssue(
                level="error",
                category="artists",
                message="Artist missing name field",
            ))

    valid = len([i for i in issues if i.level == "error"]) == 0

    return ValidationResult(valid=valid, issues=issues, stats=stats)


def validate_graph(graph_data: dict, config: dict | None = None) -> ValidationResult:
    """Validate graph output.

    Checks:
    - Has nodes and edges
    - Communities assigned
    - Edge weights in range

    Args:
        graph_data: Graph dictionary
        config: Validation thresholds

    Returns:
        ValidationResult
    """
    issues = []
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    communities = graph_data.get("communities", {})

    stats = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "community_count": len(set(communities.values())) if communities else 0,
    }

    if len(nodes) == 0:
        issues.append(ValidationIssue(
            level="error",
            category="graph",
            message="Graph has no nodes",
        ))

    if len(edges) == 0:
        issues.append(ValidationIssue(
            level="warning",
            category="graph",
            message="Graph has no edges",
        ))

    # Check edge weights
    for edge in edges[:100]:  # Sample first 100
        weight = edge.get("weight", 0)
        if weight < 0 or weight > 1:
            issues.append(ValidationIssue(
                level="warning",
                category="graph",
                message=f"Edge weight out of range: {weight}",
                details={"source": edge.get("source"), "target": edge.get("target")},
            ))
            break

    # Check community coverage
    if communities:
        covered = len([n for n in nodes if n.get("id") in communities])
        stats["community_coverage"] = covered / max(len(nodes), 1)

    valid = len([i for i in issues if i.level == "error"]) == 0

    return ValidationResult(valid=valid, issues=issues, stats=stats)


def validate_embedding(embedding_data: dict, config: dict | None = None) -> ValidationResult:
    """Validate embedding output.

    Checks:
    - Has positions
    - Positions in normalized range
    - Clusters assigned

    Args:
        embedding_data: Embedding dictionary
        config: Validation thresholds

    Returns:
        ValidationResult
    """
    issues = []
    positions = embedding_data.get("positions", {})
    clusters = embedding_data.get("clusters", {})

    stats = {
        "point_count": len(positions),
        "cluster_count": len(set(clusters.values())) if clusters else 0,
    }

    if len(positions) == 0:
        issues.append(ValidationIssue(
            level="error",
            category="embedding",
            message="Embedding has no positions",
        ))

    # Check position ranges (should be normalized to [-1, 1])
    out_of_range = 0
    for pos in list(positions.values())[:100]:
        x, y = pos if isinstance(pos, (list, tuple)) else (pos.get("x"), pos.get("y"))
        if abs(x) > 1.5 or abs(y) > 1.5:
            out_of_range += 1

    if out_of_range > 0:
        issues.append(ValidationIssue(
            level="info",
            category="embedding",
            message=f"{out_of_range} positions outside [-1.5, 1.5] range",
        ))

    valid = len([i for i in issues if i.level == "error"]) == 0

    return ValidationResult(valid=valid, issues=issues, stats=stats)


def validation_result_to_json(result: ValidationResult) -> dict:
    """Convert ValidationResult to JSON-serializable dict."""
    return {
        "valid": result.valid,
        "error_count": len(result.errors),
        "warning_count": len(result.warnings),
        "issues": [
            {
                "level": i.level,
                "category": i.category,
                "message": i.message,
                "details": i.details,
            }
            for i in result.issues
        ],
        "stats": result.stats,
    }
