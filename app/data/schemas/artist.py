"""Artist schema - aggregated artist data from tracks."""

from typing import Optional
from pydantic import BaseModel, Field


class SampleTrack(BaseModel):
    """Minimal track info for display purposes."""

    name: str
    album: str


class AudioProfile(BaseModel):
    """Aggregated audio features for an artist (all 0-1 normalized)."""

    energy: float = Field(..., ge=0, le=1)
    danceability: float = Field(..., ge=0, le=1)
    valence: float = Field(..., ge=0, le=1)
    acousticness: float = Field(..., ge=0, le=1)
    instrumentalness: float = Field(..., ge=0, le=1)
    speechiness: float = Field(0.0, ge=0, le=1)
    liveness: float = Field(0.0, ge=0, le=1)
    tempo: float = Field(..., ge=0, le=1, description="Normalized tempo")


class Artist(BaseModel):
    """An artist with aggregated features from their tracks."""

    id: str = Field(..., description="Artist name (used as ID)")
    label: Optional[str] = Field(None, description="Display label (usually same as id)")
    track_count: int = Field(..., ge=1, description="Number of tracks in library")

    # Genre information
    genres: list[str] = Field(default_factory=list, description="All genres from tracks")
    parent_genres: list[str] = Field(default_factory=list, description="Parent genre categories")

    # Temporal
    primary_decade: Optional[str] = Field(None, description="Decade with most tracks")
    mean_year: Optional[int] = Field(None, description="Average release year")

    # Aggregated audio profile
    audio_profile: AudioProfile = Field(..., description="Mean audio features")

    # Sample tracks for display
    sample_tracks: list[SampleTrack] = Field(
        default_factory=list,
        description="Representative tracks"
    )

    # Track IDs for lookups
    track_ids: list[str] = Field(default_factory=list, description="All track IDs")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "Gabriels",
                "track_count": 2,
                "genres": ["retro soul"],
                "parent_genres": ["R&B"],
                "primary_decade": "2020s",
                "mean_year": 2023,
                "audio_profile": {
                    "energy": 0.57,
                    "danceability": 0.505,
                    "valence": 0.64,
                    "acousticness": 0.545,
                    "instrumentalness": 0.1,
                    "speechiness": 0.0,
                    "liveness": 0.4,
                    "tempo": 0.775
                }
            }
        }
