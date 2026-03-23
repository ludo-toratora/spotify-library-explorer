"""Recompute endpoints.

POST /api/recompute - Trigger pipeline recomputation
GET /api/recompute/{job_id} - Get job status
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks

from app.api.dependencies import (
    get_cache, get_config, get_uploads_dir, clear_all_caches,
    get_graph_presets, get_embedding_presets
)
from app.api.models import RecomputeRequest, RecomputeResponse, JobStatus
from app.pipeline.runner import PipelineRunner, PipelineConfig

router = APIRouter()
logger = logging.getLogger(__name__)


def get_jobs(request: Request) -> dict[str, dict]:
    """Get jobs dict from app state."""
    return getattr(request.app.state, "jobs", {})


def run_pipeline_job(
    job_id: str,
    jobs: dict[str, dict],
    tracks_path: Path,
    config: PipelineConfig,
    force: bool = False,
) -> None:
    """Run pipeline in background.

    Updates jobs dict with progress and results.
    """
    job = jobs[job_id]
    job["status"] = "running"
    job["started_at"] = datetime.now().isoformat()

    def progress_callback(step_id: str, message: str, pct: float) -> None:
        job["current_step"] = step_id
        job["progress"] = pct
        job["log"].append({
            "time": datetime.now().isoformat(),
            "step": step_id,
            "message": message,
        })
        if "done" in message or "cached" in message:
            if step_id not in job["steps_completed"]:
                job["steps_completed"].append(step_id)

    try:
        # Clear in-memory caches so runner re-reads config/cache on this run.
        # Do NOT wipe cache files upfront — that leaves artists.json missing
        # for the whole pipeline duration and serves empty data to the UI.
        # The runner's hash-based invalidation handles stale cache detection.
        clear_all_caches()
        if force:
            job["log"].append({
                "time": datetime.now().isoformat(),
                "step": "system",
                "message": "Force recompute: cache will be invalidated per step",
            })

        runner = PipelineRunner(config)
        result = runner.run(tracks_path, progress_callback=progress_callback, force=force)

        if result.success:
            job["status"] = "completed"
            job["result"] = {
                "artists_count": result.artists_count,
                "graphs_computed": result.graphs_computed,
                "embeddings_computed": result.embeddings_computed,
                "cached_steps": result.cached_steps,
            }
        else:
            job["status"] = "failed"
            job["errors"] = result.errors

    except Exception as e:
        logger.exception(f"Pipeline job {job_id} failed")
        job["status"] = "failed"
        job["errors"] = [str(e)]

    finally:
        job["completed_at"] = datetime.now().isoformat()
        # Clear caches so next request gets fresh data
        clear_all_caches()


@router.post("/recompute", response_model=RecomputeResponse)
async def trigger_recompute(
    request: Request,
    background_tasks: BackgroundTasks,
    body: RecomputeRequest,
) -> RecomputeResponse:
    """Trigger pipeline recomputation.

    Runs the pipeline in a background task. Use GET /api/recompute/{job_id}
    to poll for status.

    Args:
        presets: Graph presets to compute (default: all)
        embedding_presets: Embedding presets to compute (default: all)
        force: Clear cache and force full recompute
        config_overrides: Temporary config changes for this run

    Returns:
        Job ID to track progress
    """
    jobs = get_jobs(request)

    # Find tracks file
    uploads_dir = get_uploads_dir()
    # Prefer normalized_tracks.json (canonical), fall back to most recent timestamped file
    canonical = uploads_dir / "normalized_tracks.json"
    timestamped = sorted(uploads_dir.glob("tracks_*.json"), reverse=True)
    if canonical.exists():
        tracks_path = canonical
    elif timestamped:
        tracks_path = timestamped[0]
    else:
        raise HTTPException(
            status_code=400,
            detail="No tracks file found. Upload a file first via POST /api/upload"
        )

    # Build config
    config = get_config()

    # Apply overrides if provided
    if body.config_overrides:
        for key, value in body.config_overrides.items():
            if key in config:
                if isinstance(config[key], dict) and isinstance(value, dict):
                    config[key].update(value)
                else:
                    config[key] = value

    pipeline_config = PipelineConfig.from_yaml(
        Path(__file__).parent.parent.parent / "config.yaml"
    )

    # Override presets if specified
    if body.presets:
        pipeline_config.graph_presets = body.presets
    if body.embedding_presets:
        pipeline_config.embedding_presets = body.embedding_presets

    # Create job
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": 0.0,
        "steps_completed": [],
        "current_step": "",
        "errors": [],
        "result": None,
        "log": [],
        "tracks_file": tracks_path.name,
        "created_at": datetime.now().isoformat(),
        "tracks_path": str(tracks_path),
    }

    # Start background task
    background_tasks.add_task(
        run_pipeline_job,
        job_id,
        jobs,
        tracks_path,
        pipeline_config,
        body.force,
    )

    return RecomputeResponse(job_id=job_id, status="pending")


@router.get("/recompute/{job_id}", response_model=JobStatus)
async def get_job_status(request: Request, job_id: str) -> JobStatus:
    """Get status of a recompute job.

    Poll this endpoint to track pipeline progress.
    """
    jobs = get_jobs(request)

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    job = jobs[job_id]

    return JobStatus(
        job_id=job["job_id"],
        status=job["status"],
        progress=job["progress"],
        steps_completed=job["steps_completed"],
        current_step=job["current_step"],
        errors=job["errors"],
        result=job.get("result"),
        log=job.get("log", []),
        tracks_file=job.get("tracks_file", ""),
    )


@router.get("/recompute")
async def list_jobs(request: Request) -> dict:
    """List all recompute jobs."""
    jobs = get_jobs(request)

    return {
        "jobs": [
            {
                "job_id": j["job_id"],
                "status": j["status"],
                "progress": j["progress"],
                "created_at": j.get("created_at"),
            }
            for j in jobs.values()
        ]
    }
