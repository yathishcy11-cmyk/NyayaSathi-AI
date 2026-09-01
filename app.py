from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Integer, String, Text, DateTime, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import json, os, re, secrets, io, csv, httpx, tempfile
import cv2
import numpy as np

BASE = Path(__file__).parent
load_dotenv(BASE/".env")
UPLOADS = BASE/"uploads"
UPLOADS.mkdir(exist_ok=True)

DB_URL = os.getenv("DATABASE_URL","").strip() or f"sqlite:///{BASE/'nyayasathi.db'}"
engine = create_engine(DB_URL, connect_args={"check_same_thread":False} if DB_URL.startswith("sqlite") else {}, pool_pre_ping=True)

class BaseModelDB(DeclarativeBase): pass

class ChatLog(BaseModelDB):
    __tablename__="chat_logs"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=lambda:datetime.now(timezone.utc))
    session_id: Mapped[str]=mapped_column(String(64), default="")
    language: Mapped[str]=mapped_column(String(8), default="en")
    question: Mapped[str]=mapped_column(Text)
    answer: Mapped[str]=mapped_column(Text)
    topic: Mapped[str]=mapped_column(String(120), default="unknown")
    source: Mapped[str]=mapped_column(String(255), default="")
    source_url: Mapped[str]=mapped_column(Text, default="")
    feedback: Mapped[str]=mapped_column(String(12), default="")

class KnowledgeChunk(BaseModelDB):
    __tablename__="knowledge_chunks"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    title: Mapped[str]=mapped_column(String(255))
    content: Mapped[str]=mapped_column(Text)
    source: Mapped[str]=mapped_column(String(255), default="")
    source_url: Mapped[str]=mapped_column(Text, default="")
    created_at: Mapped[datetime]=mapped_column(DateTime, default=lambda:datetime.now(timezone.utc))

BaseModelDB.metadata.create_all(engine)

app = FastAPI(title="NyayaSathi AI Full", version="3.0")
app.mount("/static", StaticFiles(directory=BASE/"static"), name="static")
TOKENS=set()

class ChatReq(BaseModel):
    message:str
    language:str="en"
    session_id:str=""

class LoginReq(BaseModel):
    username:str
    password:str

class FeedbackReq(BaseModel):
    chat_id:int
    value:str

def seed_knowledge():
    with Session(engine) as db:
        if (db.scalar(select(func.count()).select_from(KnowledgeChunk)) or 0)==0:
            items=json.loads((BASE/"data"/"knowledge.json").read_text(encoding="utf-8"))
            for it in items:
                combined=f"{it['title']}\n{it['text_en']}\n{it['text_hi']}\n{it['text_kn']}"
                db.add(KnowledgeChunk(title=it["title"],content=combined,source=it["source"],source_url=it["url"]))
            db.commit()
seed_knowledge()

def chunks_from_text(text, size=900, overlap=120):
    text=re.sub(r"\s+"," ",text).strip()
    if not text:return []
    out=[]; start=0
    while start<len(text):
        out.append(text[start:start+size])
        if start+size>=len(text):break
        start += size-overlap
    return out

def retrieve(query, top_k=3):
    with Session(engine) as db:
        rows=db.scalars(select(KnowledgeChunk)).all()
    if not rows:return []
    docs=[r.content for r in rows]
    vect=TfidfVectorizer(ngram_range=(1,2), lowercase=True, max_features=12000)
    mat=vect.fit_transform(docs+[query])
    scores=cosine_similarity(mat[-1],mat[:-1]).flatten()
    order=np.argsort(scores)[::-1][:top_k]
    return [{"score":float(scores[i]),"id":rows[i].id,"title":rows[i].title,"content":rows[i].content,
             "source":rows[i].source,"url":rows[i].source_url} for i in order if scores[i] > 0.02]

def lang_instruction(lang):
    return {"hi":"Respond in Hindi.","kn":"Respond in Kannada.","en":"Respond in English."}.get(lang,"Respond in English.")

async def llm_answer(question, lang, docs):
    key=os.getenv("LLM_API_KEY","").strip()
    if not key or not docs:return None
    ctx="\n\n".join(f"[{d['source']}] {d['content']}\nURL: {d['url']}" for d in docs)
    payload={"model":os.getenv("LLM_MODEL","gpt-4.1-mini"),"temperature":0.1,
             "messages":[
                {"role":"system","content":"You are NyayaSathi, a justice-service information navigator for India. Use ONLY the supplied context. Never invent law, deadlines, eligibility, case outcomes, or legal advice. Be concise, practical, and cite the named source in plain text. "+lang_instruction(lang)},
                {"role":"user","content":f"CONTEXT:\n{ctx}\n\nQUESTION:\n{question}"}
             ]}
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r=await c.post(os.getenv("LLM_BASE_URL","https://api.openai.com/v1").rstrip("/")+"/chat/completions",
                           headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=payload)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None

def safe_fallback(lang):
    return {
      "en":"I do not have enough verified information in the current knowledge base to answer that safely. Please use the official service links or ask about legal aid, eCourts case-status navigation, Tele-Law, or documents.",
      "hi":"वर्तमान सत्यापित ज्ञान-संग्रह में इस प्रश्न का सुरक्षित उत्तर देने के लिए पर्याप्त जानकारी नहीं है। कृपया आधिकारिक सेवा लिंक का उपयोग करें या कानूनी सहायता, eCourts केस स्थिति, टेली-लॉ या दस्तावेज़ों के बारे में पूछें।",
      "kn":"ಈ ಪ್ರಶ್ನೆಗೆ ಸುರಕ್ಷಿತವಾಗಿ ಉತ್ತರಿಸಲು ಪ್ರಸ್ತುತ ಪರಿಶೀಲಿತ ಜ್ಞಾನಕೋಶದಲ್ಲಿ ಸಾಕಷ್ಟು ಮಾಹಿತಿ ಇಲ್ಲ. ಅಧಿಕೃತ ಸೇವಾ ಲಿಂಕ್‌ಗಳನ್ನು ಬಳಸಿ ಅಥವಾ ಕಾನೂನು ಸಹಾಯ, eCourts ಪ್ರಕರಣ ಸ್ಥಿತಿ, ಟೆಲಿ-ಲಾ ಅಥವಾ ದಾಖಲೆಗಳ ಬಗ್ಗೆ ಕೇಳಿ."
    }.get(lang,"I do not have enough verified information.")

def local_summary(doc, lang):
    text=doc["content"]
    # Prefer a language-tagged seed when present; uploaded docs may be single-language.
    if lang=="hi":
        m=re.search(r"([\u0900-\u097F][^\\n]{40,})",text)
        if m:return m.group(1)[:900]
    if lang=="kn":
        m=re.search(r"([\u0C80-\u0CFF][^\\n]{40,})",text)
        if m:return m.group(1)[:900]
    # For seeded records, first English paragraph follows title.
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    return (lines[1] if len(lines)>1 else text)[:900]

def require_admin(auth):
    if not auth or not auth.startswith("Bearer ") or auth[7:] not in TOKENS:
        raise HTTPException(401,"Unauthorized")

@app.get("/")
def home(): return FileResponse(BASE/"index.html")
@app.get("/admin")
def admin(): return FileResponse(BASE/"admin.html")
@app.get("/health")
def health(): return {"ok":True,"database":"postgresql" if DB_URL.startswith("postgres") else "sqlite"}

@app.post("/api/chat")
async def chat(req:ChatReq):
    q=req.message.strip()
    if not q: raise HTTPException(400,"Question required")
    if len(q)>2500: raise HTTPException(400,"Question too long")
    lang=req.language if req.language in ("en","hi","kn") else "en"
    docs=retrieve(q)
    generated=await llm_answer(q,lang,docs)
    if generated:
        ans=generated; mode="RAG + LLM"
    elif docs:
        ans=local_summary(docs[0],lang); mode="TF-IDF verified retrieval"
    else:
        ans=safe_fallback(lang); mode="Safe fallback"
    src=docs[0]["source"] if docs else "Official service navigation"
    url=docs[0]["url"] if docs else "https://doj.gov.in/"
    topic=docs[0]["title"] if docs else "Unresolved"
    with Session(engine) as db:
        row=ChatLog(session_id=req.session_id[:64],language=lang,question=q,answer=ans,topic=topic,source=src,source_url=url)
        db.add(row);db.commit();db.refresh(row)
        cid=row.id
    return {"chat_id":cid,"answer":ans,"source":src,"source_url":url,"topic":topic,"mode":mode,
            "references":[{"source":d["source"],"url":d["url"],"score":round(d["score"],3)} for d in docs]}

@app.get("/api/history/{session_id}")
def history(session_id:str):
    with Session(engine) as db:
        rows=db.scalars(select(ChatLog).where(ChatLog.session_id==session_id[:64]).order_by(ChatLog.id.asc()).limit(100)).all()
    return [{"id":r.id,"question":r.question,"answer":r.answer,"source":r.source,"source_url":r.source_url} for r in rows]

@app.post("/api/feedback")
def feedback(req:FeedbackReq):
    if req.value not in ("up","down"):raise HTTPException(400,"Invalid feedback")
    with Session(engine) as db:
        row=db.get(ChatLog,req.chat_id)
        if not row:raise HTTPException(404,"Not found")
        row.feedback=req.value;db.commit()
    return {"ok":True}

@app.post("/api/admin/login")
def login(req:LoginReq):
    if not secrets.compare_digest(req.username,os.getenv("ADMIN_USERNAME","admin")) or not secrets.compare_digest(req.password,os.getenv("ADMIN_PASSWORD","change-me")):
        raise HTTPException(401,"Invalid credentials")
    t=secrets.token_urlsafe(32);TOKENS.add(t);return {"token":t}

@app.post("/api/admin/knowledge/upload")
async def upload_knowledge(file:UploadFile=File(...), source_name:str=Form("Uploaded document"), source_url:str=Form(""), authorization:Optional[str]=Header(default=None)):
    require_admin(authorization)
    raw=await file.read()
    if len(raw)>8_000_000:raise HTTPException(400,"File too large")
    name=(file.filename or "document").lower()
    text=""
    if name.endswith(".pdf"):
        try:
            reader=PdfReader(io.BytesIO(raw))
            text="\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            raise HTTPException(400,f"Could not read PDF: {e}")
    elif name.endswith((".txt",".md")):
        text=raw.decode("utf-8",errors="ignore")
    else:
        raise HTTPException(400,"Use PDF, TXT or MD")
    chunks=chunks_from_text(text)
    if not chunks:raise HTTPException(400,"No readable text found")
    with Session(engine) as db:
        for i,ch in enumerate(chunks):
            db.add(KnowledgeChunk(title=f"{file.filename} · part {i+1}",content=ch,source=source_name,source_url=source_url))
        db.commit()
    return {"ok":True,"chunks_added":len(chunks)}

@app.post("/api/admin/image/preprocess")
async def preprocess_image(file:UploadFile=File(...), authorization:Optional[str]=Header(default=None)):
    require_admin(authorization)
    raw=await file.read()
    arr=np.frombuffer(raw,np.uint8)
    img=cv2.imdecode(arr,cv2.IMREAD_COLOR)
    if img is None:raise HTTPException(400,"Invalid image")
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    gray=cv2.GaussianBlur(gray,(3,3),0)
    proc=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,11)
    ok,buf=cv2.imencode(".png",proc)
    if not ok:raise HTTPException(500,"Processing failed")
    return StreamingResponse(io.BytesIO(buf.tobytes()),media_type="image/png",
        headers={"Content-Disposition":"attachment; filename=preprocessed.png"})

@app.get("/api/admin/stats")
def stats(authorization:Optional[str]=Header(default=None)):
    require_admin(authorization)
    with Session(engine) as db:
        total=db.scalar(select(func.count()).select_from(ChatLog)) or 0
        helpful=db.scalar(select(func.count()).select_from(ChatLog).where(ChatLog.feedback=="up")) or 0
        bad=db.scalar(select(func.count()).select_from(ChatLog).where(ChatLog.feedback=="down")) or 0
        unresolved=db.scalar(select(func.count()).select_from(ChatLog).where(ChatLog.topic=="Unresolved")) or 0
        kcount=db.scalar(select(func.count()).select_from(KnowledgeChunk)) or 0
        topics=db.execute(select(ChatLog.topic,func.count(ChatLog.id)).group_by(ChatLog.topic).order_by(func.count(ChatLog.id).desc())).all()
    return {"total_chats":total,"helpful":helpful,"unhelpful":bad,"unresolved":unresolved,"knowledge_chunks":kcount,
            "topics":[{"name":a,"count":b} for a,b in topics]}

@app.get("/api/admin/chats")
def chats(authorization:Optional[str]=Header(default=None)):
    require_admin(authorization)
    with Session(engine) as db:
        rows=db.scalars(select(ChatLog).order_by(ChatLog.id.desc()).limit(150)).all()
    return [{"id":r.id,"created_at":r.created_at.isoformat() if r.created_at else "","language":r.language,
             "question":r.question,"topic":r.topic,"feedback":r.feedback} for r in rows]

@app.get("/api/admin/export.csv")
def export_csv(authorization:Optional[str]=Header(default=None)):
    require_admin(authorization)
    with Session(engine) as db: rows=db.scalars(select(ChatLog).order_by(ChatLog.id.asc())).all()
    sio=io.StringIO(); w=csv.writer(sio);w.writerow(["id","created_at","language","question","topic","source","feedback"])
    for r in rows:w.writerow([r.id,r.created_at,r.language,r.question,r.topic,r.source,r.feedback])
    return StreamingResponse(io.BytesIO(sio.getvalue().encode("utf-8")),media_type="text/csv",
        headers={"Content-Disposition":"attachment; filename=nyayasathi_chat_logs.csv"})
