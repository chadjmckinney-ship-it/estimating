from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EstimatorRole(str, Enum):
    admin = "admin"
    estimator = "estimator"
    viewer = "viewer"


class EstimatorBase(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, examples=["jsmith"])
    full_name: str = Field(..., min_length=1, max_length=200, examples=["Jane Smith"])
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=40, examples=["512-555-0100"])
    title: str | None = Field(None, max_length=120, examples=["Senior Estimator"])
    role: EstimatorRole = EstimatorRole.estimator
    notes: str | None = None
    is_active: bool = True


class EstimatorCreate(EstimatorBase):
    pass


class EstimatorUpdate(BaseModel):
    """All fields optional for PATCH-style updates."""

    username: str | None = Field(None, min_length=1, max_length=64)
    full_name: str | None = Field(None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=40)
    title: str | None = Field(None, max_length=120)
    role: EstimatorRole | None = None
    notes: str | None = None
    is_active: bool | None = None


class EstimatorRead(EstimatorBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
