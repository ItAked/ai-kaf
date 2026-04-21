from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, File, UploadFile, Form
from openai import OpenAI
from pathlib import Path
from dotenv import load_dotenv
import base64, os, json, uuid
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)
# load_dotenv(".env")

print("📂 BASE_DIR:", BASE_DIR)
print("📄 ENV_PATH:", ENV_PATH)


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID")

print("KEY:", bool(OPENAI_API_KEY))
print("VECTOR:", bool(VECTOR_STORE_ID))

client = OpenAI(api_key=OPENAI_API_KEY)

# ══════════════════════════════════════════
# 💾 التخزين المشفر
# ══════════════════════════════════════════
STORAGE_DIR       = r"conversations"
STORAGE_PLAIN     = os.path.join(STORAGE_DIR, "plain")
STORAGE_ENCRYPTED = os.path.join(STORAGE_DIR, "encrypted")
os.makedirs(STORAGE_PLAIN, exist_ok=True)
os.makedirs(STORAGE_ENCRYPTED, exist_ok=True)

ENCRYPTION_KEY = b"9f3a6c8d2e1b4a7f5c9d0e2a1b3c4d6e"

def encrypt_text(text: str) -> str:
    key = ENCRYPTION_KEY
    text_bytes = text.encode("utf-8")
    encrypted = bytes([text_bytes[i] ^ key[i % len(key)] for i in range(len(text_bytes))])
    return base64.b64encode(encrypted).decode("utf-8")

def decrypt_text(encrypted_b64: str) -> str:
    key = ENCRYPTION_KEY
    encrypted = base64.b64decode(encrypted_b64.encode("utf-8"))
    decrypted = bytes([encrypted[i] ^ key[i % len(key)] for i in range(len(encrypted))])
    return decrypted.decode("utf-8")

def save_conversation(session_id: str, user_type: str, question: str, answer: str, mode: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str = datetime.now().strftime("%Y-%m-%d")

    record = {
        "session_id": session_id,
        "timestamp": timestamp,
        "user_type": user_type,
        "mode": mode,
        "question": question,
        "answer": answer
    }

    plain_file = os.path.join(STORAGE_PLAIN, f"{date_str}_{session_id}.json")
    records = []

    if os.path.exists(plain_file):
        try:
            with open(plain_file, "r", encoding="utf-8") as f:
                records = json.load(f)
        except:
            pass

    records.append(record)

    with open(plain_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    enc_file = os.path.join(STORAGE_ENCRYPTED, f"{date_str}_{session_id}.enc")
    enc_records = []

    if os.path.exists(enc_file):
        try:
            with open(enc_file, "r", encoding="utf-8") as f:
                dec = decrypt_text(f.read())
            enc_records = json.loads(dec)
        except:
            pass

    enc_records.append(record)

    with open(enc_file, "w", encoding="utf-8") as f:
        f.write(encrypt_text(json.dumps(enc_records, ensure_ascii=False)))

    print(f"💾 محادثة محفوظة: {session_id} | {user_type} | {mode}")

# ══════════════════════════════════════════
# 🚨 الطوارئ والـ Fallback
# ══════════════════════════════════════════
EMERGENCY_KEYWORDS = [
    "ألم في الصدر", "ضيق تنفس", "صعوبة التنفس", "لا أتنفس",
    "فقدان الوعي", "إغماء", "سكتة", "جلطة", "شلل مفاجئ",
    "نزيف حاد", "نزيف لا يتوقف", "حرق شديد", "تسمم",
    "جرعة زائدة", "انتحار", "إيذاء النفس", "chest pain"
]

def is_emergency(text: str) -> bool:
    lowered = text.lower()
    return any(k.lower() in lowered for k in EMERGENCY_KEYWORDS)

def is_greeting(text: str) -> bool:
    greetings = ["السلام", "هلا", "مرحبا", "مرحباً", "اهلا", "أهلاً",
                 "hello", "hi", "مساء", "صباح", "كيف حالك"]
    lowered = text.lower()
    return any(x in lowered for x in greetings) and len(text.split()) <= 6

EMERGENCY_MSG  = (
    "⚠️ تحذير عاجل — حالة طارئة\n\n"
    "تبدو هذه الحالة طارئة وتستدعي تدخلاً فورياً.\n\n"
    "اتصل بالإسعاف الآن: 911\n\n"
    "لا تتأخر. سلامتك أهم من أي شيء آخر.\n\n"
    "بعد التأكد من سلامتك يمكنني مساعدتك في الجانب القانوني."
)
FALLBACK_EMPTY = "اكتب سؤالك أو حالتك وسأحللها فوراً."
FALLBACK_ERROR = "حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى."

# ══════════════════════════════════════════
# 💬 System Prompts
# ══════════════════════════════════════════
SYSTEM_PROMPTS = {
# ─────────────── مريض ───────────────
"patient": """
أنت "كاف" — مستشار طبي وقانوني ذكي متخصص في المنظومة الصحية والقانونية السعودية.
اسمك كاف. تتحدث مع مريض أو أهل مريض.
جميع ردودك بالعربية الفصحى الواضحة — حتى لو المصادر إنجليزية.
لا تخترع أي رقم مادة أو نص.
 
قواعد السلامة الطبية:
- لا تجزم بتشخيص — استخدم "قد يكون" و"يُنصح بـ"
- إذا لم تتوفر معلومات كافية → قل: "لا توجد معلومات طبية موثوقة كافية، يُنصح بمراجعة طبيب"
- في حالات الطوارئ → نبّه فوراً
 
أوضاع العمل:
 
الوضع 1 — أول رسالة:
**🔍 فهم الحالة:** ملخص سريع
**⚖️ التحليل الأولي:** المخالفة / قوة الحالة
**📚 الأنظمة المبدئية:** من النصوص المقدمة
ثم: "يمكنك إضافة تفاصيل، وعندما تكون جاهزاً اطلب **التحليل النهائي**."
 
الوضع 2 — محادثة: أجب بشكل طبيعي مختصر.
 
الوضع 3 — التحليل النهائي:
**🔍 فهم الحالة الكاملة**
**🩺 التحليل الطبي:** تقييم الإجراء / اشتباه خطأ طبي
**💊 النصائح الطبية:** ماذا يفعل الآن / فحوصات / متى للطوارئ / متابعة / وقاية
**⚖️ التحليل القانوني:** المخالفة / المسؤولية / قوة الحالة
 
**📚 الأنظمة واللوائح المطبقة:**
⚠️ هذا القسم إلزامي ومفصّل — اذكر كل مادة وجدتها في النصوص المقدمة ذات صلة بالحالة، لا تتجاهل أياً منها.
لكل مادة اكتب:
┌─────────────────────────────────────────┐
│ 📌 النظام  : [اسم النظام / اللائحة]
│ رقم المادة : [حرفياً من النص]
│ رقم الصفحة : [حرفياً من النص]
│ نص المادة  : [اقتبس الجزء المرتبط مباشرة]
│ الربط      : [كيف تنطبق على هذه الحالة]
└─────────────────────────────────────────┘
كرّر هذا الإطار لكل مادة — لا تدمج مادتين في إطار واحد.
 
**🛡️ الخطوات العملية**
**📋 تنويه:** هذا للاستئناس فقط ولا يُغني عن طبيب أو محامٍ مختص.
 
قواعد ثابتة:
- اذكر كل مادة من النصوص المقدمة ذات صلة — لا تكتفِ بمادة واحدة
- أرقام المواد: من النصوص فقط — "غير مذكور في النص" إذا غائب
- المواد من البحث الإضافي: أضف "(من البحث الإضافي — يُنصح بالتحقق)"
- لا تخترع مواد غير موجودة في النصوص المقدمة
""",
 
# ─────────────── ممارس صحي ───────────────
"doctor": """
أنت "كاف" — مستشار طبي وقانوني متخصص، تتحدث مع ممارس صحي (طبيب أو أخصائي).
اسمك كاف. لغتك طبية احترافية — تتعامل مع زميل مختص.
جميع ردودك بالعربية الفصحى — حتى لو المصادر إنجليزية.
لا تخترع أي رقم مادة أو نص.
 
تخصصك:
• تقييم الإجراءات الطبية وفق معايير الرعاية (Standard of Care)
• تحليل مخاطر المسؤولية الطبية
• إرشادات التوثيق الطبي القانوني
• الحماية القانونية للممارس الصحي
 
أوضاع العمل:
 
الوضع 1 — أول رسالة:
**🩺 تقييم الإجراء:** مطابق / غير مطابق / يحتاج تحقق
**⚖️ التقييم القانوني المبدئي:** تعرض قانوني محتمل / الأنظمة ذات الصلة
ثم: "يمكنك إضافة تفاصيل، وعندما تكون جاهزاً اطلب **التحليل النهائي**."
 
الوضع 2 — محادثة: أجب بلغة طبية مختصرة.
 
الوضع 3 — التحليل النهائي:
**📋 ملخص الحالة السريرية**
**🩺 التقييم الطبي المهني:** Standard of Care / وجود خطأ / نوعه
**⚖️ التحليل القانوني:** مستوى التعرض / المسؤولية / نقاط القوة والضعف
**📚 الأنظمة واللوائح المطبقة:**
⚠️ اذكر كل مادة من النصوص المقدمة ذات صلة — لا تكتفِ بمادة واحدة.
لكل مادة:
┌─────────────────────────────────────────┐
│ 📌 النظام  : [اسم النظام / اللائحة]
│ رقم المادة : [حرفياً من النص]
│ رقم الصفحة : [حرفياً من النص]
│ نص المادة  : [اقتبس الجزء المرتبط]
│ الصلة      : [كيف تنطبق على الممارس]
└─────────────────────────────────────────┘
كرّر لكل مادة على حدة.
 
**🛡️ توصيات الحماية القانونية:** التوثيق / الإبلاغ / التأمين / الجهات
 
قواعد ثابتة:
- اذكر كل مادة ذات صلة — لا تكتفِ بمادة واحدة
- أرقام المواد: من النصوص فقط
- اللغة طبية احترافية دائماً
""",
 
# ─────────────── محامي ───────────────
"lawyer": """
أنت "كاف" — مستشار قانوني متخصص في القضايا الطبية، تتحدث مع محامٍ أو مستشار قانوني.
اسمك كاف. لغتك قانونية احترافية دقيقة.
جميع ردودك بالعربية الفصحى — حتى لو المصادر إنجليزية.
لا تخترع أي رقم مادة أو نص.
 
تخصصك:
• تحليل أركان المسؤولية الطبية (الخطأ، الضرر، العلاقة السببية)
• تقييم قوة الدعوى وأدلتها
• استخراج النصوص القانونية بدقة
• تحليل الاختصاص القضائي
• تقدير التعويضات وفق الأنظمة السعودية
• استراتيجية الدفاع أو الادعاء
 
أوضاع العمل:
 
الوضع 1 — أول رسالة:
**📁 تكييف القضية:** النوع / الجهة المختصة
**⚖️ التقييم الأولي:** أركان المسؤولية (خطأ ✓/✗ / ضرر ✓/✗ / سببية ✓/✗) / قوة القضية
ثم: "يمكنك إضافة وقائع، وعندما تكون جاهزاً اطلب **التحليل النهائي**."
 
الوضع 2 — محادثة: أجب بلغة قانونية مختصرة.
 
الوضع 3 — التحليل النهائي (المذكرة القانونية):
**📋 الوقائع:** ملخص منظم
**🩺 الجانب الطبي:** تقييم الخطأ / معيار الإهمال
**⚖️ التحليل القانوني:** أركان المسؤولية / قوة الدعوى / نقاط القوة والضعف / التقادم
**📚 الأنظمة واللوائح المطبقة:**
⚠️ اذكر كل مادة من النصوص المقدمة ذات صلة بالقضية — لا تكتفِ بمادة واحدة أو اثنتين.
لكل مادة:
┌─────────────────────────────────────────┐
│ 📌 النظام  : [اسم النظام / اللائحة]
│ رقم المادة : [حرفياً من النص]
│ رقم الصفحة : [حرفياً من النص]
│ نص المادة  : [اقتبس الجزء المرتبط]
│ الحجية     : [كيف تُوظَّف في الدعوى]
└─────────────────────────────────────────┘
كرّر لكل مادة على حدة.
 
**💰 التعويضات المحتملة:** مادي / معنوي / أساس التقدير
**🗂️ الإجراءات المقترحة:** الخطوات / المهل / الأدلة المطلوبة
 
قواعد ثابتة:
- اذكر كل مادة ذات صلة — لا تكتفِ بمادة أو اثنتين
- أرقام المواد: من النصوص فقط
- اللغة قانونية احترافية دقيقة دائماً
""",
}

# ══════════════════════════════════════════
# 🎯 كشف الوضع
# ══════════════════════════════════════════
def detect_mode(question: str, has_history: bool) -> str:
    q = question.strip()
    deep_all = ["التفصيل الممل", "فصّل كل شي", "بالتفصيل الممل", "تفصيل كامل", "فصّلني", "فصلني"]
    deep_med = ["تفصيل طبي", "فصّل طبياً", "فصل طبي", "التفصيل الطبي", "طبي بالتفصيل"]
    deep_law = ["تفصيل قانوني", "فصّل قانونياً", "فصل قانوني", "التفصيل القانوني", "كل المواد", "جميع المواد"]
    final_kw = ["التحليل النهائي", "حللني", "التحليل الكامل", "حلل الآن", "عطني التحليل", "أعطني التحليل", "حللي"]

    if any(k in q for k in deep_all):
        return "deep_all"
    if any(k in q for k in deep_med):
        return "deep_med"
    if any(k in q for k in deep_law):
        return "deep_law"
    if any(k in q for k in final_kw):
        return "final"
    if not has_history:
        return "first"
    return "chat"

def classify_medical_intent(question: str) -> str:
    q = question.lower()
    legal = ["خطأ طبي", "إهمال", "شكوى", "تعويض", "مسؤولية", "ضرر", "وفاة", "أقاضي", "محكمة", "تقصير"]
    medical = ["عملية", "جراحة", "دواء", "علاج", "تشخيص", "مضاعفات", "نزيف", "عدوى", "بعد العملية", "عندي"]
    general = ["ما هو", "ما هي", "كيف", "متى", "لماذا", "ما الفرق", "أبغى أعرف", "وش يعني", "هل صحيح"]

    if any(k in q for k in legal):
        return "needs_legal"
    if sum(1 for k in medical if k in q) >= 2:
        return "needs_medical"
    if any(k in q for k in general) and not any(k in q for k in legal):
        return "general_inquiry"
    return "unknown"

def classify_with_gpt(question: str) -> str:
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "صنّف السؤال في فئة واحدة وأجب بكلمة: general_inquiry / needs_legal / needs_medical"
                },
                {"role": "user", "content": question}
            ],
            max_tokens=10,
            temperature=0
        )
        result = (res.choices[0].message.content or "").strip().lower()
        if result in ("general_inquiry", "needs_legal", "needs_medical"):
            return result
        return "needs_medical"
    except:
        return "needs_medical"

# ══════════════════════════════════════════
# 🧠 OpenAI File Search
# ══════════════════════════════════════════
def build_user_input(question: str, image_content=None, image_mime_type="image/jpeg"):
    if image_content:
        return [{
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        question
                        + "\n\n[تعليمات: صورة مرفقة. حلّل المحتوى الطبي أو المرئي المرتبط بالسؤال. "
                          "لا تحاول التعرف على هوية الأشخاص.]"
                    )
                },
                {
                    "type": "input_image",
                    "image_url": f"data:{image_mime_type};base64,{image_content}"
                }
            ]
        }]

    return [{
        "role": "user",
        "content": [
            {"type": "input_text", "text": question}
        ]
    }]

def ask_knowledge_base(system_text: str, user_question: str, image_content=None, image_mime_type="image/jpeg") -> str:
    if not VECTOR_STORE_ID:
        return "لم يتم ضبط VECTOR_STORE_ID في ملف البيئة."

    try:
        response = client.responses.create(
            model="gpt-4.1",
            instructions=system_text,
            input=build_user_input(user_question, image_content, image_mime_type),
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [VECTOR_STORE_ID]
                }
            ]
        )
        return response.output_text or FALLBACK_ERROR
    except Exception as e:
        print(f"OpenAI file_search error: {e}")
        return FALLBACK_ERROR

# ══════════════════════════════════════════
# 🚀 Startup
# ══════════════════════════════════════════
@app.on_event("startup")
def startup():
    if not OPENAI_API_KEY:
        print("⚠️ OPENAI_API_KEY غير موجود في .env")
    else:
        print("✅ OPENAI_API_KEY موجود")

    if not VECTOR_STORE_ID:
        print("⚠️ VECTOR_STORE_ID غير موجود في .env")
    else:
        print("✅ VECTOR_STORE_ID موجود")

@app.post("/reload")
def reload_index():
    return {
        "status": "ok",
        "message": "لا يوجد reload محلي الآن. إذا رفعت ملفات جديدة إلى الـ vector store فسيتم استخدامها بعد اكتمال الفهرسة."
    }

# ══════════════════════════════════════════
# 🚀 API الموحّد
# ══════════════════════════════════════════
@app.post("/analyze")
async def analyze(
    question: str = Form(None),
    history: str = Form(None),
    user_type: str = Form("patient"),
    intent_type: str = Form("auto"),
    file: UploadFile = File(None)
):
    if not question or not question.strip():
        return PlainTextResponse(FALLBACK_EMPTY)

    if is_greeting(question):
        greet = {
            "patient": "وعليكم السلام 👋\n\nأنا كاف — مستشارك الطبي والقانوني.\nأخبرني بحالتك مباشرة وسأحللها. 🎯",
            "doctor": "وعليكم السلام 👋\n\nأنا كاف — مستشارك الطبي القانوني للممارسين الصحيين.\nاعرض حالتك السريرية وسأحللها. 🩺",
            "lawyer": "وعليكم السلام 👋\n\nأنا كاف — مستشارك في القضايا الطبية القانونية.\nاعرض قضيتك وسأحللها. ⚖️",
        }
        return PlainTextResponse(greet.get(user_type, greet["patient"]))

    if is_emergency(question):
        return PlainTextResponse(EMERGENCY_MSG)

    if user_type == "patient" and intent_type == "general_inquiry":
        detected = classify_medical_intent(question)
        if detected == "unknown":
            detected = classify_with_gpt(question)
        if detected in ("needs_legal", "needs_medical"):
            intent_type = detected

    image_content = None
    image_mime_type = "image/jpeg"

    if file:
        contents = await file.read()
        image_content = base64.b64encode(contents).decode()
        fname = (file.filename or "").lower()
        if fname.endswith(".png"):
            image_mime_type = "image/png"
        elif fname.endswith(".webp"):
            image_mime_type = "image/webp"
        elif fname.endswith(".gif"):
            image_mime_type = "image/gif"

    chat_history = []
    if history:
        try:
            parsed = json.loads(history)
            chat_history = [
                m for m in parsed
                if m.get("role") in ("user", "assistant")
                and isinstance(m.get("content"), str)
                and m.get("content", "").strip()
            ]
        except:
            pass

    if user_type == "patient" and intent_type == "general_inquiry":
        mode = "general_inquiry"
    else:
        mode = detect_mode(question, has_history=bool(chat_history))

    mode_instructions = {
        "general_inquiry": (
            "الوضع: استفسار طبي عام.\n"
            "أجب على السؤال الطبي مباشرة بلغة بسيطة.\n"
            "لا تدخل في تحليل قانوني إلا إذا طلب المستخدم ذلك."
        ),
        "first": "الوضع: أول رسالة. أعطِ تحليلاً أولياً سريعاً ثم وجّه المستخدم لإضافة مزيد من التفاصيل عند الحاجة.",
        "chat": "الوضع: محادثة عادية. أجب بشكل طبيعي مختصر.",
        "final": "الوضع: تحليل نهائي. أعطِ تحليلاً شاملاً ومنظماً.",
        "deep_med": "الوضع: تفصيل طبي عميق. لا تختصر.",
        "deep_law": "الوضع: تفصيل قانوني عميق. لا تختصر.",
        "deep_all": "الوضع: تفصيل طبي وقانوني عميق. لا تختصر."
    }

    history_text = ""
    if chat_history:
        history_text = "\n\n".join([
            f"{'المستخدم' if m['role'] == 'user' else 'المساعد'}: {m['content']}"
            for m in chat_history
        ])

    system_text = (
        SYSTEM_PROMPTS.get(user_type, SYSTEM_PROMPTS["patient"])
        + "\n\n"
        + mode_instructions.get(mode, "")
        + "\n\n"
        + "تعليمات الاسترجاع:\n"
          "- اعتمد أولاً على النصوص المسترجعة من الملفات داخل قاعدة المعرفة.\n"
          "- لا تخترع مواد أو صفحات أو نصوص غير ظاهرة.\n"
          "- عند الاستناد إلى مادة، اذكر اسم النظام ورقم المادة كما ظهر في النص المسترجع.\n"
          "- إذا لم تظهر مادة صريحة، قل ذلك بوضوح.\n"
    )

    composed_question = question
    if history_text:
        composed_question = (
            f"سياق المحادثة السابقة:\n{history_text}\n\n"
            f"السؤال الحالي:\n{question}"
        )

    final_answer = ask_knowledge_base(
        system_text=system_text,
        user_question=composed_question,
        image_content=image_content,
        image_mime_type=image_mime_type
    )

    try:
        session_id = str(uuid.uuid4())[:8]
        save_conversation(session_id, user_type, question, final_answer, mode)
    except Exception as e:
        print(f"⚠️ خطأ في الحفظ: {e}")

    return PlainTextResponse(final_answer)