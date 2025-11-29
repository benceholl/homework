from hashlib import sha256
from sqlalchemy import func, text
from typing import Dict, List, Union
from sqlmodel import Session, select
from sqlalchemy.dialects.postgresql import insert
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, FastAPI, HTTPException

from db import get_session, init_db
from models import PipelineRun, PipelineRunBase, PipelineRunRead


app = FastAPI(
    title="Homework API",
    version="1.0.0",
    description="Collect CI/CD pipeline runs and expose them for dashboards and consumers.",
    contact={"name": "Ex Ample", "email": "you@example.com"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


@app.post(
    "/events",
    response_model=List[PipelineRunRead],
    status_code=201,
    tags=["events"],
    summary="Ingest pipeline runs (single or array)",
    description="Upserts on (build_id, branch). Accepts a single object or an array of objects.",
)
def ingest_events(
    payload: Union[PipelineRunBase, List[PipelineRunBase]],
    session: Session = Depends(get_session),
) -> List[PipelineRunRead]:
    runs = payload if isinstance(payload, list) else [payload]
    saved: List[PipelineRun] = []

    for run in runs:
        values = run.model_dump()
        key_input = (
            f"{run.build_id}|{run.branch}|{run.start_time.isoformat()}|"
            f"{run.end_time.isoformat() if run.end_time else ''}|{run.result}|"
            f"{run.repo_name or ''}|{run.commit_sha or ''}|{run.runner or ''}|{run.workflow or ''}"
        )
        values["idempotency_key"] = sha256(key_input.encode("utf-8")).hexdigest()
        stmt = (
            insert(PipelineRun)
            .values(values)
            .on_conflict_do_update(
                index_elements=["idempotency_key"],
                set_=values,
            )
            .returning(PipelineRun)
        )
        db_run = session.exec(stmt).scalar_one()
        saved.append(db_run)

    session.commit()
    return [PipelineRunRead.model_validate(run) for run in saved]


@app.get(
    "/events",
    response_model=List[PipelineRunRead],
    tags=["events"],
    summary="List recent pipeline runs",
    description="Returns up to 100 most recent runs ordered by start_time desc.",
)
def list_events(session: Session = Depends(get_session)) -> List[PipelineRunRead]:
    stmt = select(PipelineRun).order_by(PipelineRun.start_time.desc()).limit(100)
    rows = session.exec(stmt).all()
    return [PipelineRunRead.model_validate(row) for row in rows]


@app.get(
    "/stats/summary",
    tags=["stats"],
    summary="Aggregated run statistics",
    description="Counts by result, average duration by branch, and latest run per branch.",
)
def stats_summary(session: Session = Depends(get_session)) -> Dict:
    counts = session.exec(
        select(PipelineRun.result, func.count()).group_by(PipelineRun.result)
    ).all()
    avg_duration = session.exec(
        select(
            PipelineRun.branch,
            func.avg(
                func.extract("epoch", PipelineRun.end_time - PipelineRun.start_time)
            ),
        )
        .where(PipelineRun.end_time.is_not(None))
        .group_by(PipelineRun.branch)
    ).all()

    latest_runs: Dict[str, PipelineRun] = {}
    ordered = session.exec(
        select(PipelineRun).order_by(PipelineRun.branch, PipelineRun.start_time.desc())
    ).all()
    for row in ordered:
        if row.branch not in latest_runs:
            latest_runs[row.branch] = row

    return {
        "counts_by_result": {result: count for result, count in counts},
        "avg_duration_seconds_by_branch": {branch: avg for branch, avg in avg_duration},
        "latest_run_by_branch": {
            branch: PipelineRunRead.model_validate(run).model_dump()
            for branch, run in latest_runs.items()
        },
    }


@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Pings the database to confirm availability.",
)
def health(session: Session = Depends(get_session)) -> Dict[str, str]:
    try:
        session.exec(text("SELECT 1")).one()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
