"""Resume library, generated cover letters and screening-answer drafts."""

import hashlib
import uuid
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.models import Document, Job, Resume
from app.schemas.documents import (
    ApplySuggestionsIn,
    CoverLetterEdit,
    CoverLetterIn,
    DocumentOut,
    GeneratedDocument,
    GeneratedResume,
    GenerateResumeIn,
    ResumeDetail,
    ResumeOut,
    ScreeningIn,
    UploadResult,
)
from app.schemas.profile import ProfileOut, ProfileUpdate, SkillIn
from app.services import audit, documents, profile_service, resume_parser
from app.services.render import render_document, render_resume
from app.services.resume_files import UploadRejected, check_upload

router = APIRouter(tags=["documents"])

MIME = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "pdf": "application/pdf"}


def _attachment(data: bytes, file_name: str, mime: str) -> Response:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in file_name)[:150]
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{safe}"'})


def _resume(db: DbSession, user: CurrentUser, resume_id: uuid.UUID) -> Resume:
    r = db.get(Resume, resume_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return r


def _document(db: DbSession, user: CurrentUser, doc_id: uuid.UUID) -> Document:
    d = db.get(Document, doc_id)
    if d is None or d.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    return d


def _job(db: DbSession, job_id: uuid.UUID | None) -> Job | None:
    if job_id is None:
        return None
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


# ---------------------------------------------------------------- resumes


@router.get("/resumes", response_model=list[ResumeOut])
def list_resumes(user: CurrentUser, db: DbSession) -> list[Resume]:
    stmt = select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc())
    return list(db.scalars(stmt))


@router.post("/resumes/upload", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
def upload_resume(
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    file: UploadFile = File(...),
) -> UploadResult:
    data = file.file.read(settings.max_upload_bytes + 1)  # never read more than the limit + 1 byte
    try:
        checked = check_upload(file.filename, data, settings.max_upload_bytes)
    except UploadRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    sha = hashlib.sha256(checked.data).hexdigest()
    existing = db.scalars(select(Resume).where(Resume.user_id == user.id, Resume.sha256 == sha)).first()
    if existing:
        response.status_code = status.HTTP_200_OK
        return UploadResult(
            resume=ResumeOut.model_validate(existing),
            duplicate=True,
            suggestions=resume_parser.parse(existing.extracted_text or ""),
        )
    count = len(list(db.scalars(select(Resume.id).where(Resume.user_id == user.id, Resume.kind == "uploaded"))))
    r = Resume(
        user_id=user.id,
        label="Uploaded resume",
        kind="uploaded",
        version=count + 1,
        file_name=checked.file_name,
        mime_type=checked.mime_type,
        size_bytes=len(checked.data),
        sha256=sha,
        content=checked.data,
        extracted_text=checked.text,
    )
    db.add(r)
    db.flush()
    audit.record(
        db,
        "resume.uploaded",
        user_id=user.id,
        entity_type="resume",
        entity_id=r.id,
        details={"size": len(checked.data), "type": checked.extension},
        request=request,
    )
    db.commit()
    return UploadResult(
        resume=ResumeOut.model_validate(r), duplicate=False, suggestions=resume_parser.parse(checked.text)
    )


@router.get("/resumes/{resume_id}", response_model=ResumeDetail)
def get_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ResumeDetail:
    r = _resume(db, user, resume_id)
    return ResumeDetail(
        **ResumeOut.model_validate(r).model_dump(), content_json=r.content_json, has_text=bool(r.extracted_text)
    )


@router.get("/resumes/{resume_id}/suggestions")
def resume_suggestions(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict:
    r = _resume(db, user, resume_id)
    if r.kind != "uploaded":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Suggestions exist only for uploaded resumes")
    return resume_parser.parse(r.extracted_text or "")


@router.post("/resumes/{resume_id}/apply", response_model=ProfileOut)
def apply_suggestions(
    resume_id: uuid.UUID, body: ApplySuggestionsIn, request: Request, user: CurrentUser, db: DbSession
) -> ProfileOut:
    """Copy reviewed values into the profile. Only fields the user explicitly sent are changed."""
    _resume(db, user, resume_id)
    profile = profile_service.update(db, user, body.profile, request)
    if body.add_education:
        merged = list(profile.education) + [e.model_dump() for e in body.add_education]
        profile = profile_service.update(db, user, ProfileUpdate(education=merged[:20]), request)
    if body.add_skills:
        current = [
            SkillIn(
                name=cs.skill.display_name,
                level=cs.level,
                years_experience=float(cs.years_experience) if cs.years_experience is not None else None,
                is_primary=cs.is_primary,
            )
            for cs in profile.skills
        ]
        have = {s.name.lower() for s in current}
        current += [SkillIn(name=n) for n in body.add_skills if n.lower() not in have]
        profile = profile_service.replace_skills(db, user, current[:200], request)
    audit.record(
        db,
        "resume.suggestions_applied",
        user_id=user.id,
        entity_type="resume",
        entity_id=resume_id,
        details={
            "fields": sorted(body.profile.model_fields_set),
            "skills_added": len(body.add_skills),
            "education_added": len(body.add_education),
        },
        request=request,
    )
    db.commit()
    return profile_service.to_out(profile_service.get_or_create(db, user))


@router.post("/resumes/generate", response_model=GeneratedResume)
def generate_resume(
    body: GenerateResumeIn, request: Request, response: Response, user: CurrentUser, db: DbSession
) -> GeneratedResume:
    job = _job(db, body.job_id)
    profile = profile_service.get_or_create(db, user)
    if not profile.full_name.strip():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Add your name to the profile before generating a resume.")
    try:
        content = documents.build_resume(profile, job)
    except documents.FactCheckFailed as exc:  # defensive: generation must never add facts
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Fact check failed: {exc}") from exc
    r, created = documents.save_generated_resume(db, user, content, job)
    if created:
        audit.record(
            db,
            "resume.generated",
            user_id=user.id,
            entity_type="resume",
            entity_id=r.id,
            details={"kind": r.kind, "version": r.version},
            request=request,
        )
    db.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return GeneratedResume(resume=ResumeOut.model_validate(r), created=created)


@router.get("/resumes/{resume_id}/download")
def download_resume(
    resume_id: uuid.UUID, user: CurrentUser, db: DbSession, format: Literal["docx", "pdf"] = "docx"
) -> Response:
    r = _resume(db, user, resume_id)
    if r.kind == "uploaded":
        original = "pdf" if r.mime_type == MIME["pdf"] else "docx"
        if format != original:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail=f"Uploaded files download in their original format ({original})."
            )
        return _attachment(r.content or b"", r.file_name, r.mime_type)
    assert r.content_json is not None
    name = r.file_name.rsplit(".", 1)[0] + f".{format}"
    return _attachment(render_resume(r.content_json, format), name, MIME[format])


@router.delete("/resumes/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(resume_id: uuid.UUID, request: Request, user: CurrentUser, db: DbSession) -> None:
    r = _resume(db, user, resume_id)
    db.delete(r)
    audit.record(db, "resume.deleted", user_id=user.id, entity_type="resume", entity_id=resume_id, request=request)
    db.commit()


# ---------------------------------------------------------------- cover letters and screening answers


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    user: CurrentUser,
    db: DbSession,
    job_id: uuid.UUID | None = None,
    kind: Literal["cover_letter", "screening_answers"] | None = None,
) -> list[Document]:
    stmt = select(Document).where(Document.user_id == user.id)
    if job_id:
        stmt = stmt.where(Document.job_id == job_id)
    if kind:
        stmt = stmt.where(Document.kind == kind)
    return list(db.scalars(stmt.order_by(Document.created_at.desc())))


def _saved(
    db: DbSession,
    user: CurrentUser,
    request: Request,
    response: Response,
    kind: str,
    content: dict,
    job: Job | None,
    title: str,
) -> GeneratedDocument:
    d, created = documents.save_document(db, user, kind, content, job, title)
    if created:
        audit.record(
            db,
            f"{kind}.generated",
            user_id=user.id,
            entity_type="document",
            entity_id=d.id,
            details={"version": d.version},
            request=request,
        )
    db.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return GeneratedDocument(document=DocumentOut.model_validate(d), created=created)


@router.post("/documents/cover-letter", response_model=GeneratedDocument)
def generate_cover_letter(
    body: CoverLetterIn, request: Request, response: Response, user: CurrentUser, db: DbSession
) -> GeneratedDocument:
    job = _job(db, body.job_id)
    assert job is not None
    content = documents.build_cover_letter(profile_service.get_or_create(db, user), job)
    return _saved(
        db, user, request, response, "cover_letter", content, job, f"Cover letter – {job.title}, {job.company}"
    )


@router.put("/documents/{doc_id}", response_model=GeneratedDocument)
def edit_cover_letter(
    doc_id: uuid.UUID, body: CoverLetterEdit, request: Request, response: Response, user: CurrentUser, db: DbSession
) -> GeneratedDocument:
    d = _document(db, user, doc_id)
    if d.kind != "cover_letter":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Only cover letters can be edited")
    content = {**d.content, **body.model_dump(), "edited": True}
    job = _job(db, d.job_id)
    return _saved(db, user, request, response, "cover_letter", content, job, d.title)


@router.post("/documents/screening-answers", response_model=GeneratedDocument)
def generate_screening_answers(
    body: ScreeningIn, request: Request, response: Response, user: CurrentUser, db: DbSession
) -> GeneratedDocument:
    job = _job(db, body.job_id)
    content = documents.build_screening_answers(profile_service.get_or_create(db, user), body.questions, job)
    title = f"Screening answers – {job.title}, {job.company}" if job else "Screening answers"
    return _saved(db, user, request, response, "screening_answers", content, job, title)


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Document:
    return _document(db, user, doc_id)


@router.get("/documents/{doc_id}/download")
def download_document(
    doc_id: uuid.UUID, user: CurrentUser, db: DbSession, format: Literal["docx", "pdf"] = "docx"
) -> Response:
    d = _document(db, user, doc_id)
    stem = "cover-letter" if d.kind == "cover_letter" else "screening-answers"
    return _attachment(render_document(d.content, format), f"{stem}-v{d.version}.{format}", MIME[format])
