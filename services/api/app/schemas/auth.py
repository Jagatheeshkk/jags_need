import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Password = Field(min_length=12, max_length=256)


class SetupStatus(BaseModel):
    setup_required: bool
    bootstrap_token_required: bool


class SetupRequest(BaseModel):
    email: EmailStr
    password: str = Password
    display_name: str = Field(default="", max_length=200)
    bootstrap_token: str | None = Field(default=None, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Password


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    confirm: Literal["DELETE MY DATA"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    last_login_at: datetime | None
    created_at: datetime


class CsrfOut(BaseModel):
    csrf_token: str
