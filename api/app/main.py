from typing import List
from fastapi import Depends, FastAPI
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from .db import get_session, init_db
from .models import PipelineRun, PipelineRunBase, PipelineRunRead


app = FastAPI(title="Homework API")

init_db()


@app.post("/pipeline-runs", response_model=PipelineRunRead, status_code=201)
def upsert_run(run: PipelineRunBase, session: Session = Depends(get_session)):
    stmt = (
        insert(PipelineRun)
        .values(run.dict())
        .on_conflict_do_update(
            index_elements=["build_id", "branch"],
            set_=run.dict(),
        )
        .returning(PipelineRun)
    )
    db_run = session.exec(stmt).one()
    session.commit()
    return PipelineRunRead(
        **db_run.__dict__,
        duration_seconds=(
            (db_run.end_time - db_run.start_time).total_seconds()
            if db_run.end_time
            else None
        ),
    )


@app.get("/pipeline-runs", response_model=List[PipelineRunRead])
def list_runs(session: Session = Depends(get_session)):
    rows = session.exec(select(PipelineRun)).all()
    return [
        PipelineRunRead(
            **row.__dict__,
            duration_seconds=(
                (row.end_time - row.start_time).total_seconds()
                if row.end_time
                else None
            ),
        )
        for row in rows
    ]
