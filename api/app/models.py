import enum

from typing import Optional
from datetime import datetime
from pydantic import model_validator
from sqlmodel import Field, SQLModel, UniqueConstraint


class Result(str, enum.Enum):
    success = "success"
    failed = "failed"
    canceled = "canceled"
    running = "running"


class PipelineRunBase(SQLModel):
    build_id: str
    branch: str
    result: Result
    start_time: datetime
    end_time: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_times(self):
        start = self.start_time
        end = self.end_time

        for key, dt in (("start_time", start), ("end_time", end)):
            if dt and (dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None):
                raise ValueError(f"{key} must be timezone-aware")

        if start and end and end < start:
            raise ValueError("end_time must be >= start_time")
        return self


class PipelineRun(PipelineRunBase, table=True):
    __table_args__ = (UniqueConstraint("build_id", "branch", name="pipeline_runs"),)

    id: Optional[int] = Field(default=None, primary_key=True)


class PipelineRunRead(PipelineRunBase):
    id: int
    duration_seconds: Optional[float] = None
