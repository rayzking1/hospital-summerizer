import io
import json
import os
import re
from datetime import datetime
from typing import Any, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# --- БЕЗОПАСНА ПРОВЕРКА ЗА WEASYPRINT (За да няма 'Load failed' crash в облака) ---
WEASYPRINT_AVAILABLE = False
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except Exception as e:
    print(f"⚠️ WeasyPrint не е наличен (липсват системни библиотеки): {e}")

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
    summary = Column(Text)  # Съхранява JSON стринг
    alerts = Column(Text)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- PYDANTIC СХЕМА ЗА ЗAДЪЛЖИТЕЛЕН JSON ИЗХОД ОТ GEMINI ---
class HospitalizationInfo(BaseModel):
    patient_name: Optional[str] = Field(None, description="Име на пациента или null")
    age: Optional[str] = Field(None, description="Възраст или null")
    iz_number: Optional[str] = Field(None, description="Номер на ИЗ или null")
    hospitalization_period: Optional[str] = Field(None, description="Период на хоспитализация")

class Diagnoses(BaseModel):
    primary_diagnosis: str = Field(..., description="Основна диагноза")
    procedures: List[str] = Field(default_factory=list, description="Списък с процедури/операции")
    comorbidities: List[str] = Field(default_factory=list, description="Придружаващи заболявания")

class Anamnesis(BaseModel):
    complaints_and_hpi: str = Field(..., description="Оплаквания и история на заболяването")
    past_medical_history: str = Field(..., description="Минали заболявания")
    allergies: str = Field(..., description="Алергии или 'Без данни'")

class StatusAndDiagnostics(BaseModel):
    physical_status: str = Field(..., description="Обективно състояние при прием")
    initial_labs: List[str] = Field(default_factory=list, description="Лабораторни показатели")
    imaging_and_instrumental: List[str] = Field(default_factory=list, description="Образни и инструментални изследвания")

class ClinicalCourse(BaseModel):
    treatment_administered: List[str] = Field(default_factory=list, description="Приложено лечение")
    evolution: str = Field(..., description="Ход на заболяването и следоперативен/болничен престой")

class DischargeSummary(BaseModel):
    discharge_status: str = Field(..., description="Състояние при изписването")
    outcome: str = Field(..., description="Изход от заболяването (напр. С подобрение)")

class EpicrisisJSONSchema(BaseModel):
    hospitalization_info: HospitalizationInfo
    diagnoses: Diagnoses
    anamnesis: Anamnesis
    status_and_diagnostics: StatusAndDiagnostics
    clinical_course_and_treatment: ClinicalCourse
    discharge_summary: DischargeSummary
    recommendations: List[str] = Field(default_factory=list, description="Препоръки за домашно лечение и режим")
    warnings: List[str] = Field(default_factory=list, description="Предупреждения за липсващи важни медицински данни")


# --- СИСТЕМЕН ПРОМПТ ЗА МЕДИЦИНСКА ТОЧНОСТ ---
SYSTEM_INSTRUCTION = """
Ти си медицински асистент и специалист по медицинска документация.
Твоята задача е да преобразуваш сурови медицински бележки или транскрипции в официална, структурирана болнична епикриза.

ПРАВИЛА:
1. Спазвай стриктно предоставената JSON схема. Връщай САМО валиден JSON обект.
2. Преформулирай бележките на академичен български медицински език.
3. Извличай само наличните данни. Не измисляй диагнози, стойности или факти.
4. Ако някоя ключова секция липсва в суровия текст (напр. липсва кръвно налягане или липсват препоръки), добави съответно предупреждение в масива `warnings`.
"""


# --- FASTAPI ПРИЛОЖЕНИЕ ---
app = FastAPI(title="MediSummarize AI API", version="2.0.0")

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
    clinical_data: Optional[str] = None
    summary: Optional[Any] = None
    uin: Optional[str] = "1000000000"


def validate_uin(uin: str):
    if not uin:
        return "1000000000"
    clean_uin = str(uin).strip()
    if not re.match(r"^\d{10}$", clean_uin):
        return "1000000000"
    return clean_uin


def anonymize_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\b\d{10}\b", "[ЕГН АНОНИМИЗИРАНО]", text)
    text = re.sub(
        r"(\+359|0)\s?\d{2,3}[\s\-]?\d{2,3}[\s\-]?\d{2,3}",
        "[ТЕЛЕФОН АНОНИМИЗИРАН]",
        text,
    )
    return text


def audit_labs(text: str) -> list:
    alerts = []
    if not text:
        return alerts

    potassium = re.search(r"калий[:\s]+(\d+[\.,]?\d*)", text, re.IGNORECASE)
    if potassium:
        val = float(potassium.group(1).replace(",", "."))
        if val > 5.5:
            alerts.append(f"⚠️ КРИТИЧНА СТОЙНОСТ: Хиперкалиемия ({val} mmol/L)!")
        elif val < 3.5:
            alerts.append(f"⚠️ КРИТИЧНА СТОЙНОСТ: Хипокалиемия ({val} mmol/L)!")

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
    return {"status": "online", "message": "MediSummarize API v2.0 (Structured JSON) is running"}


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

    if not req.clinical_data:
        raise HTTPException(status_code=400, detail="Моля, въведете медицински данни.")

    safe_text = anonymize_text(req.clinical_data)
    alerts = audit_labs(safe_text)

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=safe_text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=EpicrisisJSONSchema,
            ),
        )

        structured_json = json.loads(response.text)

        # Запис в базата данни като JSON текст
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
            "summary": structured_json,
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
            contents=[audio_part, "Моля, състави официална структурирана епикриза въз основа на аудиото."],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=EpicrisisJSONSchema,
            ),
        )

        structured_json = json.loads(response.text)
        alerts = audit_labs(response.text)

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
            "summary": structured_json,
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
        try:
            parsed_summary = json.loads(r.summary)
        except Exception:
            parsed_summary = r.summary

        result.append(
            {
                "id": r.id,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "clinical_data": r.clinical_data,
                "summary": parsed_summary,
                "alerts": r.alerts.split(" | ") if r.alerts else [],
            }
        )

    return {"status": "success", "history": result}


@app.post("/api/generate-pdf")
def generate_pdf(req: SummarizeRequest):
    validate_uin(req.uin)

    if not WEASYPRINT_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="PDF генераторът (WeasyPrint) не е наличен на този сървър поради липсващи C-библиотеки в Vercel/Render. Използвайте бутона за печат в браузъра.",
        )

    if not GEMINI_API_KEY or not client:
        raise HTTPException(
            status_code=500,
            detail="API ключът за Gemini не е настроен на сървъра.",
        )

    try:
        # Ако вече има подаден структуриран summary от фронтенда
        if req.summary and isinstance(req.summary, dict):
            data = req.summary
        else:
            safe_text = anonymize_text(req.clinical_data or "")
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=safe_text,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=EpicrisisJSONSchema,
                ),
            )
            data = json.loads(response.text)

        alerts = audit_labs(json.dumps(data, ensure_ascii=False))

        procedures_html = "".join([f"<li>{p}</li>" for p in data.get('diagnoses', {}).get('procedures', [])])
        comorbidities_html = "".join([f"<li>{c}</li>" for c in data.get('diagnoses', {}).get('comorbidities', [])])
        labs_html = "".join([f"<li>{l}</li>" for l in data.get('status_and_diagnostics', {}).get('initial_labs', [])])
        imaging_html = "".join([f"<li>{i}</li>" for i in data.get('status_and_diagnostics', {}).get('imaging_and_instrumental', [])])
        treatment_html = "".join([f"<li>{t}</li>" for t in data.get('clinical_course_and_treatment', {}).get('treatment_administered', [])])
        recs_html = "".join([f"<li>{r}</li>" for r in data.get('recommendations', [])])

        alerts_html = ""
        if alerts:
            alerts_items = "".join([f"<li>{a}</li>" for a in alerts])
            alerts_html = f"""
            <div style="background-color: #fff5f5; border: 1px solid #feb2b2; padding: 8px 12px; margin-bottom: 15px; border-radius: 4px;">
                <strong style="color: #c53030; font-size: 9pt;">⚠️ КЛИНИЧНИ СИГНАЛИ:</strong>
                <ul style="margin: 3px 0 0 0; color: #9b2c2c; font-size: 8.5pt;">{alerts_items}</ul>
            </div>
            """

        today_date = datetime.now().strftime("%d.%m.%Y г.")

        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                @page {{ size: A4; margin: 15mm; }}
                body {{ font-family: 'DejaVu Sans', Arial, sans-serif; color: #1a202c; line-height: 1.4; font-size: 9.5pt; }}
                .hospital-header {{ text-align: center; border-bottom: 2px solid #1a365d; padding-bottom: 8px; margin-bottom: 12px; }}
                .hospital-title {{ font-size: 13pt; font-weight: bold; color: #1a365d; text-transform: uppercase; }}
                .doc-title {{ text-align: center; font-size: 14pt; font-weight: bold; margin: 10px 0; }}
                .patient-info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; font-size: 8.5pt; }}
                .patient-info-table td {{ border: 1px solid #cbd5e0; padding: 4px 6px; }}
                .bg-light {{ background-color: #f7fafc; font-weight: bold; }}
                .section-title {{ color: #1a365d; font-size: 10pt; font-weight: bold; border-bottom: 1px solid #e2e8f0; margin-top: 10px; margin-bottom: 4px; text-transform: uppercase; }}
                .signatures {{ margin-top: 30px; width: 100%; font-size: 9pt; }}
            </style>
        </head>
        <body>
            <div class="hospital-header">
                <div class="hospital-title">УМБАЛ "АЛЕКСАНДРОВСКА" ЕАД</div>
                <div style="font-size: 8.5pt; color: #4a5568;">гр. София, бул. "Св. Георги Софийски" № 1</div>
            </div>

            <div class="doc-title">Е П И К Р И З А</div>

            <table class="patient-info-table">
                <tr>
                    <td class="bg-light" width="20%">Пациент:</td>
                    <td width="30%">{data.get('hospitalization_info', {}).get('patient_name') or '[АНОНИМИЗИРАН]'}</td>
                    <td class="bg-light" width="20%">Дата:</td>
                    <td width="30%">{today_date}</td>
                </tr>
                <tr>
                    <td class="bg-light">История № (ИЗ):</td>
                    <td>{data.get('hospitalization_info', {}).get('iz_number') or '3912/2026'}</td>
                    <td class="bg-light">Престой:</td>
                    <td>{data.get('hospitalization_info', {}).get('hospitalization_period') or 'Не е посочен'}</td>
                </tr>
            </table>

            {alerts_html}

            <div class="section-title">1. Окончателна диагноза</div>
            <p><strong>Основна:</strong> {data.get('diagnoses', {}).get('primary_diagnosis', '')}</p>
            {f"<p><strong>Процедури:</strong></p><ul>{procedures_html}</ul>" if procedures_html else ""}
            {f"<p><strong>Придружаващи:</strong></p><ul>{comorbidities_html}</ul>" if comorbidities_html else ""}

            <div class="section-title">2. Анамнеза</div>
            <p>{data.get('anamnesis', {}).get('complaints_and_hpi', '')}</p>
            <p><strong>Минали заболявания:</strong> {data.get('anamnesis', {}).get('past_medical_history', '')}</p>
            <p><strong>Алергии:</strong> {data.get('anamnesis', {}).get('allergies', '')}</p>

            <div class="section-title">3. Обективно състояние и изследвания</div>
            <p>{data.get('status_and_diagnostics', {}).get('physical_status', '')}</p>
            {f"<ul>{labs_html}</ul>" if labs_html else ""}
            {f"<ul>{imaging_html}</ul>" if imaging_html else ""}

            <div class="section-title">4. Проведено лечение и еволюция</div>
            {f"<ul>{treatment_html}</ul>" if treatment_html else ""}
            <p>{data.get('clinical_course_and_treatment', {}).get('evolution', '')}</p>

            <div class="section-title">5. Състояние при изписване</div>
            <p><strong>Изход:</strong> {data.get('discharge_summary', {}).get('outcome', '')}</p>
            <p>{data.get('discharge_summary', {}).get('discharge_status', '')}</p>

            <div class="section-title">6. Препоръки</div>
            <ul>{recs_html}</ul>

            <table class="signatures">
                <tr>
                    <td width="50%">
                        <strong>Лекуващ лекар:</strong> ........................<br/>
                        <span style="font-size: 8pt; color: #4a5568;">/ д-р Иван Иванов /</span>
                    </td>
                    <td width="50%" style="text-align: right;">
                        <strong>Зав. Клиника:</strong> ........................<br/>
                        <span style="font-size: 8pt; color: #4a5568;">/ Проф. д-р М. Петров, дмн /</span>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        pdf_bytes = HTML(string=full_html).write_pdf()

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=epicrisis_official.pdf"
            },
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
