"""Upload endpoint.

POST /api/upload - Upload tracks JSON file or Chosic CSV
"""

import csv
import io
import json
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from typing import Literal, Optional

from app.api.dependencies import get_uploads_dir, clear_all_caches
from app.api.models import UploadResponse, ValidationResponse, ValidationIssue

router = APIRouter()


# === Chosic CSV conversion ===

# Actual Chosic export column names
REQUIRED_CHOIC_COLS = ["Song", "Artist", "BPM", "Energy", "Dance", "Spotify Track Id"]


def _parse_list_field(value: str) -> list[str]:
    """Parse a comma or semicolon-delimited genre string into a list."""
    if not value or not value.strip():
        return []
    # Try semicolon first, then comma
    sep = ";" if ";" in value else ","
    return [v.strip() for v in value.split(sep) if v.strip()]


def _safe_float(value: str) -> float | None:
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _safe_int(value: str) -> int | None:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _duration_to_ms(value: str) -> int | None:
    """Convert mm:ss or hh:mm:ss string to milliseconds."""
    value = str(value).strip()
    try:
        parts = value.split(":")
        if len(parts) == 2:
            return (int(parts[0]) * 60 + int(parts[1])) * 1000
        elif len(parts) == 3:
            return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000
    except (ValueError, TypeError):
        pass
    return None


def _scale01(value: str) -> float | None:
    """Convert 0-100 int string to 0.0-1.0 float."""
    v = _safe_float(value)
    return round(v / 100.0, 4) if v is not None else None


def convert_choic_csv(content: bytes) -> list[dict]:
    """Convert a Chosic CSV export to normalized_tracks format.

    Chosic columns: #, Song, Artist, BPM, Camelot, Energy, Added At,
    Duration, Popularity, Genres, Parent Genres, Album, Album Date,
    Dance, Acoustic, Instrumental, Valence, Speech, Live, Loud (Db),
    Key, Time Signature, Spotify Track Id, Label, ISRC

    Raises:
        ValueError with structured info if required columns are missing.
    """
    # Try common encodings in order
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Could not decode CSV file (tried utf-8, latin-1, cp1252)")

    # Detect delimiter by checking which gives the most columns
    best_delim = ","
    best_count = 0
    for delim in (",", ";", "\t"):
        probe = csv.DictReader(io.StringIO(text), delimiter=delim)
        cols = probe.fieldnames or []
        if len(cols) > best_count:
            best_count = len(cols)
            best_delim = delim

    reader = csv.DictReader(io.StringIO(text), delimiter=best_delim)
    found_cols = list(reader.fieldnames or [])

    missing = [c for c in REQUIRED_CHOIC_COLS if c not in found_cols]
    if missing:
        raise ValueError(json.dumps({
            "error": "missing_columns",
            "missing": missing,
            "found": found_cols,
        }))

    tracks = []
    for row in reader:
        track_id = row.get("Spotify Track Id", "").strip()
        if not track_id:
            continue

        track = {
            "track_id":          track_id,
            "track_name":        row.get("Song", "").strip(),
            "artist_name":       row.get("Artist", "").strip(),
            # Audio features: Chosic uses 0-100 scale → normalize to 0-1
            "tempo":             _safe_float(row.get("BPM", "")),
            "energy":            _scale01(row.get("Energy", "")),
            "danceability":      _scale01(row.get("Dance", "")),
            "acousticness":      _scale01(row.get("Acoustic", "")),
            "instrumentalness":  _scale01(row.get("Instrumental", "")),
            "valence":           _scale01(row.get("Valence", "")),
            "speechiness":       _scale01(row.get("Speech", "")),
            "liveness":          _scale01(row.get("Live", "")),
            "loudness":          _safe_float(row.get("Loud (Db)", "")),
            # Metadata
            "camelot":           row.get("Camelot", "").strip() or None,
            "popularity":        _safe_int(row.get("Popularity", "")),
            "duration_ms":       _duration_to_ms(row.get("Duration", "")),
            "time_signature":    _safe_int(row.get("Time Signature", "")),
            "key":               row.get("Key", "").strip() or None,
            "album_name":        row.get("Album", "").strip() or None,
            "album_date":        row.get("Album Date", "").strip() or None,
            "isrc":              row.get("ISRC", "").strip() or None,
            "label":             row.get("Label", "").strip() or None,
            "added_at":          row.get("Added At", "").strip() or None,
            # Genres
            "genres":        _parse_list_field(row.get("Genres", "")),
            "parent_genres": _parse_list_field(row.get("Parent Genres", "")),
            "flags":         [],
        }
        tracks.append(track)

    return tracks


# Required fields for validation
REQUIRED_FIELDS = ["track_id", "track_name", "artist_name"]
AUDIO_FIELDS = ["tempo", "energy", "danceability", "valence", "acousticness", "instrumentalness"]


def validate_tracks_json(data: list[dict]) -> tuple[bool, list[dict], list[dict]]:
    """Quick validation of tracks data.

    Returns:
        Tuple of (is_valid, errors, warnings)
    """
    errors = []
    warnings = []

    if not isinstance(data, list):
        errors.append({"code": "NOT_LIST", "message": "Expected JSON array of tracks"})
        return False, errors, warnings

    if len(data) == 0:
        errors.append({"code": "EMPTY", "message": "No tracks in file"})
        return False, errors, warnings

    # Check required fields on first few tracks
    required_fields = ["track_id", "track_name", "artist_name"]
    audio_fields = ["tempo", "energy", "danceability", "valence", "acousticness", "instrumentalness"]

    sample = data[:10]
    missing_required = set()
    missing_audio = set()

    for track in sample:
        for field in required_fields:
            if field not in track:
                missing_required.add(field)
        for field in audio_fields:
            if field not in track:
                missing_audio.add(field)

    if missing_required:
        errors.append({
            "code": "MISSING_REQUIRED",
            "message": f"Missing required fields: {', '.join(missing_required)}"
        })

    if missing_audio:
        warnings.append({
            "code": "MISSING_AUDIO",
            "message": f"Missing audio features: {', '.join(missing_audio)}"
        })

    # Check for genres
    tracks_with_genres = sum(1 for t in data if t.get("genres"))
    if tracks_with_genres < len(data) * 0.5:
        warnings.append({
            "code": "LOW_GENRE_COVERAGE",
            "message": f"Only {tracks_with_genres}/{len(data)} tracks have genres"
        })

    return len(errors) == 0, errors, warnings


@router.post("/upload", response_model=UploadResponse)
async def upload_tracks(
    tracks_file: UploadFile = File(..., description="normalized_tracks.json or Chosic .csv"),
    genre_hierarchy_file: Optional[UploadFile] = File(None, description="Optional genre hierarchy JSON"),
    format: str = Form("json", description="'json' or 'choic_csv'"),
    fmt: str = Query("", description="Alternative to format form field"),
) -> UploadResponse:
    """Upload track data for processing.

    Accepts a normalized_tracks.json (format=json) or Chosic CSV export
    (format=choic_csv). Validates and saves to uploads directory.

    The uploaded file can then be processed via POST /api/recompute.
    """
    uploads_dir = get_uploads_dir()
    content = await tracks_file.read()

    # Auto-detect format: if file ends in .csv treat as Chosic regardless of form field
    filename = tracks_file.filename or ""
    if filename.endswith(".csv"):
        effective_format = "choic_csv"
    else:
        effective_format = fmt if fmt else format

    # === CSV path ===
    if effective_format == "choic_csv":
        try:
            data = convert_choic_csv(content)
        except ValueError as e:
            try:
                detail = json.loads(str(e))
            except Exception:
                detail = str(e)
            raise HTTPException(status_code=422, detail=detail)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")
    else:
        # === JSON path ===
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    # Validate structure
    is_valid, errors, warnings = validate_tracks_json(data)

    if not is_valid:
        validation = ValidationResponse(
            valid=False,
            track_count=len(data) if isinstance(data, list) else 0,
            errors=[ValidationIssue(level="error", **e) for e in errors],
            warnings=[ValidationIssue(level="warning", **w) for w in warnings],
        )
        return UploadResponse(
            status="error",
            message="Validation failed",
            validation=validation,
        )

    # Save file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tracks_{timestamp}.json"
    file_path = uploads_dir / filename

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    # Also overwrite canonical file
    canonical_path = uploads_dir / "normalized_tracks.json"
    with open(canonical_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    # Handle optional genre hierarchy
    if genre_hierarchy_file:
        try:
            hierarchy_content = await genre_hierarchy_file.read()
            hierarchy_data = json.loads(hierarchy_content)
            hierarchy_path = uploads_dir / f"genre_hierarchy_{timestamp}.json"
            with open(hierarchy_path, "w", encoding="utf-8") as f:
                json.dump(hierarchy_data, f)
        except json.JSONDecodeError:
            warnings.append({
                "code": "INVALID_HIERARCHY",
                "message": "Genre hierarchy file is invalid JSON, skipped"
            })

    # Count unique artists
    artist_count = len(set(t.get("artist_name", "") for t in data))

    validation = ValidationResponse(
        valid=True,
        track_count=len(data),
        artist_count=artist_count,
        errors=[],
        warnings=[ValidationIssue(level="warning", **w) for w in warnings],
    )

    return UploadResponse(
        status="success",
        message=f"Uploaded {len(data)} tracks from {artist_count} artists",
        track_count=len(data),
        artist_count=artist_count,
        file_path=str(file_path),
        validation=validation,
    )


class ValidateRequest(BaseModel):
    """Request body for validation endpoint."""
    content: str  # JSON string to validate


@router.post("/validate", response_model=ValidationResponse)
async def validate_tracks_content(body: ValidateRequest) -> ValidationResponse:
    """Validate tracks JSON content without uploading.

    Useful for client-side preview before committing to upload.
    """
    try:
        data = json.loads(body.content)
    except json.JSONDecodeError as e:
        return ValidationResponse(
            valid=False,
            track_count=0,
            errors=[ValidationIssue(level="error", code="INVALID_JSON", message=str(e))],
            warnings=[],
        )

    is_valid, errors, warnings = validate_tracks_json(data)
    artist_count = len(set(t.get("artist_name", "") for t in data)) if isinstance(data, list) else 0

    return ValidationResponse(
        valid=is_valid,
        track_count=len(data) if isinstance(data, list) else 0,
        artist_count=artist_count,
        errors=[ValidationIssue(level="error", **e) for e in errors],
        warnings=[ValidationIssue(level="warning", **w) for w in warnings],
    )
