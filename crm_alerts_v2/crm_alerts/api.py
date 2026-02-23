"""
CRM Stalled Alert — REST API with Swagger UI
=============================================
Provides HTTP endpoints to trigger reports, check status, and inspect config.

Run with:
    uvicorn api:app --host 0.0.0.0 --port 8000

Swagger UI:  http://localhost:8000/docs
ReDoc:       http://localhost:8000/redoc
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).parent

app = FastAPI(
    title="CRM Daily Stalled Alert API",
    description=(
        "REST API for the **CRM Daily Stalled Alert System**.\n\n"
        "Use this API to:\n"
        "- Trigger a manual report run (with or without sending emails)\n"
        "- Check the status and result of the last run\n"
        "- View the active configuration (credentials redacted)\n"
        "- Stream recent application logs\n"
        "- Health-check the service\n\n"
        "The report runner automatically skips weekends. "
        "Pass `force=true` to override."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "Paikane CRM Team"},
)

# In-memory run state (resets on server restart)
_run_state: dict = {
    "is_running":       False,
    "last_run_at":      None,
    "last_run_mode":    None,
    "last_run_result":  None,
    "last_run_output":  None,
}


# ============================================================================
# REQUEST / RESPONSE SCHEMAS
# ============================================================================

class RunRequest(BaseModel):
    test_mode: bool = Field(
        default=False,
        description="If true, generates Excel locally without sending any emails.",
    )
    force: bool = Field(
        default=False,
        description="If true, runs even on weekends (overrides business-day check).",
    )
    config_path: Optional[str] = Field(
        default=None,
        description="Absolute path to an alternate config.json. Leave blank to use default.",
    )


class RunResponse(BaseModel):
    message: str
    mode: str
    triggered_at: str


class StatusResponse(BaseModel):
    is_running: bool
    last_run_at: Optional[str]
    last_run_mode: Optional[str]
    last_run_result: Optional[str]


# ============================================================================
# BACKGROUND JOB
# ============================================================================

def _execute_run(test_mode: bool, force: bool, config_path: Optional[str]):
    _run_state["is_running"] = True
    _run_state["last_run_at"] = datetime.now().isoformat()
    _run_state["last_run_mode"] = "TEST" if test_mode else "LIVE"
    _run_state["last_run_result"] = "running"
    _run_state["last_run_output"] = None

    args = [sys.executable, str(BASE_DIR / "run.py")]
    if test_mode:
        args.append("--test")
    if force:
        args.append("--force")
    if config_path:
        args.extend(["--config", config_path])

    try:
        result = subprocess.run(
            args,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=1800,   # 30-minute hard cap
        )
        _run_state["last_run_result"] = "success" if result.returncode == 0 else "failed"
        _run_state["last_run_output"] = (result.stdout + result.stderr)[-4000:]
    except subprocess.TimeoutExpired:
        _run_state["last_run_result"] = "timeout"
    except Exception as exc:
        _run_state["last_run_result"] = f"error: {exc}"
    finally:
        _run_state["is_running"] = False


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/health", tags=["System"], summary="Health check")
def health_check():
    """Returns HTTP 200 with a timestamp confirming the API is alive."""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "service": "CRM Stalled Alert API",
    }


@app.get("/api/config", tags=["Configuration"], summary="View active config (redacted)")
def get_config():
    """
    Returns the contents of `config.json` with all credentials replaced by `***`.
    Useful for verifying thresholds, stages, and recipients without exposing secrets.
    """
    config_path = BASE_DIR / "config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="config.json not found")

    with open(config_path) as f:
        config = json.load(f)

    # Redact sensitive fields in-place
    if "zoho" in config:
        for key in ("client_id", "client_secret", "refresh_token"):
            if key in config["zoho"]:
                config["zoho"][key] = "***"
    if "email" in config:
        if "sender_password" in config["email"]:
            config["email"]["sender_password"] = "***"

    return config


@app.post(
    "/api/run",
    response_model=RunResponse,
    tags=["Reports"],
    summary="Trigger a manual report run",
)
def trigger_run(request: RunRequest, background_tasks: BackgroundTasks):
    """
    Kicks off a report run in the background.

    - **test_mode=true** → builds Excel files locally, no emails sent.
    - **test_mode=false** → live run — sends emails to all configured recipients.
    - **force=true** → bypasses the weekend/holiday check.

    Returns immediately. Use `GET /api/status` to poll for the result.
    """
    if _run_state["is_running"]:
        raise HTTPException(
            status_code=409,
            detail="A run is already in progress. Check /api/status.",
        )

    background_tasks.add_task(
        _execute_run, request.test_mode, request.force, request.config_path
    )

    return RunResponse(
        message="Run triggered successfully",
        mode="TEST" if request.test_mode else "LIVE",
        triggered_at=datetime.now().isoformat(),
    )


@app.get(
    "/api/status",
    response_model=StatusResponse,
    tags=["Reports"],
    summary="Get last run status",
)
def get_status():
    """
    Returns the status of the most recent report run:
    - `is_running`: whether a run is currently in progress
    - `last_run_result`: `success`, `failed`, `timeout`, `running`, or an error message
    """
    return StatusResponse(
        is_running=_run_state["is_running"],
        last_run_at=_run_state["last_run_at"],
        last_run_mode=_run_state["last_run_mode"],
        last_run_result=_run_state["last_run_result"],
    )


@app.get("/api/logs", tags=["System"], summary="Tail the application log")
def get_logs(lines: int = 100):
    """
    Returns the last `lines` lines from `daily_alert.log`.

    - Default: last 100 lines
    - Max recommended: 500
    """
    log_path = BASE_DIR / "daily_alert.log"
    if not log_path.exists():
        return {"total_lines": 0, "returned_lines": 0, "logs": []}

    with open(log_path, encoding="utf-8") as f:
        all_lines = f.readlines()

    tail = all_lines[-lines:]
    return {
        "total_lines": len(all_lines),
        "returned_lines": len(tail),
        "logs": [line.rstrip() for line in tail],
    }
