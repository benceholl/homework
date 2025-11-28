from sqlalchemy import func
from typing import Dict, List, Union
from fastapi import Depends, FastAPI
from sqlmodel import Session, select
from sqlalchemy.dialects.postgresql import insert

from .db import get_session, init_db
from .models import PipelineRun, PipelineRunBase, PipelineRunRead


app = FastAPI(title="Homework API")

init_db()


@app.post("/events", response_model=List[PipelineRunRead], status_code=201)
def ingest_events(
    payload: Union[PipelineRunBase, List[PipelineRunBase]],
    session: Session = Depends(get_session),
) -> List[PipelineRunRead]:
    runs = payload if isinstance(payload, list) else [payload]
    saved: List[PipelineRun] = []

    for run in runs:
        values = run.model_dump()
        stmt = (
            insert(PipelineRun)
            .values(values)
            .on_conflict_do_update(
                index_elements=["build_id", "branch"],
                set_=values,
            )
            .returning(PipelineRun)
        )
        db_run = session.exec(stmt).one()
        saved.append(db_run)

    session.commit()
    return [PipelineRunRead.model_validate(run) for run in saved]


@app.get("/events", response_model=List[PipelineRunRead])
def list_events(session: Session = Depends(get_session)) -> List[PipelineRunRead]:
    stmt = select(PipelineRun).order_by(PipelineRun.start_time.desc()).limit(100)
    rows = session.exec(stmt).all()
    return [PipelineRunRead.model_validate(row) for row in rows]


@app.get("/stats/summary")
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
