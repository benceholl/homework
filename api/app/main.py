import os
import logging

from enum import Enum
from datetime import datetime
from sqlalchemy.dialects.postgresql import insert
from fastapi import FastAPI, Depends
from sqlmodel import Field, SQLModel, UniqueConstraint, create_engine, select, Session


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

class Result(str, Enum):
    success = "success"
    failed = "failed"
    cancelled = "cancelled"
    running = "running"

class PipelineRunBase(SQLModel):
    build_id: str
    branch: str
    result: Result
    start_time: datetime
    end_time: datetime | None = None

    @classmethod
    def __get_validators__(cls):
        yield cls.ensure_tz

    @staticmethod
    def ensure_tz(values) -> datetime:
        for key in ("start_time", "end_time"):
            dt = values.get(key)
            if dt and (dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None):
                raise ValueError(f"{key} must be timezone-aware")
        if values.get("end_time") and values["end_time"] < values["start_time"]:
            raise ValueError("end_time must be >= start_time")
        return values

class PipelineRun(PipelineRunBase, table = True):
    __table_args__ = (UniqueConstraint("build_id", "branch", name="uq_build_branch"),)
    id: int | None = Field(default=None, primary_key=True)

class PipelineRunRead(PipelineRunBase):
    id: int
    duration_seconds: float | None


# FastAPI app
app = FastAPI(title="Homework API")

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not configured")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(engine)

# Dependency
def get_session():
    with Session(engine) as session:
        yield session


@app.post("/pipeline-runs", response_model=PipelineRunRead, status_code=201)
def upsert_run(run: PipelineRunBase, session: Session = Depends(get_session)):
    stmt = (
        insert(PipelineRun)
        .values(run.model_dump())
        .on_conflict_do_update(
            index_elements=["build_id", "branch"],
            set_=run.model_dump(),
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

@app.get("/pipeline-runs", response_model=list[PipelineRunRead])
def list_runs(session: Session = Depends(get_session)):
    rows = session.exec(select(PipelineRun)).all()
    return [
        PipelineRunRead(
            **row.__dict__,
            duration_seconds=(
                (row.end_time - row.start_time).total_seconds() if row.end_time else None
            ),
        )
        for row in rows
    ]

@app.get("/stats/summary", response_model=PipelineRunBase)
def create_summary()