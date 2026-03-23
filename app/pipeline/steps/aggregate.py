"""Aggregate tracks into artist profiles.

Input: List of track dictionaries (from normalized_tracks.json)
Output: List of artist dictionaries with aggregated features

This step computes:
- Mean audio profile across all tracks
- Union of all genres and parent_genres
- Primary decade (most common)
- Mean year
- Track count and track IDs
"""

from collections import defaultdict
from dataclasses import dataclass, field
import numpy as np
from typing import Any


# Default audio features for aggregation
DEFAULT_AUDIO_FEATURES = [
    'energy', 'danceability', 'valence', 'acousticness',
    'instrumentalness', 'speechiness', 'liveness', 'tempo'
]


@dataclass
class AggregationConfig:
    """Configuration for artist aggregation."""
    audio_features: list[str] = field(default_factory=lambda: DEFAULT_AUDIO_FEATURES.copy())
    tempo_max: float = 200.0  # For normalizing tempo to 0-1
    min_tracks: int = 1  # Minimum tracks per artist


@dataclass
class AggregationResult:
    """Result of artist aggregation."""
    artists: list[dict]
    artist_count: int
    track_count: int
    skipped_artists: int  # Artists with fewer than min_tracks


def aggregate_tracks_to_artists(
    tracks: list[dict],
    config: AggregationConfig | None = None
) -> AggregationResult:
    """Aggregate tracks into artist profiles.

    Each artist gets:
    - name: Artist name
    - track_count: Number of tracks
    - track_ids: List of track IDs
    - audio_profile: Mean of audio features (tempo normalized to 0-1)
    - genres: Union of all track genres
    - parent_genres: Union of all track parent genres
    - primary_decade: Most common decade
    - mean_year: Mean release year

    Args:
        tracks: List of track dictionaries
        config: Aggregation configuration

    Returns:
        AggregationResult with artist list and stats
    """
    if config is None:
        config = AggregationConfig()

    # Group tracks by artist
    artist_tracks: dict[str, list[dict]] = defaultdict(list)
    for track in tracks:
        artist_name = track.get('artist_name', 'Unknown')
        artist_tracks[artist_name].append(track)

    artists = []
    skipped = 0

    for artist_name, track_list in artist_tracks.items():
        if len(track_list) < config.min_tracks:
            skipped += 1
            continue

        # Compute mean audio profile
        audio_profile = _compute_audio_profile(
            track_list, config.audio_features, config.tempo_max
        )

        # Collect genres
        all_genres = set()
        parent_genres = set()
        for t in track_list:
            all_genres.update(t.get('genres', []))
            parent_genres.update(t.get('parent_genres', []))

        # Compute temporal info
        years, decade_counts = _extract_temporal_info(track_list)
        primary_decade = (
            max(decade_counts.items(), key=lambda x: x[1])[0]
            if decade_counts else 'Unknown'
        )
        mean_year = int(np.mean(years)) if years else 1990

        # Collect track IDs
        track_ids = [t.get('id') or t.get('track_id') for t in track_list]
        track_ids = [tid for tid in track_ids if tid]

        artists.append({
            'name': artist_name,
            'track_count': len(track_list),
            'track_ids': track_ids,
            'audio_profile': audio_profile,
            'genres': sorted(all_genres),
            'parent_genres': sorted(parent_genres),
            'primary_decade': primary_decade,
            'mean_year': mean_year,
        })

    return AggregationResult(
        artists=artists,
        artist_count=len(artists),
        track_count=len(tracks),
        skipped_artists=skipped,
    )


def _compute_audio_profile(
    tracks: list[dict],
    features: list[str],
    tempo_max: float
) -> dict[str, float]:
    """Compute mean audio profile from tracks.

    Args:
        tracks: List of track dictionaries
        features: Audio feature names to include
        tempo_max: Maximum tempo for normalization

    Returns:
        Dictionary of feature name to mean value
    """
    profile = {}

    for feature in features:
        values = []
        for t in tracks:
            val = t.get(feature)
            if val is not None:
                # Normalize tempo to 0-1
                if feature == 'tempo':
                    val = min(val / tempo_max, 1.0)
                values.append(val)

        if values:
            profile[feature] = float(np.mean(values))
        else:
            profile[feature] = 0.0

    return profile


def _extract_temporal_info(tracks: list[dict]) -> tuple[list[int], dict[str, int]]:
    """Extract years and decade counts from tracks.

    Args:
        tracks: List of track dictionaries

    Returns:
        Tuple of (list of years, decade counts dict)
    """
    years = []
    decade_counts: dict[str, int] = defaultdict(int)

    for t in tracks:
        album_date = t.get('album_date', '')
        if album_date and len(str(album_date)) >= 4:
            try:
                year = int(str(album_date)[:4])
                years.append(year)
                decade = f"{(year // 10) * 10}s"
                decade_counts[decade] += 1
            except ValueError:
                pass

    return years, dict(decade_counts)


def artists_to_feature_matrix(
    artists: list[dict],
    features: list[str] | None = None
) -> tuple[np.ndarray, list[str]]:
    """Convert artists to feature matrix for embedding.

    Args:
        artists: List of artist dictionaries
        features: Feature names to extract (defaults to primary audio features)

    Returns:
        Tuple of (feature matrix, artist IDs)
    """
    if features is None:
        features = ['energy', 'danceability', 'valence',
                    'acousticness', 'instrumentalness', 'tempo']

    matrix = []
    ids = []

    for artist in artists:
        profile = artist.get('audio_profile', {})
        vec = [profile.get(f, 0.0) for f in features]
        matrix.append(vec)
        ids.append(artist['name'])

    return np.array(matrix, dtype=float), ids
