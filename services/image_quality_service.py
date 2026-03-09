"""
Service for image quality detection in CuratAI Backend.
Wraps the ImageQualityDetector and manages scan jobs with Supabase persistence
and in-memory SSE progress tracking.
"""

import asyncio
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from services.base import BaseService
from detector import ImageQualityDetector
from core.exceptions import DatabaseException, ValidationException

# Thread pool for CPU-bound image analysis (OpenCV/NumPy release the GIL)
_image_pool = ThreadPoolExecutor(max_workers=min(os.cpu_count() or 4, 8))

# Module-level in-memory store shared across service instances.
# Holds SSE events and intermediate results for active (non-completed) jobs.
_active_jobs: Dict[str, dict] = {}


class ImageQualityService(BaseService):
    """Service for handling image quality scanning operations."""

    def __init__(self):
        super().__init__()

    # ── Job lifecycle ─────────────────────────────────────────────────────────

    def create_job(
        self, user_id: str, project_id: str, total: int, sensitivity: str
    ) -> str:
        """Create a scan job in Supabase and set up in-memory tracking."""
        job_id = str(uuid.uuid4())

        try:
            self.db.table("scan_jobs").insert({
                "id": job_id,
                "user_id": user_id,
                "project_id": project_id,
                "status": "pending",
                "total_images": total,
                "processed_images": 0,
                "sensitivity": sensitivity,
            }).execute()
        except Exception as e:
            self.logger.error(f"Failed to create scan job in DB: {e}")
            raise DatabaseException("Failed to create scan job", operation="insert")

        _active_jobs[job_id] = {
            "status": "pending",
            "total": total,
            "processed": 0,
            "results": [],
            "events": [],
            "sensitivity": sensitivity,
        }

        self.logger.info(f"Scan job created: {job_id} ({total} images, {sensitivity})")
        return job_id

    # ── Background scan ───────────────────────────────────────────────────────

    async def run_scan(
        self, job_id: str, files_data: List[dict], sensitivity: str
    ) -> None:
        """Run the quality scan in background. Updates in-memory events and
        persists final results to Supabase."""
        job = _active_jobs.get(job_id)
        if not job:
            self.logger.error(f"Job {job_id} not found in active jobs")
            return

        job["status"] = "running"
        self._update_job_status(job_id, "running")

        detector = ImageQualityDetector(sensitivity=sensitivity)
        loop = asyncio.get_event_loop()

        # Submit all images to the thread pool
        tasks: List[Tuple[dict, str, asyncio.Future]] = []
        for fd in files_data:
            image_id = fd["image_id"]
            future = loop.run_in_executor(
                _image_pool, detector.analyze, fd["content"], image_id, fd["filename"]
            )
            tasks.append((fd, image_id, future))

        # Await results, emitting progress events as each completes
        for i, (fd, image_id, future) in enumerate(tasks):
            try:
                result = await future

                result_dict = {
                    "image_id": result.image_id,
                    "filename": result.filename,
                    "thumbnail": result.thumbnail_b64,
                    "width": result.width,
                    "height": result.height,
                    "file_size": result.file_size,
                    "quality_score": result.quality_score,
                    "is_clean": result.is_clean,
                    "overall_severity": result.overall_severity,
                    "patch_heatmap": result.patch_heatmap,
                    "issues": [
                        {
                            "type": iss.type,
                            "severity": iss.severity,
                            "score": iss.score,
                            "metadata": iss.metadata,
                        }
                        for iss in result.issues
                    ],
                }
                job["results"].append(result_dict)

                job["events"].append({
                    "type": "progress",
                    "processed": i + 1,
                    "total": job["total"],
                    "latest": {
                        "filename": result.filename,
                        "is_clean": result.is_clean,
                        "overall_severity": result.overall_severity,
                    },
                })

            except Exception as exc:
                self.logger.error(f"Error analyzing {fd['filename']}: {exc}")
                job["events"].append({
                    "type": "error",
                    "filename": fd["filename"],
                    "error": str(exc),
                    "processed": i + 1,
                    "total": job["total"],
                })

            job["processed"] = i + 1
            await asyncio.sleep(0)  # yield to event loop for SSE delivery

        # Mark completed
        job["status"] = "completed"
        job["events"].append({"type": "complete", "total": job["total"]})

        # Persist results to Supabase
        self._persist_results(job_id, job["results"])
        self._update_job_status(job_id, "completed", processed=job["processed"])

        self.logger.info(
            f"Scan job {job_id} completed: {len(job['results'])} images analysed"
        )

    # ── SSE progress ──────────────────────────────────────────────────────────

    async def get_job_progress(self, job_id: str) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted events as images are processed."""
        job = _active_jobs.get(job_id)
        if not job:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Job not found or already cleaned up'})}\n\n"
            return

        last_sent = 0
        while True:
            events = job["events"]
            while last_sent < len(events):
                yield f"data: {json.dumps(events[last_sent])}\n\n"
                last_sent += 1

            if job["status"] == "completed":
                break
            await asyncio.sleep(0.05)

    # ── Results ───────────────────────────────────────────────────────────────

    def get_results(
        self,
        job_id: str,
        category: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> dict:
        """Return scan results, optionally filtered. Reads from in-memory if
        the job is still active, otherwise from Supabase."""
        # Try in-memory first (active or recently completed)
        job = _active_jobs.get(job_id)
        if job:
            results = list(job["results"])
            status = job["status"]
            total = job["total"]
            processed = job["processed"]
        else:
            # Fall back to Supabase
            status, total, processed = self._get_job_meta(job_id)
            results = self._fetch_results_from_db(job_id)

        # Apply filters
        results = self._filter_results(results, category, severity)

        # Sort worst-first
        sev_order = {"severe": 3, "moderate": 2, "mild": 1, None: 0}
        results.sort(
            key=lambda r: sev_order.get(r.get("overall_severity"), 0), reverse=True
        )

        return {
            "job_id": job_id,
            "status": status,
            "total_images": total,
            "processed_images": processed,
            "results": results,
            "summary": self._build_summary(results),
        }

    # ── History ─────────────────────────────────────────────────────────────

    def get_history(self, user_id: str, project_id: Optional[str] = None) -> List[dict]:
        """Return completed scan jobs for a user, optionally filtered by project."""
        try:
            query = (
                self.db.table("scan_jobs")
                .select("id, project_id, sensitivity, total_images, completed_at")
                .eq("user_id", user_id)
                .eq("status", "completed")
                .order("completed_at", desc=True)
            )
            if project_id:
                query = query.eq("project_id", project_id)
            resp = query.execute()
            return [
                {
                    "job_id": row["id"],
                    "project_id": row["project_id"],
                    "sensitivity": row["sensitivity"],
                    "total_images": row["total_images"],
                    "completed_at": row["completed_at"],
                }
                for row in (resp.data or [])
            ]
        except Exception as e:
            self.logger.error(f"Failed to fetch scan history for user {user_id}: {e}")
            raise DatabaseException("Failed to fetch scan history", operation="select")

    # ── Deletion ──────────────────────────────────────────────────────────────

    def delete_job(self, job_id: str) -> None:
        """Delete a scan job from Supabase and clean up in-memory state."""
        _active_jobs.pop(job_id, None)

        try:
            self.db.table("scan_results").delete().eq("job_id", job_id).execute()
            self.db.table("scan_jobs").delete().eq("id", job_id).execute()
        except Exception as e:
            self.logger.error(f"Failed to delete scan job {job_id}: {e}")
            raise DatabaseException("Failed to delete scan job", operation="delete")

        self.logger.info(f"Scan job deleted: {job_id}")

    # ── Private helpers ───────────────────────────────────────────────────────

    def _update_job_status(
        self, job_id: str, status: str, processed: Optional[int] = None
    ) -> None:
        update: dict = {"status": status}
        if processed is not None:
            update["processed_images"] = processed
        if status == "completed":
            from datetime import datetime, timezone
            update["completed_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self.db.table("scan_jobs").update(update).eq("id", job_id).execute()
        except Exception as e:
            self.logger.error(f"Failed to update job status for {job_id}: {e}")

    def _persist_results(self, job_id: str, results: List[dict]) -> None:
        if not results:
            return
        rows = []
        for r in results:
            rows.append({
                "id": str(uuid.uuid4()),
                "job_id": job_id,
                "image_id": r["image_id"],
                "filename": r["filename"],
                "thumbnail": r["thumbnail"],
                "width": r["width"],
                "height": r["height"],
                "file_size": r["file_size"],
                "quality_score": r["quality_score"],
                "is_clean": r["is_clean"],
                "overall_severity": r["overall_severity"],
                "patch_heatmap": r["patch_heatmap"],
                "issues": r["issues"],
            })
        try:
            self.db.table("scan_results").insert(rows).execute()
        except Exception as e:
            self.logger.error(f"Failed to persist scan results for job {job_id}: {e}")

    def _get_job_meta(self, job_id: str) -> Tuple[str, int, int]:
        try:
            resp = (
                self.db.table("scan_jobs")
                .select("status, total_images, processed_images")
                .eq("id", job_id)
                .single()
                .execute()
            )
            d = resp.data
            return d["status"], d["total_images"], d["processed_images"]
        except Exception as e:
            self.logger.error(f"Failed to fetch job meta for {job_id}: {e}")
            raise DatabaseException("Scan job not found", operation="select")

    def _fetch_results_from_db(self, job_id: str) -> List[dict]:
        try:
            resp = (
                self.db.table("scan_results")
                .select("*")
                .eq("job_id", job_id)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            self.logger.error(f"Failed to fetch results for job {job_id}: {e}")
            return []

    @staticmethod
    def _filter_results(
        results: List[dict],
        category: Optional[str],
        severity: Optional[str],
    ) -> List[dict]:
        if category:
            if category == "clean":
                results = [r for r in results if r.get("is_clean")]
            else:
                results = [
                    r for r in results
                    if any(i["type"] == category for i in r.get("issues", []))
                ]
        if severity:
            results = [r for r in results if r.get("overall_severity") == severity]
        return results

    @staticmethod
    def _build_summary(results: List[dict]) -> dict:
        total = len(results)
        clean = sum(1 for r in results if r.get("is_clean"))
        categories: Dict[str, int] = {}
        severities = {"severe": 0, "moderate": 0, "mild": 0}

        for r in results:
            for iss in r.get("issues", []):
                categories[iss["type"]] = categories.get(iss["type"], 0) + 1
                if iss["severity"] in severities:
                    severities[iss["severity"]] += 1

        return {
            "total": total,
            "issues_count": total - clean,
            "clean_count": clean,
            "categories": categories,
            "severities": severities,
        }
