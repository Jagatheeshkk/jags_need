import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.profile import EmploymentIn, EmploymentOut, ProfileOut, ProfileUpdate, SkillIn
from app.services import profile_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def get_profile(user: CurrentUser, db: DbSession) -> ProfileOut:
    return profile_service.to_out(profile_service.get_or_create(db, user))


@router.patch("", response_model=ProfileOut)
def update_profile(body: ProfileUpdate, request: Request, user: CurrentUser, db: DbSession) -> ProfileOut:
    return profile_service.to_out(profile_service.update(db, user, body, request))


@router.post("/employment", response_model=EmploymentOut, status_code=status.HTTP_201_CREATED)
def add_employment(body: EmploymentIn, request: Request, user: CurrentUser, db: DbSession) -> EmploymentOut:
    return EmploymentOut.model_validate(profile_service.add_employment(db, user, body, request))


@router.put("/employment/{employment_id}", response_model=EmploymentOut)
def update_employment(
    employment_id: uuid.UUID, body: EmploymentIn, request: Request, user: CurrentUser, db: DbSession
) -> EmploymentOut:
    row = profile_service.update_employment(db, user, employment_id, body, request)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employment entry not found")
    return EmploymentOut.model_validate(row)


@router.delete("/employment/{employment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employment(employment_id: uuid.UUID, request: Request, user: CurrentUser, db: DbSession) -> None:
    if not profile_service.delete_employment(db, user, employment_id, request):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employment entry not found")


@router.put("/skills", response_model=ProfileOut)
def replace_skills(body: list[SkillIn], request: Request, user: CurrentUser, db: DbSession) -> ProfileOut:
    if len(body) > 200:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At most 200 skills")
    return profile_service.to_out(profile_service.replace_skills(db, user, body, request))
