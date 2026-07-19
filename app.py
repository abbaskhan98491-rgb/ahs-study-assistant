"""
Medical Study Assistant - Web App (Streamlit)
Two modes: Ask a Question  +  Practice MCQs (Sanrio-styled)
RUN LOCALLY:  streamlit run app.py
"""

import os
import json
import time
import streamlit as st
import fitz
import chromadb
from sentence_transformers import SentenceTransformer
from groq import Groq
from syllabus import SYLLABUS

# ---------------- SOURCES: subject -> Book / Slides file names ----------------
# These must match the exact PDF file names in the books/ folder.
SOURCES = {
    "Physiology": {
        "Book": "Essentials of Medical Physiology (6 Ed)(book).pdf",
        "Slides": "Physiology-Slides.pdf",
    },
    "Biochemistry": {
        "Book": "Satyanarayana-biochemistry-pdf-free.pdf",
        "Slides": "Biochemistry-Slides.pdf",
    },
    "Anatomy": {
        "Book": "Snells-clinical-anatomy-by-regions-10 ed.pdf",
        "Slides": "Anatomy-slides-pdf.pdf",
    },
    "English": {
        "Slides": "English-Slides.pdf",
    },
}


# ---------------- CONFIG ----------------
BOOKS_DIR = "books" if os.path.isdir("books") else "books_small"
DB_DIR = "rag_db"
COLLECTION_NAME = "semester_books"
EMBED_MODEL = "all-MiniLM-L6-v2"
TOP_K = 10
MCQ_CONTEXT_K = 24          # more chunks for making questions
MCQ_TOTAL = 30              # how many questions to make
MCQ_BATCH = 6               # generate this many per API call
GROQ_MODEL = "llama-3.3-70b-versatile"
ZOOM = 2

# ---- PASTE YOUR KEY BELOW (keep the quotes) ----
MY_KEY = "PASTE-YOUR-KEY-HERE"
# ------------------------------------------------

GROQ_API_KEY = ""
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    GROQ_API_KEY = ""
if not GROQ_API_KEY:
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", MY_KEY)


# ---------------- THEME ----------------
SANRIO_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Inter:wght@400;500;600&display=swap');

:root{
  --pink-900:#9d1b5c; --pink-700:#c9256f; --pink-500:#ff6fae;
  --pink-300:#ffb3d4; --pink-100:#ffe4f0; --pink-50:#fff5fa;
  --ink:#3d2436; --muted:#8a6b7c;
  --card:#ffffff; --line:#f6d9e7;
  --shadow:0 1px 2px rgba(157,27,92,.04), 0 8px 24px -12px rgba(157,27,92,.18);
  --shadow-lg:0 2px 4px rgba(157,27,92,.05), 0 20px 40px -20px rgba(157,27,92,.28);
  --r:18px;
}

.stApp{ background:
   radial-gradient(1100px 500px at 12% -8%, #ffe9f4 0%, transparent 60%),
   radial-gradient(900px 460px at 92% 4%, #eaf1ff 0%, transparent 55%),
   linear-gradient(180deg,#fffafc 0%, #fdf4f9 100%);
}
html,body,p,div,span,label,li,input,textarea{
  font-family:'Inter',system-ui,sans-serif !important; color:var(--ink);
  -webkit-font-smoothing:antialiased;
}
h1,h2,h3,h4{ font-family:'Plus Jakarta Sans',sans-serif !important;
  color:var(--pink-900) !important; letter-spacing:-.02em; }

/* hide streamlit chrome */
#MainMenu,footer,header[data-testid="stHeader"]{visibility:hidden; height:0;}
.block-container{ padding-top:1.6rem; padding-bottom:3rem; max-width:1080px; }

/* ---------- HEADER ---------- */
.hero{
  background:linear-gradient(135deg,#ffffff 0%,#fff6fb 100%);
  border:1px solid var(--line); border-radius:26px;
  padding:26px 30px; margin-bottom:22px; box-shadow:var(--shadow-lg);
  position:relative; overflow:hidden;
}
.hero:before{content:"";position:absolute;inset:0 0 auto 0;height:4px;
  background:linear-gradient(90deg,var(--pink-500),#b98bff,#7fb5ff);}
.hero-eyebrow{ font-size:.72rem; font-weight:700; letter-spacing:.14em;
  text-transform:uppercase; color:var(--pink-500); margin-bottom:6px; }
.hero-title{ font-family:'Plus Jakarta Sans',sans-serif; font-weight:800;
  font-size:2.05rem; line-height:1.15; color:var(--pink-900);
  margin:0 0 8px 0; letter-spacing:-.03em; }
.hero-sub{ color:var(--muted); font-size:.95rem; margin:0; }
.hero-chips{ display:flex; gap:8px; flex-wrap:wrap; margin-top:16px; }
.chip{ background:var(--pink-50); border:1px solid var(--line);
  color:var(--pink-700); font-size:.76rem; font-weight:600;
  padding:5px 12px; border-radius:999px; }

/* ---------- CARDS ---------- */
.card{ background:var(--card); border:1px solid var(--line);
  border-radius:var(--r); padding:22px 24px; box-shadow:var(--shadow);
  margin-bottom:16px; }
.card-title{ font-family:'Plus Jakarta Sans',sans-serif; font-weight:700;
  font-size:1.1rem; color:var(--pink-900); margin:0 0 4px 0; }
.card-sub{ color:var(--muted); font-size:.86rem; margin:0 0 14px 0; }

/* ---------- INPUTS ---------- */
.stTextInput input, .stSelectbox div[data-baseweb="select"]>div{
  border-radius:12px !important; border:1px solid var(--line) !important;
  background:#fff !important; font-size:.92rem !important;
}
.stTextInput input:focus{ border-color:var(--pink-300) !important;
  box-shadow:0 0 0 3px rgba(255,111,174,.14) !important; }

/* ---------- BUTTONS ---------- */
.stButton>button{
  background:linear-gradient(135deg,var(--pink-500) 0%,#ff5aa3 100%) !important;
  color:#fff !important; border:none !important; border-radius:12px !important;
  padding:.6rem 1.5rem !important; font-family:'Plus Jakarta Sans',sans-serif !important;
  font-weight:700 !important; font-size:.9rem !important; letter-spacing:.01em;
  box-shadow:0 1px 2px rgba(201,37,111,.2), 0 8px 20px -8px rgba(255,90,163,.5) !important;
  transition:transform .15s ease, box-shadow .15s ease !important;
}
.stButton>button:hover{ transform:translateY(-1px);
  box-shadow:0 2px 4px rgba(201,37,111,.22), 0 14px 28px -10px rgba(255,90,163,.6) !important; }
.stButton>button:active{ transform:translateY(0); }

/* ---------- RADIO (Book / Slides) ---------- */
div[role="radiogroup"]{ gap:8px !important; }
div[role="radiogroup"] label{
  background:#fff; border:1px solid var(--line); border-radius:11px;
  padding:8px 14px !important; font-weight:600; font-size:.86rem;
  transition:all .15s ease; cursor:pointer;
}
div[role="radiogroup"] label:hover{ border-color:var(--pink-300); }

/* ---------- SIDEBAR ---------- */
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#fffdfe 0%,#fff4f9 100%);
  border-right:1px solid var(--line);
}
section[data-testid="stSidebar"] .block-container{ padding-top:1.4rem; }
.side-title{ font-family:'Plus Jakarta Sans',sans-serif; font-weight:800;
  font-size:1.15rem; color:var(--pink-900); margin-bottom:2px; }
.side-note{ color:var(--muted); font-size:.78rem; margin-bottom:16px; }
.side-step{ font-size:.72rem; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; color:var(--pink-500); margin:16px 0 6px; }
.side-card{ background:#fff; border:1px solid var(--line);
  border-radius:14px; padding:14px 16px; margin-top:16px; box-shadow:var(--shadow); }
.side-links{ display:flex; flex-direction:column; gap:2px; margin-top:8px; }
.side-links a{ display:flex; align-items:center; gap:9px; color:var(--pink-700);
  text-decoration:none; font-weight:600; font-size:.83rem; padding:6px 8px;
  border-radius:9px; transition:background .15s ease; }
.side-links a:hover{ background:var(--pink-50); }
.side-links img{ width:17px; height:17px;
  filter:invert(20%) sepia(84%) saturate(2400%) hue-rotate(310deg); }


/* ---------- MCQ ---------- */
.mcq-card{ background:#fff; border:1px solid var(--line); border-left:3px solid var(--pink-300);
  border-radius:14px; padding:16px 20px; margin:0 0 6px 0; box-shadow:var(--shadow); }
.mcq-num{ font-size:.7rem; font-weight:700; letter-spacing:.1em; color:var(--pink-500);
  text-transform:uppercase; }
.mcq-q{ font-family:'Plus Jakarta Sans',sans-serif; font-weight:600;
  color:var(--ink); font-size:1rem; margin-top:3px; line-height:1.45; }
.correct-box{ background:#f0fdf5; border:1px solid #bbf0d0; border-left:3px solid #34c77b;
  border-radius:13px; padding:14px 18px; margin-bottom:10px; font-size:.9rem; }
.wrong-box{ background:#fff5f6; border:1px solid #ffd4da; border-left:3px solid #ff5a76;
  border-radius:13px; padding:14px 18px; margin-bottom:10px; font-size:.9rem; }
.score-badge{ background:linear-gradient(135deg,#fff 0%,#fff6fb 100%);
  border:1px solid var(--line); border-radius:20px; padding:26px;
  text-align:center; box-shadow:var(--shadow-lg); margin-bottom:20px; }
.score-num{ font-family:'Plus Jakarta Sans',sans-serif; font-weight:800;
  font-size:2.6rem; color:var(--pink-700); line-height:1; }
.score-lbl{ color:var(--muted); font-size:.84rem; margin-top:6px;
  letter-spacing:.08em; text-transform:uppercase; font-weight:600; }

/* ---------- FOOTER ---------- */
.foot{ margin-top:34px; padding:22px 26px; background:#fff;
  border:1px solid var(--line); border-radius:20px; box-shadow:var(--shadow);
  display:flex; justify-content:space-between; align-items:center;
  flex-wrap:wrap; gap:14px; }
.foot-name{ font-family:'Plus Jakarta Sans',sans-serif; font-weight:700;
  color:var(--pink-900); font-size:.95rem; }
.foot-role{ color:var(--muted); font-size:.79rem; margin-top:2px; }
.foot-links{ display:flex; gap:6px; flex-wrap:wrap; }
.foot-links a{ display:flex; align-items:center; gap:7px; text-decoration:none;
  background:var(--pink-50); border:1px solid var(--line); color:var(--pink-700);
  font-size:.8rem; font-weight:600; padding:8px 14px; border-radius:10px;
  transition:all .15s ease; }
.foot-links a:hover{ background:#fff; border-color:var(--pink-300);
  transform:translateY(-1px); }
.foot-links img{ width:15px; height:15px;
  filter:invert(20%) sepia(84%) saturate(2400%) hue-rotate(310deg); }


/* wrapper: pin to top-left, above everything */
div[data-testid="stSidebarCollapsedControl"]{
  position:fixed !important; top:12px !important; left:12px !important;
  z-index:2147483647 !important;
  display:flex !important; opacity:1 !important; visibility:visible !important;
  transform:none !important; width:auto !important; height:auto !important;
}
/* the reopen button itself: big pink pill, impossible to miss */
div[data-testid="stSidebarCollapsedControl"] button{
  background:linear-gradient(135deg,#ff6fae 0%,#ff5aa3 100%) !important;
  border:none !important; border-radius:12px !important;
  width:46px !important; height:46px !important;
  box-shadow:0 4px 10px rgba(201,37,111,.28), 0 14px 30px -10px rgba(255,90,163,.65) !important;
  opacity:1 !important; visibility:visible !important;
  display:flex !important; align-items:center !important; justify-content:center !important;
  overflow:hidden !important; font-size:0 !important; cursor:pointer !important;
}
div[data-testid="stSidebarCollapsedControl"] button *{
  visibility:hidden !important; font-size:0 !important; color:transparent !important;
}
div[data-testid="stSidebarCollapsedControl"] button::after{
  content:"" !important; visibility:visible !important;
  display:block !important; width:22px !important; height:22px !important;
  background-repeat:no-repeat !important; background-position:center !important;
  background-size:22px 22px !important;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><rect x='3' y='4' width='18' height='16' rx='2.5'/><line x1='9.5' y1='4' x2='9.5' y2='20'/></svg>") !important;
}

/* the close button inside the sidebar: clean white square with panel icon */
div[data-testid="stSidebarCollapseButton"] button{
  background:#fff !important; border:1px solid #f6d9e7 !important;
  border-radius:10px !important; width:34px !important; height:34px !important;
  box-shadow:0 1px 3px rgba(157,27,92,.12) !important;
  display:flex !important; align-items:center !important; justify-content:center !important;
  overflow:hidden !important; font-size:0 !important;
}
div[data-testid="stSidebarCollapseButton"] button *{
  visibility:hidden !important; font-size:0 !important; color:transparent !important;
}
div[data-testid="stSidebarCollapseButton"] button::after{
  content:"" !important; visibility:visible !important;
  display:block !important; width:18px !important; height:18px !important;
  background-repeat:no-repeat !important; background-position:center !important;
  background-size:18px 18px !important;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23c9256f' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><rect x='3' y='4' width='18' height='16' rx='2.5'/><line x1='9.5' y1='4' x2='9.5' y2='20'/></svg>") !important;
}


/* hide the Deploy text / toolbar so only our button shows */
div[data-testid="stToolbar"], div[data-testid="stDecoration"],
div[data-testid="stStatusWidget"]{ display:none !important; }

/* ===== Sidebar stays open — collapse control removed on purpose ===== */
div[data-testid="stSidebarCollapseButton"],
div[data-testid="stSidebarCollapsedControl"]{ display:none !important; }
header[data-testid="stHeader"]{ visibility:hidden !important; height:0 !important; }
div[data-testid="stToolbar"], div[data-testid="stDecoration"],
div[data-testid="stStatusWidget"], #MainMenu{ display:none !important; }
section[data-testid="stSidebar"]{ min-width:310px !important; }

/* ===== hide the now-empty sidebar completely ===== */
section[data-testid="stSidebar"]{ display:none !important; }
div[data-testid="stSidebarCollapseButton"],
div[data-testid="stSidebarCollapsedControl"]{ display:none !important; }

/* ===== MOBILE ===== */
@media (max-width: 640px){
  .block-container{ padding:.8rem .7rem 2rem !important; max-width:100% !important; }
  .hero{ padding:18px 18px !important; border-radius:20px !important; }
  .hero-title{ font-size:1.4rem !important; line-height:1.2 !important; }
  .hero-sub{ font-size:.85rem !important; }
  .hero-eyebrow{ font-size:.65rem !important; }
  .chip{ font-size:.7rem !important; padding:4px 10px !important; }
  .card{ padding:16px 16px !important; border-radius:15px !important; }
  .card-title{ font-size:1rem !important; }
  .mcq-card{ padding:13px 15px !important; }
  .mcq-q{ font-size:.93rem !important; }
  .score-num{ font-size:2rem !important; }
  .stButton>button{ width:100% !important; padding:.65rem 1rem !important; }
  div[role="radiogroup"]{ flex-wrap:wrap !important; }
  div[role="radiogroup"] label{ font-size:.82rem !important; padding:7px 12px !important; }
  .foot{ flex-direction:column !important; align-items:flex-start !important;
         padding:18px !important; }
  .foot-links{ width:100% !important; }
  .foot-links a{ font-size:.75rem !important; padding:7px 11px !important; }
  div[data-testid="stExpander"] summary{ font-size:.85rem !important;
    padding:12px 14px !important; }
  /* stack the two-column rows on small screens */
  div[data-testid="stHorizontalBlock"]{ flex-direction:column !important; gap:0 !important; }
  div[data-testid="stHorizontalBlock"] > div{ width:100% !important; flex:1 1 100% !important; }
}
@media (max-width: 400px){
  .hero-title{ font-size:1.2rem !important; }
  .chip{ font-size:.65rem !important; }
}

/* hide Streamlit's icon element (renders as raw text when font fails) */
div[data-testid="stExpander"] summary [data-testid="stExpanderToggleIcon"],
div[data-testid="stExpander"] summary span[class*="material"],
div[data-testid="stExpander"] summary i,
div[data-testid="stExpander"] summary svg{
  display:none !important; font-size:0 !important; width:0 !important;
  visibility:hidden !important;
}

/* our own chevron on the right */
div[data-testid="stExpander"] summary::after{
  content:"" !important; flex:0 0 auto !important;
  width:20px !important; height:20px !important;
  background-repeat:no-repeat !important; background-position:center !important;
  background-size:20px 20px !important;
  transition:transform .2s ease !important;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23c9256f' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>") !important;
}
div[data-testid="stExpander"] details[open] > summary::after,
div[data-testid="stExpander"][open] summary::after{ transform:rotate(180deg) !important; }

/* keep the label text tidy */
div[data-testid="stExpander"] summary p,
div[data-testid="stExpander"] summary div{
  margin:0 !important; font-family:'Plus Jakarta Sans',sans-serif !important;
  font-weight:700 !important; color:var(--pink-900) !important;
  overflow:hidden !important; text-overflow:ellipsis !important;
  white-space:nowrap !important;
}

/* extra mobile polish */
@media (max-width: 640px){
  div[data-testid="stExpander"] summary::after{
    width:18px !important; height:18px !important; background-size:18px 18px !important; }
  div[data-testid="stExpander"] summary p{ font-size:.84rem !important; }
  .side-step{ margin:12px 0 5px !important; font-size:.66rem !important; }
  div[data-testid="stExpander"] .stSelectbox,
  div[data-testid="stExpander"] div[role="radiogroup"]{ margin-bottom:2px !important; }
  .stButton>button{ margin-bottom:6px !important; }
  .hero-chips{ gap:6px !important; margin-top:12px !important; }
}

/* bring back ONLY the label text */
div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] *{
  font-size:.95rem !important; line-height:1.4 !important;
  color:var(--pink-900) !important;
  font-family:'Plus Jakarta Sans',sans-serif !important; font-weight:700 !important;
}
/* our chevron must stay visible */
div[data-testid="stExpander"] summary::after{
  font-size:0 !important; color:transparent !important;
}
@media (max-width: 640px){
  div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
  div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] *{
    font-size:.86rem !important; }
}
</style>
"""



# ---------------- DARK MODE OVERRIDES ----------------
DARK_CSS = """
<style>
/* ---- base surface ---- */
.stApp{ background:
   radial-gradient(1100px 500px at 12% -8%, #2a1826 0%, transparent 60%),
   radial-gradient(900px 460px at 92% 4%, #1a2036 0%, transparent 55%),
   linear-gradient(180deg,#17101a 0%, #120c14 100%) !important; }

html,body,p,div,span,label,li,small{ color:#ece0e8 !important; }
h1,h2,h3,h4{ color:#ffd6ea !important; }
.stMarkdown p, .stMarkdown li{ color:#ddd0da !important; }

/* ---- hero ---- */
.hero{ background:linear-gradient(135deg,#251527 0%,#2c1a2c 100%) !important;
       border:1px solid #3d2740 !important; }
.hero-eyebrow{ color:#ff8fc4 !important; }
.hero-title{ color:#ffe0ef !important; }
.hero-sub{ color:#b9a4b4 !important; }
.chip{ background:#33203a !important; border:1px solid #4a2f4c !important;
       color:#ffb3d8 !important; }

/* ---- cards ---- */
.card{ background:#221527 !important; border:1px solid #3d2740 !important; }
.card-title{ color:#ffd6ea !important; }
.card-sub{ color:#b09aab !important; }

.mcq-card{ background:#221527 !important; border:1px solid #3d2740 !important;
           border-left:3px solid #ff6fae !important; }
.mcq-num{ color:#ff8fc4 !important; }
.mcq-q{ color:#f0e4ee !important; }

.score-badge{ background:linear-gradient(135deg,#221527 0%,#2c1a2c 100%) !important;
              border:1px solid #3d2740 !important; }
.score-num{ color:#ffb3d8 !important; }
.score-lbl{ color:#b09aab !important; }

.correct-box{ background:#132a1d !important; border:1px solid #2f6647 !important;
              border-left:3px solid #3ad48a !important; color:#dcf0e4 !important; }
.correct-box b,.correct-box i,.correct-box small{ color:#dcf0e4 !important; }
.wrong-box{ background:#2b1620 !important; border:1px solid #70303f !important;
            border-left:3px solid #ff6b85 !important; color:#f6dde2 !important; }
.wrong-box b,.wrong-box i,.wrong-box small{ color:#f6dde2 !important; }

/* ---- sidebar ---- */
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#1c1220 0%,#221527 100%) !important;
  border-right:1px solid #3d2740 !important; }
.side-title{ color:#ffd6ea !important; }
.side-note{ color:#b09aab !important; }
.side-step{ color:#ff8fc4 !important; }
.side-card{ background:#2a1830 !important; border:1px solid #4a2f4c !important; }
.side-card div{ color:#ece0e8 !important; }

/* ---- links ---- */
.side-links a,.foot-links a{ background:#33203a !important;
  border:1px solid #4a2f4c !important; color:#ffb3d8 !important; }
.side-links a:hover,.foot-links a:hover{ background:#3d2745 !important; }
.side-links img,.foot-links img{
  filter:invert(78%) sepia(35%) saturate(1500%) hue-rotate(292deg) !important; }

/* ---- footer ---- */
.foot{ background:#221527 !important; border:1px solid #3d2740 !important; }
.foot-name{ color:#ffd6ea !important; }
.foot-role{ color:#b09aab !important; }

/* ---- inputs ---- */
.stTextInput input{ background:#2a1830 !important; border:1px solid #4a2f4c !important;
                    color:#f0e4ee !important; }
.stTextInput input::placeholder{ color:#8a7284 !important; }
.stSelectbox div[data-baseweb="select"]>div{
  background:#2a1830 !important; border:1px solid #4a2f4c !important; color:#f0e4ee !important; }
.stSelectbox svg{ fill:#ffb3d8 !important; }
div[data-baseweb="popover"] div,div[data-baseweb="popover"] li{
  background:#2a1830 !important; color:#f0e4ee !important; }
div[data-baseweb="popover"] li:hover{ background:#3d2745 !important; }

div[role="radiogroup"] label{ background:#2a1830 !important;
  border:1px solid #4a2f4c !important; }
div[role="radiogroup"] label p,div[role="radiogroup"] label div{ color:#f0e4ee !important; }

/* alerts */
div[data-testid="stAlert"]{ background:#2a1830 !important;
  border:1px solid #4a2f4c !important; color:#f0e4ee !important; }

/* expander in dark mode */
div[data-testid="stExpander"]{ background:#221527 !important;
  border:1px solid #3d2740 !important; }
div[data-testid="stExpander"] summary{ background:#2a1830 !important;
  color:#ffd6ea !important; }
div[data-testid="stExpander"] summary:hover{ background:#33203a !important; }
div[data-testid="stExpander"] svg{ fill:#ffb3d8 !important; }

div[data-testid="stExpander"] summary::after{
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffb3d8' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>") !important;
}
div[data-testid="stExpander"] summary p{ color:#ffd6ea !important; }

div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] *{
  color:#ffd6ea !important; }

div[data-testid="stSidebarCollapsedControl"] button{
  background:#2a1830 !important; border:1px solid #4a2f4c !important;
  box-shadow:0 2px 4px rgba(0,0,0,.4), 0 12px 28px -12px rgba(0,0,0,.8) !important;
}

div[data-testid="stSidebarCollapseButton"] button::after,
div[data-testid="stSidebarCollapsedControl"] button::after,
button[data-testid="stBaseButton-headerNoPadding"]::after{
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffb3d8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><rect x='3' y='4' width='18' height='16' rx='2.5'/><line x1='9.5' y1='4' x2='9.5' y2='20'/></svg>") !important;
}
</style>
"""

# ---------------- CACHED LOADERS ----------------
@st.cache_resource
def load_model():
    return SentenceTransformer(EMBED_MODEL)


@st.cache_resource
def load_collection():
    client = chromadb.PersistentClient(path=DB_DIR)
    return client.get_collection(COLLECTION_NAME)


@st.cache_data
def get_book_list(_collection):
    sample = _collection.get(limit=20000, include=["metadatas"])
    return sorted({m["book"] for m in sample["metadatas"]})


@st.cache_data
def render_page(book, page):
    path = os.path.join(BOOKS_DIR, book)
    doc = fitz.open(path)
    pix = doc[page - 1].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


# ---------------- CORE: retrieve ----------------
def retrieve(question, selected_book, model, collection, k):
    q_emb = model.encode([question]).tolist()
    args = {"query_embeddings": q_emb, "n_results": k}
    if selected_book != "Both / All books":
        args["where"] = {"book": selected_book}
    results = collection.query(**args)
    return results["documents"][0], results["metadatas"][0]


# ---------------- MODE 1: Q&A ----------------
def answer_question(question, selected_book, model, collection, groq_client):
    chunks, metas = retrieve(question, selected_book, model, collection, TOP_K)
    if not chunks:
        return "No matching text found in that book. Try 'Both'.", []

    context = "\n\n---\n\n".join(
        f"[{m['book']}, page {m['page']}]\n{c}" for c, m in zip(chunks, metas)
    )
    prompt = f"""You are a medical study tutor. Answer the student's question in DETAIL,
using ONLY the context provided below from their textbooks.

Rules:
- Write a full, well-structured explanation, like a textbook or exam answer.
- Use clear headings and bullet points where helpful.
- Define key terms, explain the mechanism step by step, and mention clinical significance if present.
- Cite the book name and page number for the main points.
- If context is not enough, say what is missing. Do NOT invent facts.

CONTEXT:
{context}

QUESTION: {question}

DETAILED ANSWER:"""
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2000,
    )
    answer = response.choices[0].message.content

    diagram_pages, seen = [], set()
    for m in metas:
        if m.get("has_diagram") and (m["book"], m["page"]) not in seen:
            diagram_pages.append((m["book"], m["page"]))
            seen.add((m["book"], m["page"]))
    return answer, diagram_pages


# ---------------- MODE 2: MCQ generation ----------------
def generate_mcq_batch(topic, context, n, avoid_questions, groq_client):
    avoid_txt = ""
    if avoid_questions:
        joined = "\n".join(f"- {q}" for q in avoid_questions[-20:])
        avoid_txt = f"\nDo NOT repeat or rephrase any of these existing questions:\n{joined}\n"

    prompt = f"""You are a medical exam question writer. Using ONLY the textbook context below,
write {n} multiple-choice questions (MCQs) on the topic: "{topic}".

Strict rules:
- Each question has exactly 4 options.
- Exactly ONE option is correct. The other 3 must be plausible but clearly wrong.
- Base every question and answer ONLY on the context. Do not use outside knowledge.
- Add a short explanation and the page number for the correct answer.
{avoid_txt}
Return ONLY valid JSON, no other text. Use this exact format:
[
  {{
    "question": "....",
    "options": ["A ...", "B ...", "C ...", "D ..."],
    "answer_index": 0,
    "explanation": "....",
    "page": "book name, page X"
  }}
]

CONTEXT:
{context}

JSON:"""

    for attempt in range(2):
        try:
            resp = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=3000,
            )
            text = resp.choices[0].message.content.strip()
            # strip code fences if present
            text = text.replace("```json", "").replace("```", "").strip()
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1:
                text = text[start:end + 1]
            data = json.loads(text)
            # keep only well-formed items
            clean = []
            for item in data:
                if (isinstance(item.get("options"), list)
                        and len(item["options"]) == 4
                        and isinstance(item.get("answer_index"), int)
                        and 0 <= item["answer_index"] <= 3
                        and item.get("question")):
                    clean.append(item)
            return clean
        except json.JSONDecodeError:
            continue
        except Exception as e:
            if "rate" in str(e).lower():
                time.sleep(3)
                continue
            raise
    return []


def generate_all_mcqs(topic, selected_book, model, collection, groq_client, progress):
    chunks, metas = retrieve(topic, selected_book, model, collection, MCQ_CONTEXT_K)
    if not chunks:
        return []
    context = "\n\n---\n\n".join(
        f"[{m['book']}, page {m['page']}]\n{c}" for c, m in zip(chunks, metas)
    )

    all_mcqs, avoid = [], []
    while len(all_mcqs) < MCQ_TOTAL:
        need = min(MCQ_BATCH, MCQ_TOTAL - len(all_mcqs))
        batch = generate_mcq_batch(topic, context, need, avoid, groq_client)
        if not batch:
            break  # give up if a batch fails twice
        for q in batch:
            all_mcqs.append(q)
            avoid.append(q["question"])
        progress.progress(min(len(all_mcqs) / MCQ_TOTAL, 1.0),
                          text=f"Made {len(all_mcqs)} of {MCQ_TOTAL} questions...")
        time.sleep(1)  # gentle on the free rate limit
    return all_mcqs[:MCQ_TOTAL]


# ==================== UI ====================
st.set_page_config(page_title="AHS Study Assistant", page_icon="🎀",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(SANRIO_CSS, unsafe_allow_html=True)

# Theme toggle state
if "dark" not in st.session_state:
    st.session_state["dark"] = False

st.markdown(
    """
    <div class="hero">
      <div class="hero-eyebrow">BS Allied Health Sciences</div>
      <div class="hero-title">2nd Semester Study Assistant</div>
      <p class="hero-sub">Ask any topic or generate practice MCQs — answered only from your own books and slides.</p>
      <div class="hero-chips">
        <span class="chip">Physiology</span>
        <span class="chip">Biochemistry</span>
        <span class="chip">Anatomy</span>
        <span class="chip">English</span>
        <span class="chip">Book + Slides</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if GROQ_API_KEY == "PASTE-YOUR-KEY-HERE" or not GROQ_API_KEY:
    st.error("Groq API key missing. Paste it into MY_KEY at the top of app.py.")
    st.stop()

try:
    model = load_model()
    collection = load_collection()
    groq_client = Groq(api_key=GROQ_API_KEY)
    books = get_book_list(collection)
except Exception as e:
    st.error(f"Setup problem: {e}")
    st.stop()

# ---------------- STUDY PANEL (plain button toggle — works everywhere) ----------------
if "panel_open" not in st.session_state:
    st.session_state["panel_open"] = True

btn_label = "Hide Study Panel" if st.session_state["panel_open"] else "Show Study Panel"
if st.button(btn_label, key="panel_toggle", use_container_width=True):
    st.session_state["panel_open"] = not st.session_state["panel_open"]
    st.rerun()

# Values must exist even when the panel is hidden
if "sel_subject" not in st.session_state:
    st.session_state["sel_subject"] = list(SOURCES.keys())[0]

if st.session_state["panel_open"]:
    st.markdown('<div class="card">', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="side-step">Subject</div>', unsafe_allow_html=True)
        subject = st.selectbox("Subject", list(SOURCES.keys()),
                               key="sel_subject", label_visibility="collapsed")
    with col2:
        source_options = list(SOURCES[subject].keys())
        st.markdown('<div class="side-step">Study from</div>', unsafe_allow_html=True)
        source_type = st.radio("Source", source_options, key="sel_source",
                               label_visibility="collapsed", horizontal=True)

    picked_topic = ""
    if subject in SYLLABUS:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="side-step">Chapter</div>', unsafe_allow_html=True)
            chapter = st.selectbox("Chapter", list(SYLLABUS[subject].keys()),
                                   key="sel_chapter", label_visibility="collapsed")
        with c2:
            st.markdown('<div class="side-step">Topic</div>', unsafe_allow_html=True)
            picked_topic = st.selectbox("Topic", SYLLABUS[subject][chapter],
                                        key="sel_topic", label_visibility="collapsed")
    st.session_state["picked_topic"] = picked_topic

    st.markdown('<div class="side-step">Mode</div>', unsafe_allow_html=True)
    m1, m2 = st.columns(2)
    with m1:
        if st.button("Topic Study", key="mode_study", use_container_width=True):
            st.session_state["mode"] = "study"
    with m2:
        if st.button("MCQs Test", key="mode_mcq", use_container_width=True):
            st.session_state["mode"] = "mcq"

    dark_on = st.toggle("Dark mode", value=st.session_state.get("dark", False),
                        key="dark_toggle")
    if dark_on != st.session_state.get("dark", False):
        st.session_state["dark"] = dark_on
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
else:
    subject = st.session_state["sel_subject"]
    source_type = st.session_state.get("sel_source",
                                       list(SOURCES[subject].keys())[0])
    if source_type not in SOURCES[subject]:
        source_type = list(SOURCES[subject].keys())[0]

if "mode" not in st.session_state:
    st.session_state["mode"] = "study"

book_choice = SOURCES[subject][source_type]

if st.session_state.get("dark", False):
    st.markdown(DARK_CSS, unsafe_allow_html=True)

# ---- MODE 1: STUDY ----
if st.session_state.get("mode", "study") == "study":
    st.markdown('<div class="card"><div class="card-title">Topic Study</div>'
                f'<div class="card-sub">Source: {subject} &middot; {source_type}</div></div>',
                unsafe_allow_html=True)
    default_q = st.session_state.get("picked_topic", "")
    question = st.text_input("Your question:",
                             value=(f"Explain {default_q}" if default_q else ""),
                             placeholder="e.g. Explain the citric acid cycle")
    if st.button("Get Answer", key="ask_btn") and question.strip():
        with st.spinner("Reading your books..."):
            answer, diagram_pages = answer_question(
                question, book_choice, model, collection, groq_client)
        st.markdown("#### Answer")
        st.markdown(answer)
        if diagram_pages:
            st.markdown("#### Diagrams from your source")
            cols = st.columns(2)
            for i, (bk, pg) in enumerate(diagram_pages[:6]):
                try:
                    with cols[i % 2]:
                        st.image(render_page(bk, pg), caption=f"{bk} — page {pg}",
                                 use_container_width=True)
                except Exception:
                    st.write(f"(Could not render {bk} page {pg})")

# ---- MODE 2: MCQ ----
if st.session_state.get("mode", "study") == "mcq":
    st.markdown('<div class="card"><div class="card-title">MCQs Test</div>'
                f'<div class="card-sub">30 practice questions &middot; {subject} &middot; {source_type}</div></div>',
                unsafe_allow_html=True)
    default_t = st.session_state.get("picked_topic", "")
    topic = st.text_input("Topic:", value=default_t,
                          placeholder="e.g. Hemoglobin, Glycolysis, Nerve conduction",
                          key="mcq_topic")

    if st.button("Generate 30 MCQs", key="mcq_btn") and topic.strip():
        progress = st.progress(0.0, text="Starting...")
        try:
            mcqs = generate_all_mcqs(topic, book_choice, model, collection, groq_client, progress)
        except Exception as e:
            st.error(f"Problem generating MCQs: {e}")
            mcqs = []
        progress.empty()
        if not mcqs:
            st.warning("Could not make questions (topic may be thin in the books, or rate limit hit). Try a clearer topic or wait a minute.")
        else:
            st.session_state["mcqs"] = mcqs
            st.session_state["submitted"] = False
            st.success(f"{len(mcqs)} questions ready — answer them below.")

    # Show the quiz if we have questions
    if "mcqs" in st.session_state and st.session_state["mcqs"]:
        mcqs = st.session_state["mcqs"]
        st.markdown("---")
        for i, q in enumerate(mcqs):
            st.markdown(f'<div class="mcq-card"><div class="mcq-num">Question {i+1}</div>'
                        f'<div class="mcq-q">{q["question"]}</div></div>',
                        unsafe_allow_html=True)
            st.radio("Choose:", q["options"], key=f"ans_{i}", index=None,
                     label_visibility="collapsed")

        if st.button("Submit & See Score", key="submit_btn"):
            st.session_state["submitted"] = True

        if st.session_state.get("submitted"):
            score = 0
            for i, q in enumerate(mcqs):
                chosen = st.session_state.get(f"ans_{i}")
                correct = q["options"][q["answer_index"]]
                if chosen == correct:
                    score += 1
            pct = round(score / len(mcqs) * 100)
            st.markdown(
                f'<div class="score-badge"><div class="score-num">{score}<span style="font-size:1.4rem;color:#8a6b7c;">/{len(mcqs)}</span></div>'
                f'<div class="score-lbl">{pct}% correct</div></div>',
                unsafe_allow_html=True)
            st.markdown("#### Review")
            for i, q in enumerate(mcqs):
                chosen = st.session_state.get(f"ans_{i}")
                correct = q["options"][q["answer_index"]]
                right = (chosen == correct)
                box = "correct-box" if right else "wrong-box"
                mark = "✅ Correct" if right else "❌ Wrong"
                your_ans = chosen if chosen else "(not answered)"
                st.markdown(
                    f'<div class="{box}"><b>Q{i+1}. {q["question"]}</b><br>'
                    f'{mark}<br>Your answer: {your_ans}<br>'
                    f'Correct answer: {correct}<br>'
                    f'<i>{q.get("explanation","")}</i><br>'
                    f'<small>📖 {q.get("page","")}</small></div>',
                    unsafe_allow_html=True)


# ---------------- FOOTER ----------------
st.markdown(
    """
    <div class="foot">
      <div>
        <div class="foot-name">Created by Abbas Khan</div>
        <div class="foot-role">BS Allied Health Sciences &middot; 2nd Semester</div>
      </div>
      <div class="foot-links">
        <a href="tel:+923459059934">
          <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/whatsapp.svg">0345-9059934</a>
        <a href="mailto:abbaskhan98491@gmail.com">
          <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/gmail.svg">Email</a>
        <a href="https://www.tiktok.com/@abbas_khan455" target="_blank">
          <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/tiktok.svg">TikTok</a>
        <a href="https://www.instagram.com/dentistabbaskhan" target="_blank">
          <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/instagram.svg">Instagram</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)