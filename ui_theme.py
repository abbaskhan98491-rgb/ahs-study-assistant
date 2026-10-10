"""Readable, locally rendered themes for the study workspace.

The light stylesheet owns structure; the dark stylesheet overrides the same
tokens, so theme changes keep controls, spacing, and keyboard behavior intact.
"""

LIGHT_CSS = """
<style>
:root {
  --pink-900: #9d1b5c;
  --pink-700: #c9256f;
  --pink-500: #ff6fae;
  --pink-300: #ffb3d4;
  --pink-100: #ffe4f0;
  --pink-50: #fff5fa;
  --page: #fff5fa;
  --page-gradient: linear-gradient(180deg, #fffafc 0%, #fff5fa 100%);
  --surface: #ffffff;
  --surface-soft: #fff5fa;
  --ink: #3d2436;
  --muted: #806174;
  --line: #f6d9e7;
  --accent: #c9256f;
  --accent-hover: #9d1b5c;
  --accent-soft: #ffe4f0;
  --accent-line: #ffb3d4;
  --button-start: #ff6fae;
  --button-end: #ff5aa3;
  --on-accent: #ffffff;
  --focus: #9638a5;
  --success-bg: #edf7f0;
  --success-ink: #205536;
  --success-line: #9dc8ac;
  --error-bg: #fcf0f0;
  --error-ink: #873535;
  --error-line: #e1b0b0;
  --r: 14px;
  --body-font: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  --display-font: "Segoe UI Variable Display", "Trebuchet MS", "Segoe UI", sans-serif;
}

html, body, .stApp {
  background: var(--page);
  color: var(--ink);
  font-family: var(--body-font);
  font-size: 16px;
  -webkit-font-smoothing: antialiased;
}
.stApp { background-image: var(--page-gradient); background-attachment: fixed; }
.block-container {
  max-width: 1200px;
  padding: 2.2rem 2rem 2.5rem;
}
/* The app masthead replaces Streamlit's floating chrome so it cannot cover it. */
header[data-testid="stHeader"] { height: 0; visibility: hidden; }
div[data-testid="stDecoration"] { display: none; }
div[data-testid="stVerticalBlock"] { gap: 1rem; }
div[data-testid="stMarkdownContainer"] {
  color: var(--ink);
  font-family: var(--body-font);
}
div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li {
  font-size: 1rem;
  line-height: 1.65;
}
h1, h2, h3, h4, h5, h6 {
  color: var(--ink);
  font-family: var(--display-font);
  letter-spacing: -.025em;
  line-height: 1.25;
}
div[data-testid="stCaptionContainer"] {
  color: var(--muted);
  font-size: .9rem;
  line-height: 1.5;
}
div[data-testid="stCaptionContainer"] p { color: var(--muted); }
a { color: var(--accent); text-underline-offset: 3px; }
hr { border-color: var(--line); }

/* A compact masthead leaves the syllabus and current task in view. */
.hero {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: 0 3px 14px -8px rgba(157, 27, 92, .2);
  padding: 1.2rem 1.4rem;
  margin-bottom: .4rem;
}
.hero-eyebrow {
  color: var(--accent);
  font-size: .8rem;
  font-weight: 700;
  letter-spacing: .075em;
  text-transform: uppercase;
  margin-bottom: .45rem;
}
.hero-title {
  color: var(--accent-hover);
  font-family: var(--display-font);
  font-size: clamp(1.55rem, 3.3vw, 2.1rem);
  font-weight: 750;
  letter-spacing: -.045em;
  line-height: 1.15;
  margin: 0 0 .5rem;
}
.hero-sub { color: var(--muted); font-size: 1rem; line-height: 1.5; margin: 0; }
.hero-chips { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: .85rem; }
.chip {
  border: 1px solid var(--line);
  border-radius: 7px;
  color: var(--muted);
  font-size: .82rem;
  padding: .3rem .65rem;
}

/* White paper surfaces, with pink reserved for selection and action. */
.card, .side-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 1.3rem 1.5rem;
  box-shadow: 0 3px 14px -9px rgba(157, 27, 92, .2);
}
.card-title, .workspace-heading {
  color: var(--ink);
  font-family: var(--display-font);
  font-size: 1.4rem;
  font-weight: 750;
  letter-spacing: -.025em;
  line-height: 1.3;
  margin: 0 0 .35rem;
}
.card-sub { color: var(--muted); font-size: .94rem; line-height: 1.5; margin: 0; }
.panel-head, .side-title {
  font-family: var(--display-font);
  font-weight: 750;
  color: var(--ink);
  font-size: 1.1rem;
  margin-bottom: .4rem;
}
.side-note { color: var(--muted); font-size: .9rem; line-height: 1.5; }
.side-step {
  color: var(--muted);
  font-size: .85rem;
  font-weight: 650;
  margin: .6rem 0 .35rem;
}
div[data-testid="stColumn"]:has(.panel-head),
div[data-testid="column"]:has(.panel-head) {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 1.3rem;
}
section[data-testid="stSidebar"] {
  background: var(--surface);
  border-right: 1px solid var(--line);
}
.side-links { display: flex; flex-direction: column; gap: .3rem; }
.side-links a {
  display: flex;
  align-items: center;
  gap: .5rem;
  color: var(--accent);
  font-size: .9rem;
  padding: .65rem .4rem;
}
.side-links img { width: 18px; height: 18px; }
.topic-trail {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .4rem;
  color: var(--accent);
  background: var(--accent-soft);
  border-radius: 8px;
  padding: .7rem .9rem;
  font-size: .9rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

/* Keep Streamlit's native fields, icons, and accessible radio semantics. */
div[data-testid="stWidgetLabel"] p,
div[data-testid="stWidgetLabel"] label {
  color: var(--ink);
  font-family: var(--body-font);
  font-size: .95rem;
  font-weight: 600;
  line-height: 1.5;
}
.stTextInput input, .stTextArea textarea, .stNumberInput input {
  color: var(--ink) !important;
  background: var(--surface) !important;
  font-family: var(--body-font) !important;
  font-size: 1rem !important;
  min-height: 46px;
}
.stTextInput div[data-baseweb="input"],
.stTextArea div[data-baseweb="textarea"],
.stNumberInput div[data-baseweb="input"] {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 10px;
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder { color: var(--muted); opacity: 1; }
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div {
  background: var(--surface) !important;
  border-color: var(--line) !important;
  border-radius: 10px !important;
  color: var(--ink) !important;
  font-family: var(--body-font);
  font-size: 1rem;
  min-height: 46px;
}
.stSelectbox div[data-baseweb="select"] svg { color: var(--muted); }
div[data-baseweb="popover"] [role="listbox"],
div[data-baseweb="popover"] [role="option"] {
  background: var(--surface);
  color: var(--ink);
  font-family: var(--body-font);
  font-size: 1rem;
}
div[data-baseweb="popover"] [role="option"][aria-selected="true"],
div[data-baseweb="popover"] [role="option"]:hover { background: var(--accent-soft); }
div[role="radiogroup"] { gap: .55rem !important; flex-wrap: wrap; }
div[role="radiogroup"] label {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 10px;
  color: var(--ink);
  min-height: 46px;
  padding: .65rem .9rem !important;
  cursor: pointer;
  transition: border-color .12s ease, background-color .12s ease;
}
div[role="radiogroup"] label p { color: var(--ink); font-size: 1rem !important; line-height: 1.45; }
div[role="radiogroup"] label:hover { border-color: var(--accent-line); background: var(--accent-soft); }
div[role="radiogroup"] label:has(input:checked) {
  background: var(--accent-soft);
  border-color: var(--accent);
}
div[role="radiogroup"] label:focus-within { outline: 3px solid var(--focus); outline-offset: 3px; }
div[class*="st-key-quiz_question_"] div[role="radiogroup"] {
  display: grid !important;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .55rem !important;
}
div[class*="st-key-quiz_question_"] div[role="radiogroup"] label {
  width: 100%;
  box-sizing: border-box;
  padding: .55rem .8rem !important;
}
.stCheckbox label, .stToggle label { color: var(--ink); min-height: 44px; }
.stCheckbox label p, .stToggle label p { color: var(--ink); font-size: .95rem !important; }

.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  border: 1px solid transparent !important;
  border-radius: 12px !important;
  background: linear-gradient(135deg, var(--button-start), var(--button-end)) !important;
  color: var(--on-accent) !important;
  font-family: var(--body-font) !important;
  font-weight: 650 !important;
  font-size: 1rem !important;
  min-height: 46px;
  padding: .65rem 1rem !important;
  box-shadow: 0 4px 14px -8px rgba(201, 37, 111, .35) !important;
  transition: border-color .12s ease, background-color .12s ease;
}
.stButton > button p, .stDownloadButton > button p, .stFormSubmitButton > button p {
  color: inherit;
  font-size: 1rem !important;
  font-weight: 650;
  text-shadow: 0 1px 2px rgba(157, 27, 92, .25);
}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
  border-color: transparent !important;
  background: linear-gradient(135deg, var(--button-end), var(--button-start)) !important;
  color: var(--on-accent) !important;
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  border-color: transparent !important;
  background: linear-gradient(135deg, var(--button-start), var(--button-end)) !important;
  color: var(--on-accent) !important;
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
  border-color: transparent !important;
  background: linear-gradient(135deg, var(--button-end), var(--button-start)) !important;
  color: var(--on-accent) !important;
}
.stButton > button:disabled, .stDownloadButton > button:disabled, .stFormSubmitButton > button:disabled {
  opacity: .5;
  cursor: not-allowed;
}
button:focus-visible, a:focus-visible, input:focus-visible,
textarea:focus-visible, summary:focus-visible,
div[role="tab"]:focus-visible {
  outline: 3px solid var(--focus) !important;
  outline-offset: 3px;
}
div[data-baseweb="select"]:focus-within,
.stTextInput div[data-baseweb="input"]:focus-within,
.stTextArea div[data-baseweb="textarea"]:focus-within { border-color: var(--focus) !important; }

div[data-testid="stExpander"] details {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 12px;
}
div[data-testid="stExpander"] summary {
  min-height: 48px;
  color: var(--ink);
  padding: .8rem 1rem;
}
div[data-testid="stExpander"] summary p { font-size: .95rem; font-weight: 600; }
div[data-testid="stExpander"] summary:hover { background: var(--surface-soft); }
div[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid var(--line); gap: 1.5rem; }
div[data-testid="stTabs"] [role="tab"] { color: var(--muted); font-weight: 650; min-height: 46px; }
div[data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: var(--accent); }
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background: var(--accent); }

/* Question numbers are the visual anchor; answers retain their full row. */
.quiz-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: .7rem;
  color: var(--muted);
  font-size: .92rem;
  line-height: 1.5;
  padding: .25rem 0 .6rem;
}
.quiz-toolbar strong { color: var(--ink); font-weight: 700; }
.quiz-card, div[class*="st-key-quiz_question_"] {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 1rem 1.25rem;
}
.mcq-card {
  border-left: 3px solid var(--accent-line);
  padding: .15rem 0 .15rem .9rem;
  margin-bottom: .6rem;
}
.mcq-num {
  color: var(--accent);
  font-size: .82rem;
  font-weight: 700;
  line-height: 1.4;
  margin-bottom: .35rem;
}
.mcq-q {
  color: var(--ink);
  font-family: var(--body-font);
  font-size: 1.1rem;
  font-weight: 650;
  line-height: 1.55;
  overflow-wrap: anywhere;
}
.correct-box, .wrong-box {
  border: 1px solid;
  border-radius: 10px;
  padding: .85rem 1rem;
  margin-top: .6rem;
  font-size: 1rem;
  line-height: 1.6;
}
.correct-box { background: var(--success-bg); border-color: var(--success-line); color: var(--success-ink); }
.wrong-box { background: var(--error-bg); border-color: var(--error-line); color: var(--error-ink); }
.score-badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: .6rem;
  border: 1px solid var(--accent-line);
  background: var(--accent-soft);
  border-radius: var(--r);
  padding: 1.6rem;
  margin-bottom: 1rem;
}
.score-num {
  color: var(--accent);
  font-family: var(--display-font);
  font-size: 2.8rem;
  font-weight: 750;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.score-lbl { color: var(--muted); font-size: .95rem; text-align: center; }
.empty-state {
  border: 1px dashed var(--accent-line);
  background: var(--surface);
  border-radius: var(--r);
  padding: 2rem;
  margin-top: .75rem;
  color: var(--muted);
  font-size: 1rem;
  line-height: 1.65;
}
.empty-state strong {
  display: block;
  color: var(--ink);
  font-family: var(--display-font);
  font-size: 1.2rem;
  margin-bottom: .4rem;
}

.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  border-top: 1px solid var(--line);
  margin-top: 2rem;
  padding: 1.3rem 0 0;
}
.foot-name { color: var(--ink); font-weight: 650; font-size: .9rem; }
.foot-role { color: var(--muted); font-size: .85rem; margin-top: .2rem; }
.foot-links { display: flex; align-items: center; flex-wrap: wrap; gap: .4rem; }
.foot-links a {
  display: flex;
  align-items: center;
  gap: .4rem;
  color: var(--accent);
  font-size: .85rem;
  padding: .65rem .7rem;
  border-radius: 8px;
  text-decoration: none;
}
.foot-links a:hover { background: var(--accent-soft); text-decoration: underline; }
.foot-links img { width: 16px; height: 16px; }

/* The initial desktop screen is a compact desk, while generated output keeps
   the roomy reading layout above. All controls remain visible and in flow. */
div[data-testid="stElementContainer"]:has(> div[data-testid="stMarkdown"] .landing-layout:empty),
div[data-testid="stElementContainer"]:has(> div[data-testid="stMarkdown"] .results-layout:empty) {
  display: none;
}
@media (min-width: 900px) {
  .block-container:has(.landing-layout),
  .stMainBlockContainer:has(.landing-layout) {
    padding-top: .8rem;
    padding-bottom: .8rem;
  }
  .block-container:has(.landing-layout) div[data-testid="stVerticalBlock"] {
    gap: .45rem;
  }
  .block-container:has(.landing-layout) .hero {
    padding: .8rem 1rem;
    margin-bottom: 0;
  }
  .block-container:has(.landing-layout) .hero-eyebrow {
    font-size: .75rem;
    line-height: 1.25;
    margin-bottom: .2rem;
  }
  .block-container:has(.landing-layout) .hero-title {
    font-size: 1.7rem;
    line-height: 1.15;
    margin-bottom: .25rem;
  }
  .block-container:has(.landing-layout) .hero-sub {
    font-size: 1rem;
    line-height: 1.4;
  }
  .block-container:has(.landing-layout) .hero-chips { margin-top: .4rem; }
  .block-container:has(.landing-layout) .card,
  .block-container:has(.landing-layout) .side-card {
    padding: .8rem 1rem;
  }
  .block-container:has(.landing-layout) div[data-testid="stWidgetLabel"] {
    margin-bottom: .2rem;
  }
  .block-container:has(.landing-layout) div[data-testid="stWidgetLabel"] p {
    font-size: 1rem;
    line-height: 1.4;
    margin-bottom: 0;
  }
  .block-container:has(.landing-layout) .stSelectbox div[data-baseweb="select"] > div,
  .block-container:has(.landing-layout) .stTextInput input,
  .block-container:has(.landing-layout) .stNumberInput input {
    min-height: 44px;
  }
  .block-container:has(.landing-layout) div[role="radiogroup"] label {
    min-height: 44px;
    padding: .55rem .8rem !important;
  }
  .block-container:has(.landing-layout) .stCheckbox label,
  .block-container:has(.landing-layout) .stToggle label { min-height: 44px; }
  .block-container:has(.landing-layout) .stButton > button {
    min-height: 44px;
    padding: .55rem 1rem !important;
  }
  .block-container:has(.landing-layout) div[data-testid="stExpander"] summary {
    min-height: 44px;
    padding: .55rem .8rem;
  }
  .block-container:has(.landing-layout) div[data-testid="stCaptionContainer"] p {
    margin-bottom: 0;
    line-height: 1.4;
  }
  .block-container:has(.landing-layout) .st-key-setup_controls {
    margin-top: 0;
    margin-bottom: 0;
  }
  .block-container:has(.landing-layout) div[class*="st-key-setup_row_"] {
    margin-top: 0;
    margin-bottom: 0;
  }
  .block-container:has(.landing-layout) .foot {
    margin-top: .45rem;
    padding-top: .45rem;
    gap: .5rem;
  }
  .block-container:has(.landing-layout) .foot-links a {
    min-height: 44px;
    padding: .45rem .6rem;
  }
}

@media (max-width: 760px) {
  .block-container { padding: 1.4rem 1rem 2rem; }
  .hero { padding-bottom: 1.1rem; }
  .hero-title { font-size: 1.6rem; }
  .card, .quiz-card, div[class*="st-key-quiz_question_"] { padding: 1.1rem; }
  .empty-state { padding: 1.4rem; }
  .topic-trail { font-size: .86rem; }
  div[class*="st-key-quiz_question_"] div[role="radiogroup"] {
    grid-template-columns: minmax(0, 1fr);
  }
  div[data-testid="stHorizontalBlock"]:has(.panel-head) { flex-wrap: wrap; gap: 1.25rem; }
  div[data-testid="stHorizontalBlock"]:has(.panel-head) > div[data-testid="stColumn"],
  div[data-testid="stHorizontalBlock"]:has(.panel-head) > div[data-testid="column"] {
    width: 100% !important;
    flex: 1 1 100% !important;
    min-width: 0 !important;
  }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
    scroll-behavior: auto !important;
  }
}
</style>
"""

DARK_CSS = """
<style>
:root {
  color-scheme: dark;
  --page: #1b171c;
  --page-gradient: linear-gradient(180deg, #221822 0%, #1b171c 100%);
  --surface: #252028;
  --surface-soft: #302a33;
  --ink: #f3eaf0;
  --muted: #c0adb9;
  --line: #51414c;
  --accent: #f098bd;
  --accent-hover: #f7b2cd;
  --accent-soft: #3a2531;
  --accent-line: #80506a;
  --button-start: #b33170;
  --button-end: #8d2459;
  --on-accent: #ffffff;
  --focus: #cfabff;
  --success-bg: #20382b;
  --success-ink: #b7e3c4;
  --success-line: #4d7c5d;
  --error-bg: #40252a;
  --error-ink: #f0c0c7;
  --error-line: #965863;
}
div[data-testid="stAlert"] {
  color: var(--ink);
  border-radius: 10px;
}
div[data-testid="stAlert"] p { color: inherit; }
div[data-testid="stProgress"] > div > div > div > div { background-color: var(--accent); }
div[data-testid="stMetricValue"], div[data-testid="stMetricLabel"] { color: var(--ink); }
</style>
"""
