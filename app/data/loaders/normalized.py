"""Loader for normalized_tracks.json files."""

import json
from pathlib import Path
from typing import Optional

from ..schemas import Track


def load_normalized_tracks(file_path: Path | str) -> list[Track]:
    """
    Load tracks from a normalized_tracks.json file.

    Args:
        file_path: Path to the JSON file

    Returns:
        List of validated Track objects

    Raises:
        FileNotFoundError: If file doesn't exist
        ValidationError: If data doesn't match schema
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if not isinstance(raw_data, list):
        raise ValueError("Expected a JSON array of tracks")

    tracks = [Track.model_validate(item) for item in raw_data]
    return tracks


def load_tracks_raw(file_path: Path | str) -> list[dict]:
    """
    Load tracks as raw dictionaries without validation.
    Useful for inspecting data before full validation.

    Args:
        file_path: Path to the JSON file

    Returns:
        List of raw track dictionaries
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_normalized_tracks(tracks: list[Track], file_path: Path | str) -> None:
    """
    Save tracks to a normalized_tracks.json file.

    Args:
        tracks: List of Track objects
        file_path: Output path
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = [track.model_dump() for track in tracks]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
