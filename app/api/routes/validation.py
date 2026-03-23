"""Validation endpoint.

GET /api/validation - Get last pipeline validation report
"""

import json
from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_cache
from app.api.models import ValidationResponse, ValidationIssue

router = APIRouter()


@router.get("/validation", response_model=ValidationResponse)
async def get_validation() -> ValidationResponse:
    """Get the last pipeline validation report.

    Returns validation results from the most recent pipeline run,
    including track and artist counts, errors, and warnings.
    """
    cache = get_cache()

    # Check for validation report in cache
    validation_path = cache.validation_dir / "report.json"

    if validation_path.exists():
        with open(validation_path, encoding="utf-8") as f:
            report = json.load(f)

        errors = []
        warnings = []

        # Extract errors
        for err in report.get("errors", []):
            errors.append(ValidationIssue(
                level="error",
                code=err.get("code", "UNKNOWN"),
                message=err.get("message", ""),
                count=err.get("count", 1),
            ))

        # Extract warnings
        for warn in report.get("warnings", []):
            warnings.append(ValidationIssue(
                level="warning",
                code=warn.get("code", "UNKNOWN"),
                message=warn.get("message", ""),
                count=warn.get("count", 1),
            ))

        return ValidationResponse(
            valid=report.get("valid", True),
            track_count=report.get("track_count", 0),
            artist_count=report.get("artist_count", 0),
            errors=errors,
            warnings=warnings,
        )

    # No validation report - try to build one from cached data
    try:
        artists = cache.load_artists()
        return ValidationResponse(
            valid=True,
            track_count=sum(a.get("track_count", 0) for a in artists),
            artist_count=len(artists),
            errors=[],
            warnings=[],
        )
    except FileNotFoundError:
        return ValidationResponse(
            valid=True,
            track_count=0,
            artist_count=0,
            errors=[],
            warnings=[],
        )
