"""Synthetic resumes built in memory for tests. All people and companies are fictitious."""

import io
import zipfile

RESUME_LINES = [
    "Asha Example",
    "QA Lead | Functional and Automation Testing",
    "asha.example@example.com | +91 98765 43210 | https://www.linkedin.com/in/asha-example",
    "",
    "Professional Summary",
    "QA lead with 10 years of experience in HRMS and ERP testing, regression and UAT cycles.",
    "",
    "Experience",
    "QA Lead, Example HR Cloud  Jan 2020 - Present",
    "Led regression testing for payroll releases.",
    "Senior Test Engineer, Sample ERP Systems  Mar 2016 - Dec 2019",
    "",
    "Skills",
    "Playwright, Selenium, Postman, User Acceptance Testing, Test Strategy",
    "",
    "Certifications",
    "ISTQB Foundation Level",
    "",
    "Education",
    "B.E. Computer Science, Example University",
]


def make_docx(lines: list[str] = RESUME_LINES) -> bytes:
    import docx

    d = docx.Document()
    for line in lines:
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def make_pdf(lines: list[str] = RESUME_LINES, encrypt: bool = False) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    kw = {"encrypt": "secret"} if encrypt else {}
    c = canvas.Canvas(buf, pagesize=A4, **kw)
    y = 800
    for line in lines:
        c.drawString(50, y, line)
        y -= 16
    c.save()
    return buf.getvalue()


def make_zip_bomb() -> bytes:
    """A DOCX-shaped archive whose content expands far beyond the limit."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
        z.writestr("word/padding.bin", b"\0" * (40 * 1024 * 1024))
    return buf.getvalue()
