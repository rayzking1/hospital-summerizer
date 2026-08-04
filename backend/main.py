import io
import os
import re
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from weasyprint import HTML

# --- НАСТРОЙКА НА БАЗАТА ДАННИ (SQLite) ---
DATABASE_URL = "sqlite:///./epicrises.db"
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class EpicrisisModel(Base):
    __tablename__ = "epicrises"

    id = Column(Integer, primary_key=True, index=True)
    doctor_uin = Column(String(10), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    clinical_data = Column(Text)
    summary = Column(Text)
    alerts = Column(Text)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- СТРОГА ИНСТРУКЦИЯ ПРОТИВ ХАЛЮЦИНИРАНЕ (GUARDRAILS) ---
STRICT_MEDICAL_INSTRUCTION = """
Ти си медицински софтуерен модул, който генерира ОФИЦИАЛНИ БОЛНИЧНИ ЕПИКРИЗИ.

КРИТИЧНИ ИЗИСКВАНИЯ ЗА ФОРМАТ:
1. ВРЪЩАЙ САМО И ЕДИНСТВЕНО ТЕКСТА НА ЕПИКРИЗАТА. 
2. ЗАБРАНЕНО Е използването на въвеждащи/заключителни изречения (напр. "Ето епикризата:", "Въз основа на предоставения запис...", "Транскрипция:").
3. ЗАБРАНЕНО Е измислянето на липсващи данни. Ако дадена секция няма информация във входа, напиши: "Няма предоставени данни".

СТРУКТУРА НА СЕКЦИИТЕ (Използвай точно тези заглавия):
ИЗСЛЕДВАНИЯ И ЛЕЧЕНИЕ
1. Окончателна диагноза (Основно заболяване, Придружаващи заболявания, Усложнения)
2. Анамнеза
3. Обективно състояние (Физикален преглед)
4. Параклинични и образни изследвания
5. Проведено лечение и терапевтична динамика
6. Настъпили усложнения (ако има)
7. ИЗХОД ОТ БОЛЕСТТА И СЪСТОЯНИЕ ПРИ ИЗПИСВАНЕТО
8. Препоръки за домашно лечение, хигиенно-диетичен режим и последващ контрол (вкл. рецепта)
"""

Нормализирай медицинската терминология, изглади стила на изказване, но спазвай стриктно наличните данни!
"""


# --- FASTAPI ПРИЛОЖЕНИЕ ---
app = FastAPI(title="MediSummarize AI API", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hospital-summarizer.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

DOCTORS_DB = {
    "1000000000": {
        "name": "д-р Иван Иванов",
        "specialty": "Кардиология",
        "hospital": "УМБАЛ Александровска",
        "password": "password123",
    }
}


class LoginRequest(BaseModel):
    uin: str = Field(..., description="10-цифрен УИН на лекаря")
    password: str


class SummarizeRequest(BaseModel):
    clinical_data: str
    uin: Optional[str] = "1000000000"
    model_name: Optional[str] = None


def validate_uin(uin: str):
    if not uin:
        return "1000000000"
    clean_uin = str(uin).strip()
    if not re.match(r"^\d{10}$", clean_uin):
        return "1000000000"
    return clean_uin


def anonymize_text(text: str) -> str:
    text = re.sub(r"\b\d{10}\b", "[ЕГН АНОНИМИЗИРАНО]", text)
    text = re.sub(
        r"(\+359|0)\s?\d{2,3}[\s\-]?\d{2,3}[\s\-]?\d{2,3}",
        "[ТЕЛЕФОН АНОНИМИЗИРАН]",
        text,
    )
    return text


def audit_labs(text: str) -> list:
    alerts = []

    # Калий
    potassium = re.search(r"калий[:\s]+(\d+[\.,]?\d*)", text, re.IGNORECASE)
    if potassium:
        val = float(potassium.group(1).replace(",", "."))
        if val > 5.5:
            alerts.append(f"⚠️ КРИТИЧНА СТОЙНОСТ: Хиперкалиемия ({val} mmol/L)!")
        elif val < 3.5:
            alerts.append(f"⚠️ КРИТИЧНА СТОЙНОСТ: Хипокалиемия ({val} mmol/L)!")

    # Креатинин
    creatinine = re.search(r"креатинин[:\s]+(\d+[\.,]?\d*)", text, re.IGNORECASE)
    if creatinine:
        val = float(creatinine.group(1).replace(",", "."))
        if val > 150:
            alerts.append(
                f"⚠️ КРИТИЧНА СТОЙНОСТ: Повишен Креатинин ({val} µmol/L)!"
            )

    return alerts


@app.get("/")
def read_root():
    return {"status": "online", "message": "MediSummarize API is running"}


@app.post("/api/auth/login")
def login(credits: LoginRequest):
    validate_uin(credits.uin)
    doctor = DOCTORS_DB.get(credits.uin)

    if not doctor or doctor["password"] != credits.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Грешен УИН или парола!",
        )

    return {
        "status": "success",
        "doctor": doctor,
        "token": f"bearer_token_{credits.uin}",
    }


@app.post("/api/summarize")
def generate_summary(req: SummarizeRequest, db: Session = Depends(get_db)):
    clean_uin = validate_uin(req.uin)

    if not GEMINI_API_KEY or not client:
        raise HTTPException(
            status_code=500,
            detail="API ключът за Gemini не е настроен на сървъра.",
        )

    safe_text = anonymize_text(req.clinical_data)
    alerts = audit_labs(safe_text)

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=safe_text,
            config=types.GenerateContentConfig(
                system_instruction=STRICT_MEDICAL_INSTRUCTION,
                temperature=0.1,  # Ниска температура срещу халюцинации
            ),
        )

        # Запис в историята
        new_entry = EpicrisisModel(
            doctor_uin=clean_uin,
            clinical_data=safe_text,
            summary=response.text,
            alerts=" | ".join(alerts) if alerts else "",
        )
        db.add(new_entry)
        db.commit()
        db.refresh(new_entry)

        return {
            "status": "success",
            "id": new_entry.id,
            "summary": response.text,
            "alerts": alerts,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    uin: Optional[str] = Form("1000000000"),
    db: Session = Depends(get_db)
):
    """Ендпойнт за качване на аудио файлове и директното им превръщане в епикриза."""
    clean_uin = validate_uin(uin)

    if not GEMINI_API_KEY or not client:
        raise HTTPException(
            status_code=500,
            detail="API ключът за Gemini не е настроен на сървъра.",
        )

    try:
        audio_bytes = await file.read()
        audio_part = types.Part.from_bytes(
            data=audio_bytes,
            mime_type=file.content_type or "audio/mp4"
        )

        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=[audio_part, "Моля, направи транскрипция и състави епикриза на базата единствено на чутото в записа."],
            config=types.GenerateContentConfig(
                system_instruction=STRICT_MEDICAL_INSTRUCTION,
                temperature=0.1,  # Ниска температура срещу халюцинации
            ),
        )

        safe_text = anonymize_text(response.text)
        alerts = audit_labs(safe_text)

        new_entry = EpicrisisModel(
            doctor_uin=clean_uin,
            clinical_data="[Гласов запис / Аудио транскрипция]",
            summary=response.text,
            alerts=" | ".join(alerts) if alerts else "",
        )
        db.add(new_entry)
        db.commit()
        db.refresh(new_entry)

        return {
            "status": "success",
            "id": new_entry.id,
            "summary": response.text,
            "alerts": alerts,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/history/{uin}")
def get_history(uin: str, db: Session = Depends(get_db)):
    clean_uin = validate_uin(uin)
    records = (
        db.query(EpicrisisModel)
        .filter(EpicrisisModel.doctor_uin == clean_uin)
        .order_by(EpicrisisModel.created_at.desc())
        .all()
    )

    result = []
    for r in records:
        result.append(
            {
                "id": r.id,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "clinical_data": r.clinical_data,
                "summary": r.summary,
                "alerts": r.alerts.split(" | ") if r.alerts else [],
            }
        )

    return {"status": "success", "history": result}


@app.post("/api/generate-pdf")
def generate_pdf(req: SummarizeRequest):
    validate_uin(req.uin)

    if not GEMINI_API_KEY or not client:
        raise HTTPException(
            status_code=500,
            detail="API ключът за Gemini не е настроен на сървъра.",
        )

    safe_text = anonymize_text(req.clinical_data)
    alerts = audit_labs(safe_text)

    try:
        pdf_instruction = STRICT_MEDICAL_INSTRUCTION + "\nИзползвай HTML тагове (<h2>, <p>, <ul>, <li>, <strong>) за форматиране на епикризата."

        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=safe_text,
            config=types.GenerateContentConfig(
                system_instruction=pdf_instruction,
                temperature=0.1,
            ),
        )

        summary_text = response.text.replace("\n", "<br/>")

        alerts_html = ""
        if alerts:
            alerts_items = "".join([f"<li>{a}</li>" for a in alerts])
            alerts_html = f"""
            <div style="background-color: #fff5f5; border-left: 4px solid #e53e3e; padding: 10px; margin-bottom: 15px;">
                <strong style="color: #c53030;">Критични сигнали (Safety Audit):</strong>
                <ul style="margin: 5px 0 0 0; color: #9b2c2c;">{alerts_items}</ul>
            </div>
            """

        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                @page {{
                    size: A4;
                    margin: 20mm 15mm;
                }}
                body {{
                    font-family: 'DejaVu Sans', Arial, sans-serif;
                    color: #2d3748;
                    line-height: 1.6;
                    font-size: 10.5pt;
                }}
                .header {{
                    border-bottom: 2px solid #2b6cb0;
                    padding-bottom: 10px;
                    margin-bottom: 20px;
                }}
                .header h1 {{
                    color: #2b6cb0;
                    font-size: 18pt;
                    margin: 0;
                    text-transform: uppercase;
                }}
                .header .subtext {{
                    color: #718096;
                    font-size: 9pt;
                }}
                .content {{
                    margin-top: 10px;
                }}
                h2 {{
                    color: #2c5282;
                    font-size: 12pt;
                    border-bottom: 1px solid #e2e8f0;
                    padding-bottom: 3px;
                    margin-top: 15px;
                }}
                .footer {{
                    margin-top: 40px;
                    border-top: 1px solid #cbd5e0;
                    padding-top: 10px;
                    font-size: 8pt;
                    color: #a0aec0;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>МЕДИЦИНСКА ЕПИКРИЗА</h1>
                <div class="subtext">MediSummarize AI | Подготвена за подпис от лекар</div>
            </div>
            {alerts_html}
            <div class="content">
                {summary_text}
            </div>
            <div class="footer">
                Документът съдържа анонимизирани данни. Изисква преглед и подпис от лекуващия лекар.
            </div>
        </body>
        </html>
        """

        pdf_bytes = HTML(string=full_html).write_pdf()

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=epicrisis.pdf"
            },
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
