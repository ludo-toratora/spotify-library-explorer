"""Data validation and quality checks."""

from dataclasses import dataclass, field
from typing import Optional

from .schemas import Track


@dataclass
class ValidationFlag:
    """A single validation issue."""

    code: str           # e.g., "missing_genres", "invalid_tempo"
    severity: str       # "error", "warning", "info"
    message: str        # Human-readable description
    track_ids: list[str] = field(default_factory=list)  # Affected tracks
    count: int = 0      # Number of affected items


@dataclass
class ValidationReport:
    """Complete validation report for a dataset."""

    total_tracks: int
    valid_tracks: int
    flags: list[ValidationFlag] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.flags)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == "warning" for f in self.flags)

    @property
    def is_valid(self) -> bool:
        """Dataset is valid if no errors (warnings are OK)."""
        return not self.has_errors

    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            f"Validation Report",
            f"  Total tracks: {self.total_tracks}",
            f"  Valid tracks: {self.valid_tracks}",
            f"  Status: {'VALID' if self.is_valid else 'INVALID'}",
        ]

        if self.flags:
            lines.append("  Issues:")
            for flag in self.flags:
                icon = {"error": "X", "warning": "!", "info": "i"}[flag.severity]
                lines.append(f"    [{icon}] {flag.code}: {flag.message} ({flag.count} tracks)")

        return "\n".join(lines)


def validate_tracks(tracks: list[Track]) -> ValidationReport:
    """
    Validate a list of tracks and return a quality report.

    Checks performed:
    - Missing genres
    - Invalid audio feature ranges
    - Missing required fields
    - Duplicate track IDs
    - Temporal consistency

    Args:
        tracks: List of Track objects to validate

    Returns:
        ValidationReport with all findings
    """
    flags: list[ValidationFlag] = []

    # Check for missing genres
    missing_genres = [t for t in tracks if not t.genres]
    if missing_genres:
        ratio = len(missing_genres) / len(tracks)
        severity = "error" if ratio > 0.5 else "warning" if ratio > 0.2 else "info"
        flags.append(ValidationFlag(
            code="missing_genres",
            severity=severity,
            message=f"{len(missing_genres)} tracks have no genre information ({ratio:.1%})",
            track_ids=[t.track_id for t in missing_genres[:100]],  # Limit stored IDs
            count=len(missing_genres)
        ))

    # Check for missing parent genres
    missing_parents = [t for t in tracks if t.genres and not t.parent_genres]
    if missing_parents:
        flags.append(ValidationFlag(
            code="missing_parent_genres",
            severity="warning",
            message=f"{len(missing_parents)} tracks have genres but no parent genres",
            track_ids=[t.track_id for t in missing_parents[:100]],
            count=len(missing_parents)
        ))

    # Check audio feature ranges (0-1 features)
    audio_errors = []
    for t in tracks:
        issues = []
        if not (0 <= t.energy <= 1):
            issues.append(f"energy={t.energy}")
        if not (0 <= t.danceability <= 1):
            issues.append(f"danceability={t.danceability}")
        if not (0 <= t.valence <= 1):
            issues.append(f"valence={t.valence}")
        if not (0 <= t.acousticness <= 1):
            issues.append(f"acousticness={t.acousticness}")
        if not (0 <= t.instrumentalness <= 1):
            issues.append(f"instrumentalness={t.instrumentalness}")
        if issues:
            audio_errors.append(t)

    if audio_errors:
        flags.append(ValidationFlag(
            code="invalid_audio_range",
            severity="error",
            message=f"{len(audio_errors)} tracks have audio features outside valid range",
            track_ids=[t.track_id for t in audio_errors[:100]],
            count=len(audio_errors)
        ))

    # Check unusual tempo (warning, not error - tempo=0 means Spotify couldn't detect)
    unusual_tempo = [t for t in tracks if t.tempo == 0 or t.tempo < 40 or t.tempo > 220]
    if unusual_tempo:
        flags.append(ValidationFlag(
            code="unusual_tempo",
            severity="info",
            message=f"{len(unusual_tempo)} tracks have unusual tempo (0 or outside 40-220 BPM)",
            track_ids=[t.track_id for t in unusual_tempo[:100]],
            count=len(unusual_tempo)
        ))

    # Check for duplicate track IDs
    seen_ids = set()
    duplicates = []
    for t in tracks:
        if t.track_id in seen_ids:
            duplicates.append(t)
        seen_ids.add(t.track_id)

    if duplicates:
        flags.append(ValidationFlag(
            code="duplicate_track_ids",
            severity="error",
            message=f"{len(duplicates)} duplicate track IDs found",
            track_ids=[t.track_id for t in duplicates[:100]],
            count=len(duplicates)
        ))

    # Check for missing artist names
    missing_artist = [t for t in tracks if not t.artist_name or t.artist_name.strip() == ""]
    if missing_artist:
        flags.append(ValidationFlag(
            code="missing_artist",
            severity="error",
            message=f"{len(missing_artist)} tracks have no artist name",
            track_ids=[t.track_id for t in missing_artist[:100]],
            count=len(missing_artist)
        ))

    # Check for very old or future dates
    import re
    date_issues = []
    for t in tracks:
        if t.album_date:
            match = re.match(r"(\d{4})", t.album_date)
            if match:
                year = int(match.group(1))
                if year < 1900 or year > 2030:
                    date_issues.append(t)

    if date_issues:
        flags.append(ValidationFlag(
            code="suspicious_dates",
            severity="warning",
            message=f"{len(date_issues)} tracks have unusual release dates",
            track_ids=[t.track_id for t in date_issues[:100]],
            count=len(date_issues)
        ))

    # Calculate valid track count (tracks without errors)
    error_track_ids = set()
    for flag in flags:
        if flag.severity == "error":
            error_track_ids.update(flag.track_ids)

    valid_count = len(tracks) - len(error_track_ids)

    return ValidationReport(
        total_tracks=len(tracks),
        valid_tracks=valid_count,
        flags=flags
    )


def get_artist_summary(tracks: list[Track]) -> dict:
    """
    Generate artist summary statistics from tracks.

    Returns:
        Dict with artist count, tracks per artist stats, etc.
    """
    artist_tracks: dict[str, list[Track]] = {}
    for t in tracks:
        if t.artist_name not in artist_tracks:
            artist_tracks[t.artist_name] = []
        artist_tracks[t.artist_name].append(t)

    track_counts = [len(tracks) for tracks in artist_tracks.values()]

    return {
        "total_artists": len(artist_tracks),
        "tracks_per_artist": {
            "min": min(track_counts) if track_counts else 0,
            "max": max(track_counts) if track_counts else 0,
            "mean": sum(track_counts) / len(track_counts) if track_counts else 0,
        },
        "single_track_artists": sum(1 for c in track_counts if c == 1),
    }


def get_genre_summary(tracks: list[Track]) -> dict:
    """
    Generate genre summary statistics from tracks.

    Returns:
        Dict with genre count, distribution, etc.
    """
    all_genres: set[str] = set()
    all_parents: set[str] = set()

    for t in tracks:
        all_genres.update(t.genres)
        all_parents.update(t.parent_genres)

    return {
        "total_genres": len(all_genres),
        "total_parent_genres": len(all_parents),
        "tracks_with_genres": sum(1 for t in tracks if t.genres),
        "tracks_without_genres": sum(1 for t in tracks if not t.genres),
    }
