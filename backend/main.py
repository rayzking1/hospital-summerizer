from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import re
import os
from google import genai

app = FastAPI(title="MediSummarize AI API", version="1.0.0")

# CORS конфигурация
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hospital-summarizer.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализиране на новия Google GenAI клиент
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

DOCTORS_DB = {
    "1000000000": {
        "name": "д-р Иван Иванов",
        "specialty": "Кардиология",
        "hospital": "УМБАЛ Александровска",
        "password": "password123"
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
    if not re.match(r'^\d{10}$', clean_uin):
        return "1000000000"
    return clean_uin

def anonymize_text(text: str) -> str:
    text = re.sub(r'\b\d{10}\b', '[ЕГН АНОНИМИЗИРАНО]', text)
    text = re.sub(r'(\+359|0)\s?\d{2,3}[\s\-]?\d{2,3}[\s\-]?\d{2,3}', '[ТЕЛЕФОН АНОНИМИЗИРАН]', text)
    return text

def audit_labs(text: str) -> list:
    alerts = []
    potassium = re.search(r'калий[:\s]+(\d+[\.,]?\d*)', text, re.IGNORECASE)
    if potassium:
        val = float(potassium.group(1).replace(',', '.'))
        if val > 5.5:
            alerts.append(f"⚠️ КРИТИЧНА СТОЙНОСТ: Хиперкалиемия ({val} mmol/L)!")
            
    creatinine = re.search(r'креатинин[:\s]+(\d+[\.,]?\d*)', text, re.IGNORECASE)
    if creatinine:
        val = float(creatinine.group(1).replace(',', '.'))
        if val > 150:
            alerts.append(f"⚠️ КРИТИЧНА СТОЙНОСТ: Повишен Креатинин ({val} µmol/L)!")
            
    return alerts

@app.post("/api/auth/login")
def login(credits: LoginRequest):
    validate_uin(credits.uin)
    doctor = DOCTORS_DB.get(credits.uin)
    
    if not doctor or doctor["password"] != credits.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Грешен УИН или парола!"
        )
    
    return {
        "status": "success",
        "doctor": doctor,
        "token": f"bearer_token_{credits.uin}"
    }

@app.post("/api/summarize")
def generate_summary(req: SummarizeRequest):
    validate_uin(req.uin)
    
    if not GEMINI_API_KEY or not client:
        raise HTTPException(
            status_code=500, 
            detail="API ключът за Gemini не е настроен на сървъра."
        )

    safe_text = anonymize_text(req.clinical_data)
    alerts = audit_labs(safe_text)
    
    try:
        system_instruction = """
        Ти си медицински софтуерен асистент. Генерирай академична медицинска епикриза 
        на български език по следния формат:
        1. Окончателна диагноза
        2. Анамнеза
        3. Физикален преглед
        4. Параклинични изследвания
        5. Проведено лечение
        6. Препоръки и терапия за дома
        """
        
        # Използваме новия стандартен клиент с gemini-2.5-flash
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=safe_text,
            config={
                'system_instruction': system_instruction
            }
        )
        
        return {
            "status": "success",
            "summary": response.text,
            "alerts": alerts
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
