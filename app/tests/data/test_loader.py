"""Tests for data loading and validation."""

import sys
from pathlib import Path

# Add app to path for imports
APP_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(APP_DIR.parent))

import pytest
from app.data.loaders import load_normalized_tracks, load_tracks_raw
from app.data.validation import validate_tracks, get_artist_summary, get_genre_summary
from app.data.schemas import Track


# Path to bootstrap data for testing
BOOTSTRAP_DATA = Path(__file__).parent.parent.parent.parent / "runs/2026-02-15_212055/02_preprocessed"
NORMALIZED_TRACKS_PATH = BOOTSTRAP_DATA / "normalized_tracks.json"


class TestLoadNormalizedTracks:
    """Test loading normalized_tracks.json."""

    @pytest.fixture
    def bootstrap_tracks_path(self) -> Path:
        """Return path to bootstrap data if it exists."""
        if not NORMALIZED_TRACKS_PATH.exists():
            pytest.skip("Bootstrap data not available")
        return NORMALIZED_TRACKS_PATH

    def test_load_raw(self, bootstrap_tracks_path):
        """Test loading raw data without validation."""
        raw = load_tracks_raw(bootstrap_tracks_path)

        assert isinstance(raw, list)
        assert len(raw) > 0
        assert "track_id" in raw[0]
        print(f"Loaded {len(raw)} raw tracks")

    def test_load_validated(self, bootstrap_tracks_path):
        """Test loading with Pydantic validation."""
        tracks = load_normalized_tracks(bootstrap_tracks_path)

        assert isinstance(tracks, list)
        assert len(tracks) > 0
        assert all(isinstance(t, Track) for t in tracks)
        print(f"Loaded and validated {len(tracks)} tracks")

    def test_track_fields(self, bootstrap_tracks_path):
        """Test that track fields are populated correctly."""
        tracks = load_normalized_tracks(bootstrap_tracks_path)
        track = tracks[0]

        # Check required fields
        assert track.track_id
        assert track.track_name
        assert track.artist_name

        # Check audio features are in range
        assert 0 <= track.energy <= 1
        assert 0 <= track.danceability <= 1
        assert 0 <= track.valence <= 1
        assert 0 <= track.acousticness <= 1
        assert 0 <= track.instrumentalness <= 1
        assert 40 <= track.tempo <= 250

        print(f"First track: {track.track_name} by {track.artist_name}")


class TestValidation:
    """Test data validation."""

    @pytest.fixture
    def bootstrap_tracks(self) -> list[Track]:
        """Load bootstrap tracks for validation tests."""
        if not NORMALIZED_TRACKS_PATH.exists():
            pytest.skip("Bootstrap data not available")
        return load_normalized_tracks(NORMALIZED_TRACKS_PATH)

    def test_validate_tracks(self, bootstrap_tracks):
        """Test validation report generation."""
        report = validate_tracks(bootstrap_tracks)

        print(report.summary())

        assert report.total_tracks == len(bootstrap_tracks)
        assert report.valid_tracks > 0
        # Bootstrap data should be valid
        assert report.is_valid, f"Bootstrap data should be valid: {report.summary()}"

    def test_artist_summary(self, bootstrap_tracks):
        """Test artist statistics."""
        summary = get_artist_summary(bootstrap_tracks)

        print(f"Artist summary: {summary}")

        assert summary["total_artists"] > 0
        assert summary["tracks_per_artist"]["min"] >= 1
        assert summary["tracks_per_artist"]["max"] >= summary["tracks_per_artist"]["min"]

    def test_genre_summary(self, bootstrap_tracks):
        """Test genre statistics."""
        summary = get_genre_summary(bootstrap_tracks)

        print(f"Genre summary: {summary}")

        assert summary["total_genres"] > 0
        # Most tracks should have genres
        assert summary["tracks_with_genres"] > summary["tracks_without_genres"]


class TestFileNotFound:
    """Test error handling for missing files."""

    def test_load_missing_file(self):
        """Test that FileNotFoundError is raised for missing files."""
        with pytest.raises(FileNotFoundError):
            load_normalized_tracks(Path("/nonexistent/path/tracks.json"))


if __name__ == "__main__":
    # Quick manual test
    if NORMALIZED_TRACKS_PATH.exists():
        print(f"Loading from: {NORMALIZED_TRACKS_PATH}")

        tracks = load_normalized_tracks(NORMALIZED_TRACKS_PATH)
        print(f"Loaded {len(tracks)} tracks")

        report = validate_tracks(tracks)
        print(report.summary())

        artist_stats = get_artist_summary(tracks)
        print(f"\nArtist stats: {artist_stats}")

        genre_stats = get_genre_summary(tracks)
        print(f"Genre stats: {genre_stats}")
    else:
        print("Bootstrap data not found - run with pytest against your own data")
