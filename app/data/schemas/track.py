"""Track schema - canonical representation of a Spotify track."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Track(BaseModel):
    """A single track with all audio features and metadata."""

    # Identifiers
    track_id: str = Field(..., description="Spotify track ID")
    isrc: Optional[str] = Field(None, description="International Standard Recording Code")
    track_name: str = Field(..., description="Track title")
    artist_name: str = Field(..., description="Primary artist name")
    album_name: str = Field(..., description="Album title")

    # Dates
    album_date: Optional[str] = Field(None, description="Album release date (YYYY-MM-DD)")
    added_at: Optional[datetime] = Field(None, description="When track was added to library")

    # Label
    label: Optional[str] = Field(None, description="Record label")

    # Core audio features (0-1 normalized except tempo/loudness)
    tempo: float = Field(..., ge=0, le=250, description="BPM (beats per minute)")
    energy: float = Field(..., ge=0, le=1, description="Intensity and activity measure")
    danceability: float = Field(..., ge=0, le=1, description="How suitable for dancing")
    valence: float = Field(..., ge=0, le=1, description="Musical positiveness/happiness")
    acousticness: float = Field(..., ge=0, le=1, description="Acoustic vs electronic")
    instrumentalness: float = Field(..., ge=0, le=1, description="Instrumental vs vocal")

    # Secondary audio features
    speechiness: float = Field(0.0, ge=0, le=1, description="Presence of spoken words")
    liveness: float = Field(0.0, ge=0, le=1, description="Presence of live audience")
    loudness: float = Field(-60.0, ge=-60, le=0, description="Overall loudness in dB")

    # Musical attributes
    key: Optional[int] = Field(None, ge=0, le=11, description="Pitch class (0=C, 1=C#, ...)")
    mode: Optional[int] = Field(None, ge=0, le=1, description="0=minor, 1=major")
    time_signature: Optional[int] = Field(4, description="Beats per measure")
    camelot: Optional[str] = Field(None, description="Camelot wheel notation for mixing")

    # Additional metadata
    duration_ms: Optional[int] = Field(None, ge=0, description="Track duration in milliseconds")
    popularity: Optional[int] = Field(None, ge=0, le=100, description="Spotify popularity score")

    # Genre information
    genres: list[str] = Field(default_factory=list, description="Raw genres from Spotify")
    parent_genres: list[str] = Field(
        default_factory=list,
        description="Parent categories (computed from genre hierarchy mapping)"
    )
    primary_parent_genre: Optional[str] = Field(
        None,
        description="Primary parent genre (most common or first)"
    )

    # Validation flags
    flags: list[str] = Field(default_factory=list, description="Data quality flags")

    class Config:
        json_schema_extra = {
            "example": {
                "track_id": "2zfaXvRq0DtBzJjQ0YFUqq",
                "track_name": "One and Only",
                "artist_name": "Gabriels",
                "album_name": "Angels & Queens (Deluxe)",
                "tempo": 124.0,
                "energy": 0.74,
                "danceability": 0.68,
                "valence": 0.78,
                "acousticness": 0.3,
                "instrumentalness": 0.08,
                "genres": ["retro soul"],
                "parent_genres": ["R&B"]
            }
        }


class AudioFeatures(BaseModel):
    """Just the audio features, useful for similarity computation."""

    energy: float = Field(..., ge=0, le=1)
    danceability: float = Field(..., ge=0, le=1)
    valence: float = Field(..., ge=0, le=1)
    acousticness: float = Field(..., ge=0, le=1)
    instrumentalness: float = Field(..., ge=0, le=1)
    tempo: float = Field(..., ge=0, le=1, description="Normalized tempo (0-1)")
    speechiness: float = Field(0.0, ge=0, le=1)
    liveness: float = Field(0.0, ge=0, le=1)

    @classmethod
    def from_track(cls, track: Track, normalize_tempo: bool = True) -> "AudioFeatures":
        """Extract audio features from a track."""
        tempo = track.tempo / 200.0 if normalize_tempo else track.tempo
        return cls(
            energy=track.energy,
            danceability=track.danceability,
            valence=track.valence,
            acousticness=track.acousticness,
            instrumentalness=track.instrumentalness,
            tempo=min(tempo, 1.0),
            speechiness=track.speechiness,
            liveness=track.liveness
        )
