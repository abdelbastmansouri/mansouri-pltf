import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import io
import time
import re  
import hashlib 
from pypdf import PdfReader

# --- 1. الإعدادات الأولية وإضفاء الطابع الاحترافي للوزارة ---
st.set_page_config(
    page_title="منصة ذ عبد الباسط منصوري", 
    layout="wide",
    page_icon="math🇲🇦"
)

def get_custom_bg():
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Amiri:ital,wght@0,400;0,700;1,400;1,700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-image: linear-gradient(to bottom, rgba(245, 247, 250, 0.94) 0%, rgba(240, 244, 248, 0.88) 100%), 
        url("https://drive.google.com/thumbnail?id=1qtyRtJXUvwJe8qd8HrkC_P7phD6MBiXe&sz=w1920") !important;
        background-size: cover !important;
        background-repeat: no-repeat !important;
        background-attachment: fixed !important;
    }
    
    * { font-family: 'Amiri', serif !important; }
    
    [data-testid="stHeader"] {
        background-color: rgba(255, 255, 255, 1) !important;
        background: white !important;
        border-bottom: 1px solid rgba(197, 160, 89, 0.3) !important;
    }
    
    .golden-title {
        color: #FFD700 !important;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.7) !important;
        font-weight: bold !important;
        text-align: center;
    }
    
    .golden-sub {
        color: #F1C40F !important;
        text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.6) !important;
        text-align: center;
        font-size: 1.3rem !important;
    }
    
    .section-title {
        color: #C5A059 !important;
        font-weight: bold !important;
        font-size: 1.6rem !important;
        border-bottom: 2px solid #C5A059;
        padding-bottom: 5px;
        margin-bottom: 15px;
    }
    
    [data-testid="stSidebar"] { background-color: rgba(26, 54, 93, 0.98) !important; }
    [data-testid="stSidebar"] * { color: white !important; }
    
    .stSelectbox, .stTextInput, .metric-card, .stTextArea, div[data-testid="stExpander"], .stDateInput {
        background-color: rgba(255, 255, 255, 0.95) !important;
        backdrop-filter: blur(8px) !important;
        border-radius: 12px !important;
        border: 1px solid rgba(197, 160, 89, 0.4) !important;
    }

    h1, h2, h3, label, .stMarkdown p { 
        color: #ED7F10 !important; 
        font-weight: bold !important; 
    }
    
    .stButton>button {
        background-color: #1a365d !important; 
        color: #FFD700 !important;
        border-radius: 8px !important; 
        border: 1px solid #C5A059 !important;
        padding: 10px 24px !important;
        font-size: 1.2rem !important;
    }
    .stButton>button:hover {
        background-color: #C5A059 !important; 
        color: #1a365d !important;
    }
    
    .status-box {
        background-color: #ffffff !important;
        color: #1e293b !important;
        border-right: 6px solid #10b981;
        padding: 16px;
        border-radius: 10px;
        margin-bottom: 20px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        font-size: 1.15rem;
    }
    </style>
    """

st.markdown(get_custom_bg(), unsafe_allow_html=True)

def get_all_api_keys():
    keys = []
    if "GEMINI_API_KEYS" in st.secrets:
        keys.extend([str(k).strip() for k in st.secrets["GEMINI_API_KEYS"] if str(k).strip()])
    if "GEMINI_API_KEY" in st.secrets:
        single_k = str(st.secrets["GEMINI_API_KEY"]).strip()
        if single_k and single_k not in keys:
            keys.append(single_k)
    return keys

if not get_all_api_keys():
    st.error("⚠️ لم يتم العثور على أي مفتاح API في Secrets (GEMINI_API_KEYS أو GEMINI_API_KEY).")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = {}
if 'role' not in st.session_state: st.session_state.role = None

def get_gcp_credentials():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    
def get_gspread_client():
    return gspread.authorize(get_gcp_credentials())

def detect_level_from_class(class_name, explicit_level=""):
    c_up = str(class_name).strip().upper()
    exp = str(explicit_level).strip()
    if exp and exp not in ["", "None", "nan"]:
        return exp
    if "1BAC" in c_up or "1 BAC" in c_up or "أولى" in c_up:
        return "أولى باكالوريا علوم (1 باك SEF)"
    return "جذع مشترك علوم"

def extract_file_id_from_drive_link(link):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', link)
    if match:
        return match.group(1)
    match_id = re.search(r'id=([a-zA-Z0-9_-]+)', link)
    if match_id:
        return match_id.group(1)
    return None

@st.cache_data(ttl=3600)
def extract_text_from_drive_pdf(drive_link):
    file_id = extract_file_id_from_drive_link(drive_link)
    if not file_id:
        return ""
    try:
        creds = get_gcp_credentials()
        drive_service = build('drive', 'v3', credentials=creds)
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        
        reader = PdfReader(fh)
        extracted_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
        return extracted_text.strip()
    except Exception as e:
        print(f"Error reading PDF from Drive: {e}")
        return ""

def calculate_image_hash(file_bytes):
    return hashlib.md5(file_bytes).hexdigest()

def optimize_image_for_api(uploaded_file):
    try:
        img = Image.open(uploaded_file)
        max_size = 1300
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=82)
        buffer.seek(0)
        return Image.open(buffer)
    except:
        return Image.open(uploaded_file)

def extract_percentage_from_report(report_str):
    text = str(report_str)
    match_pct = re.search(r"النسبة\s+النهائية[\s\*]*:[\s\*]*(\d+(?:[\.,]\d+)?)\s*%?", text)
    if match_pct:
        clean_num = match_pct.group(1).replace(",", ".")
        return f"{clean_num}%"
    
    all_pcts = re.findall(r"(\d+(?:[\.,]\d+)?)\s*%", text)
    if all_pcts:
        clean_num = all_pcts[-1].replace(",", ".")
        return f"{clean_num}%"
        
    return "0%"

def is_cheating_row(row):
    rep = str(row.get('التقرير', ''))
    col_h = str(row.get('بصمة_الخط', '')).strip()
    pct = extract_percentage_from_report(rep) if rep else col_h
    if pct == "0%" or col_h == "0%" or "حالة غش" in rep or "عدم تطابق الهوية" in rep:
        return True
    return False

def normalize_reports_df(df):
    df.columns = df.columns.str.strip()
    for col in df.columns:
        if col in ["إسم", "اسم", "اسم التلميذ", "إسم التلميذ"]:
            df = df.rename(columns={col: "الاسم"})
        elif col.startswith("الدرس"):
            df = df.rename(columns={col: "الدرس"})
        elif col in ["بصمة_الصور", "بصمات الصور", "بصمة الصور"]:
            df = df.rename(columns={col: "بصمات_الصور"})
    return df

@st.cache_data(ttl=2)
def load_data():
    sh = None
    for attempt in range(4):
        try:
            client = get_gspread_client()
            sh = client.open("les classes")
            break
        except:
            if attempt == 3: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
            time.sleep(3)
            
    if sh is None: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    try:
        data_rows = sh.sheet1.get_all_values()
        if data_rows and len(data_rows) > 1:
            headers = [h.strip() for h in data_rows[0]]
            df_students = pd.DataFrame(data_rows[1:], columns=headers)
            df_students.columns = df_students.columns.str.strip()
            if "إسم التلميذ" in df_students.columns: df_students = df_students.rename(columns={"إسم التلميذ": "اسم التلميذ"})
        else:
            df_students = pd.DataFrame(columns=["رقم التلميذ", "الرقم التسلسلي", "اسم التلميذ", "تاريخ الإزدياد", "القسم", "المستوى"])
    except:
        df_students = pd.DataFrame(columns=["رقم التلميذ", "الرقم التسلسلي", "اسم التلميذ", "تاريخ الإزدياد", "القسم", "المستوى"])

    try:
        reports_worksheet = sh.worksheet("Reports")
        reports_rows = reports_worksheet.get_all_values()
        if reports_rows and len(reports_rows) > 1:
            reports_headers = [h.strip() for h in reports_rows[0]]
            df_reports = pd.DataFrame(reports_rows[1:], columns=reports_headers)
            df_reports = normalize_reports_df(df_reports)
        else:
            df_reports = pd.DataFrame(columns=["التاريخ", "رقم مسار", "الاسم", "القسم", "الدرس", "التقرير", "بصمات_الصور", "بصمة_الخط"])
    except:
        df_reports = pd.DataFrame(columns=["التاريخ", "رقم مسار", "الاسم", "القسم", "الدرس", "التقرير", "بصمات_الصور", "بصمة_الخط"])
        
    try:
        lessons_worksheet = sh.worksheet("Lessons")
        lessons_rows = lessons_worksheet.get_all_values()
        exact_headers = ["المستوى", "الدرس", "رابط_PDF", "الملاحظات_المرجعية", "تاريخ_التحديث", "حالة_التفعيل"]
        if lessons_rows and len(lessons_rows) > 1:
            raw_headers = [h.strip() for h in lessons_rows[0]]
            while len(raw_headers) < 6:
                raw_headers.append(exact_headers[len(raw_headers)])
            padded_rows = [r + [""] * (len(raw_headers) - len(r)) for r in lessons_rows[1:]]
            df_lessons = pd.DataFrame(padded_rows, columns=raw_headers)
            df_lessons.columns = df_lessons.columns.str.strip()
        else:
            df_lessons = pd.DataFrame(columns=exact_headers)
    except:
        df_lessons = pd.DataFrame(columns=["المستوى", "الدرس", "رابط_PDF", "الملاحظات_المرجعية", "تاريخ_التحديث", "حالة_التفعيل"])
        
    return df_students, df_reports, df_lessons

df_students, df_reports, df_lessons = load_data()

def get_lesson_details(level_name, lesson_name, df_lessons):
    clean_level = level_name.strip()
    clean_lesson = lesson_name.strip()
    if not df_lessons.empty and "المستوى" in df_lessons.columns and "الدرس" in df_lessons.columns:
        match_row = df_lessons[(df_lessons["المستوى"].str.strip() == clean_level) & (df_lessons["الدرس"].str.strip() == clean_lesson)]
        if not match_row.empty:
            pdf_link = str(match_row.iloc[0].get("رابط_PDF", "")).strip()
            latex_or_note = str(match_row.iloc[0].get("الملاحظات_المرجعية", "")).strip()
            status_raw = str(match_row.iloc[0].get("حالة_التفعيل", "")).strip()
            has_reference = bool(pdf_link or latex_or_note)
            
            if status_raw in ["مغلق", "غير مفعل", "معطل", "False", "0"]:
                is_active = False
            elif status_raw == "مفعل":
                is_active = has_reference
            else:
                is_active = has_reference
            return pdf_link, latex_or_note, is_active, status_raw
    return "", "", False, "مغلق"

# --- القائمة الجانبية ---
with st.sidebar:
    st.markdown("""
        <div style='text-align: center; padding: 10px;'>
        <span style='font-size: 1.9rem;'>🎓</span>
        <h3 style='color: #FFD700 !important; font-size: 1.3rem; margin-top: 10px; text-shadow: 1px 1px 2px black;'>وزارة التربية الوطنية والتعليم الأولي والرياضة</h3>
            <p style='color: #cbd5e1 !important; font-size: 0.95rem;'>ثانوية الزرقطوني التأهيلية</p>
        </div>
    """, unsafe_allow_html=True)
    st.divider()
    
    if st.session_state.auth:
        user_display = st.session_state.user.get('name', 'المستخدم')
        st.success(f" مرحباً ب: \n\n**{user_display}**")
        if st.session_state.role == "student":
            st.info(f"🏫 القسم: {st.session_state.user.get('class')}\n🔢 الرقم التسلسلي: {st.session_state.user.get('serial')}\n📚 المستوى: {st.session_state.user.get('level')}")
        st.divider()
        if st.button("🚪 تسجيل الخروج", use_container_width=True):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.cache_data.clear()
            st.rerun()
    else:
        menu = st.radio(label="اختر الفضاء المستهدف:", options=["فضاء التلميذات والتلاميذ", "فضاء الإدارة والأستاذ"])
        st.session_state.role = "student" if "التلميذ" in menu else "admin"

# --- واجهة الأستاذ ---
def admin_space(df_students, df_reports, df_lessons):
    st.markdown("""
        <div style='background: linear-gradient(#008E8E, #1a365d 0%, #C72C48 100%); padding: 30px; border-radius: 15px; margin-bottom: 25px; color: white; border: 2px solid #C5A059;'>
            <h1 class='golden-title' style='font-size: 2.3rem;'>👨‍🏫 الفضاء الرقمي للتدقيق الإداري والتربوي</h1>
            <p class='golden-sub'>مرحباً بك ذ.عبد الباسط منصوري - تتبع ذكي لمراقبة وتصحيح دفاتر التلاميذ</p>
        </div>
    """, unsafe_allow_html=True)
    
    tab1, tab_classes, tab2, tab3, tab4 = st.tabs([
        "📊 لوحة الإحصائيات", 
        "📋 تتبع التلاميذ حسب القسم", 
        "🚦 تفعيل الدروس وإدارة المراجع (PDF / LaTeX)", 
        "👥 تتبع السجلات وحالات الغش", 
        "⚙️ الإعدادات"
    ])
    
    with tab1:
        st.markdown("<div class='section-title'>📈 المؤشرات التربوية العامة</div>", unsafe_allow_html=True)
        cheat_count = 0
        if not df_reports.empty:
            cheat_count = sum(1 for _, r in df_reports.iterrows() if is_cheating_row(r))
            
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.markdown(f"<div class='metric-card'><p style='color:#64748b; font-weight:bold;'>إجمالي التلاميذ</p><h2 style='margin:0; color:#1a365d;'>👥 {len(df_students)}</h2></div>", unsafe_allow_html=True)
        with col2: st.markdown(f"<div class='metric-card'><p style='color:#64748b; font-weight:bold;'>الدفاتر المدققة</p><h2 style='margin:0; color:#1a365d;'>📥 {len(df_reports)}</h2></div>", unsafe_allow_html=True)
        with col3: st.markdown(f"<div class='metric-card' style='border: 2px solid #dc2626 !important; background-color: #fef2f2 !important;'><p style='color:#991b1b; font-weight:bold;'>حالات الغش / المخالفات</p><h2 style='margin:0; color:#dc2626;'>🚨 {cheat_count}</h2></div>", unsafe_allow_html=True)
        with col4: 
            num_classes = df_students['القسم'].nunique() if not df_students.empty and 'القسم' in df_students.columns else 0
            st.markdown(f"<div class='metric-card'><p style='color:#64748b; font-weight:bold;'>الأقسام</p><h2 style='margin:0; color:#1a365d;'>🏫 {num_classes}</h2></div>", unsafe_allow_html=True)
        
        if not df_reports.empty and 'القسم' in df_reports.columns:
            fig = px.bar(df_reports.groupby('القسم').size().reset_index(name='عدد الإرسالات'), x='القسم', y='عدد الإرسالات', title="📊 تفاعل الأقسام والالتزام بالدفاتر الرقمية", color_discrete_sequence=['#1a365d'])
            st.plotly_chart(fig, use_container_width=True)

    with tab_classes:
        st.markdown("<div class='section-title'>🏫 التتبع الشامل لتلاميذ كل قسم وحالة إرسال الدروس</div>", unsafe_allow_html=True)
        if df_students.empty or 'القسم' not in df_students.columns:
            st.warning("⚠️ لا توجد بيانات للتلاميذ في ورقة التلاميذ حالياً.")
        else:
            all_classes_list = sorted([c for c in df_students['القسم'].astype(str).str.strip().unique().tolist() if c and c != "nan"])
            if not all_classes_list:
                st.warning("⚠️ لم يتم العثور على أقسام مسجلة.")
            else:
                if "selected_track_class" not in st.session_state or st.session_state["selected_track_class"] not in all_classes_list:
                    st.session_state["selected_track_class"] = all_classes_list[0]
                
                st.markdown("**1️⃣ اضغط على القسم لعرض لائحة تلاميذه وإحصائيات الإرسال:**")
                btn_cols = st.columns(len(all_classes_list))
                for idx_c, cls_name in enumerate(all_classes_list):
                    is_selected = (st.session_state["selected_track_class"] == cls_name)
                    btn_label = f"📍 {cls_name}" if is_selected else f"🏫 {cls_name}"
                    if btn_cols[idx_c].button(btn_label, key=f"cls_btn_{cls_name}", use_container_width=True):
                        st.session_state["selected_track_class"] = cls_name
                        st.rerun()
                
                chosen_cls = st.session_state["selected_track_class"]
                df_cls_students = df_students[df_students['القسم'].astype(str).str.strip() == chosen_cls].copy()
                
                if 'الرقم التسلسلي' in df_cls_students.columns:
                    df_cls_students['_ser_num'] = pd.to_numeric(df_cls_students['الرقم التسلسلي'], errors='coerce').fillna(9999)
                    df_cls_students = df_cls_students.sort_values(by='_ser_num')
                
                sample_lvl = str(df_cls_students.iloc[0].get('المستوى', '')).strip() if (not df_cls_students.empty and 'المستوى' in df_cls_students.columns) else ""
                cls_level = detect_level_from_class(chosen_cls, sample_lvl)
                
                active_lessons_for_cls = []
                for idx_l in range(1, 13):
                    l_name_tmp = f"الدرس {idx_l}"
                    _, _, is_act_tmp, _ = get_lesson_details(cls_level, l_name_tmp, df_lessons)
                    if is_act_tmp:
                        active_lessons_for_cls.append(l_name_tmp)
                
                tracked_lessons = active_lessons_for_cls if active_lessons_for_cls else ["الدرس 1", "الدرس 2"]
                
                st.markdown(f"### 📋 لائحة تلاميذ قسم: **{chosen_cls}** ({cls_level})")
                
                submissions_map = {}
                if not df_reports.empty and 'رقم مسار' in df_reports.columns and 'الدرس' in df_reports.columns:
                    for _, rep_r in df_reports.iterrows():
                        m_key = str(rep_r.get('رقم مسار', '')).strip().upper()
                        l_key = str(rep_r.get('الدرس', '')).strip()
                        rep_txt = str(rep_r.get('التقرير', ''))
                        col_h = str(rep_r.get('بصمة_الخط', '')).strip()
                        pct_val = extract_percentage_from_report(rep_txt) if rep_txt else (col_h if "%" in col_h else "0%")
                        cheat_flag = is_cheating_row(rep_r)
                        submissions_map[(m_key, l_key)] = (pct_val, cheat_flag)
                
                total_students_cls = len(df_cls_students)
                lesson_sent_counts = {l: 0 for l in tracked_lessons}
                both_or_all_count = 0
                partial_count = 0
                none_count = 0
                
                table_rows = []
                for _, st_r in df_cls_students.iterrows():
                    st_massar = str(st_r.get('رقم التلميذ', '')).strip().upper()
                    st_serial = str(st_r.get('الرقم التسلسلي', '')).strip()
                    st_name = str(st_r.get('اسم التلميذ', '')).strip()
                    
                    row_dict = {
                        "الرقم التسلسلي": st_serial,
                        "رقم مسار": st_massar,
                        "اسم التلميذ": st_name,
                    }
                    
                    sent_for_this_student = 0
                    for l_tr in tracked_lessons:
                        if (st_massar, l_tr) in submissions_map:
                            pct_v, is_ch = submissions_map[(st_massar, l_tr)]
                            lesson_sent_counts[l_tr] += 1
                            sent_for_this_student += 1
                            if is_ch:
                                row_dict[f"أرسل {l_tr}"] = "🚨 نعم (غش 0%)"
                            else:
                                row_dict[f"أرسل {l_tr}"] = f"✅ نعم ({pct_v})"
                        else:
                            row_dict[f"أرسل {l_tr}"] = "❌ لا"
                    
                    if sent_for_this_student == len(tracked_lessons):
                        both_or_all_count += 1
                        row_dict["ملخص الحالة"] = "🟢 أرسل جميع الدروس المفعّلة"
                    elif sent_for_this_student > 0:
                        partial_count += 1
                        row_dict["ملخص الحالة"] = f"🟡 أرسل {sent_for_this_student} من {len(tracked_lessons)} فقط"
                    else:
                        none_count += 1
                        row_dict["ملخص الحالة"] = "🔴 لم يرسل أي درس"
                        
                    table_rows.append(row_dict)
                
                st.markdown("#### 📊 نسب الإرسال وتوزيع التلاميذ في هذا القسم:")
                stat_cols = st.columns(len(tracked_lessons) + 3)
                
                for idx_l, l_tr in enumerate(tracked_lessons):
                    cnt_l = lesson_sent_counts[l_tr]
                    rate_l = round((cnt_l / total_students_cls) * 100, 1) if total_students_cls > 0 else 0.0
                    with stat_cols[idx_l]:
                        st.markdown(
                            f"<div class='metric-card' style='padding:12px; text-align:center;'>"
                            f"<p style='color:#64748b; margin:0; font-size:0.95rem;'>نسبة إرسال {l_tr}</p>"
                            f"<h3 style='color:#1e3a8a; margin:4px 0;'>{rate_l}%</h3>"
                            f"<small style='color:#475569;'>({cnt_l} من {total_students_cls} تلميذ)</small>"
                            f"</div>", unsafe_allow_html=True
                        )
                
                with stat_cols[len(tracked_lessons)]:
                    st.markdown(
                        f"<div class='metric-card' style='padding:12px; text-align:center; border-color:#10b981 !important;'>"
                        f"<p style='color:#065f46; margin:0; font-size:0.95rem;'>أرسلوا الكل (نعم/نعم)</p>"
                        f"<h3 style='color:#059669; margin:4px 0;'>🟢 {both_or_all_count}</h3>"
                        f"<small style='color:#475569;'>تلميذ(ة)</small>"
                        f"</div>", unsafe_allow_html=True
                    )
                with stat_cols[len(tracked_lessons) + 1]:
                    st.markdown(
                        f"<div class='metric-card' style='padding:12px; text-align:center; border-color:#f59e0b !important;'>"
                        f"<p style='color:#92400e; margin:0; font-size:0.95rem;'>أرسلوا درساً واحداً فقط</p>"
                        f"<h3 style='color:#d97706; margin:4px 0;'>🟡 {partial_count}</h3>"
                        f"<small style='color:#475569;'>تلميذ(ة)</small>"
                        f"</div>", unsafe_allow_html=True
                    )
                with stat_cols[len(tracked_lessons) + 2]:
                    st.markdown(
                        f"<div class='metric-card' style='padding:12px; text-align:center; border-color:#ef4444 !important;'>"
                        f"<p style='color:#991b1b; margin:0; font-size:0.95rem;'>لم يرسلوا شيئاً (لا/لا)</p>"
                        f"<h3 style='color:#dc2626; margin:4px 0;'>🔴 {none_count}</h3>"
                        f"<small style='color:#475569;'>تلميذ(ة)</small>"
                        f"</div>", unsafe_allow_html=True
                    )
                
                st.write("")
                df_class_tracking = pd.DataFrame(table_rows)
                
                status_filter = st.radio(
                    "تصفية تلاميذ القسم:",
                    [
                        f"الجميع ({total_students_cls})",
                        f"🟢 أرسلوا جميع الدروس ({both_or_all_count})",
                        f"🟡 أرسلوا درساً واحداً فقط ({partial_count})",
                        f"🔴 لم يرسلوا أي درس ({none_count})"
                    ],
                    horizontal=True,
                    key=f"filter_radio_{chosen_cls}"
                )
                
                df_filtered_view = df_class_tracking.copy()
                if "أرسلوا جميع الدروس" in status_filter:
                    df_filtered_view = df_filtered_view[df_filtered_view["ملخص الحالة"].str.contains("🟢")]
                elif "درساً واحداً فقط" in status_filter:
                    df_filtered_view = df_filtered_view[df_filtered_view["ملخص الحالة"].str.contains("🟡")]
                elif "لم يرسلوا أي درس" in status_filter:
                    df_filtered_view = df_filtered_view[df_filtered_view["ملخص الحالة"].str.contains("🔴")]
                
                def style_tracking_table(row):
                    summary = str(row.get("ملخص الحالة", ""))
                    if "🟢" in summary:
                        return ['background-color: #ecfdf5; color: #065f46'] * len(row)
                    elif "🟡" in summary:
                        return ['background-color: #fffbeb; color: #92400e'] * len(row)
                    elif "🔴" in summary:
                        return ['background-color: #fef2f2; color: #991b1b'] * len(row)
                    return [''] * len(row)
                
                st.dataframe(
                    df_filtered_view.style.apply(style_tracking_table, axis=1),
                    use_container_width=True,
                    hide_index=True
                )
                
                csv_export = df_class_tracking.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label=f"📥 تحميل لائحة تتبع قسم {chosen_cls} (Excel / CSV)",
                    data=csv_export,
                    file_name=f"تتبع_قسم_{chosen_cls}_{datetime.now().strftime('%Y-%m-%d')}.csv",
                    mime="text/csv"
                )

    with tab2:
        st.markdown("<div class='section-title'>🚦 التحكم في تفعيل / إغلاق إرسال الدروس للتلاميذ</div>", unsafe_allow_html=True)
        selected_level = st.selectbox("1️⃣ اختر المستوى الدراسي المستهدف:", ["جذع مشترك علوم", "أولى باكالوريا علوم (1 باك SEF)"], key="ctrl_level_select")
        
        if st.session_state.get("last_synced_level") != selected_level:
            for idx_l in range(1, 13):
                l_t = f"الدرس {idx_l}"
                _, _, act_db, _ = get_lesson_details(selected_level, l_t, df_lessons)
                st.session_state[f"chk_{selected_level}_{l_t}"] = act_db
            st.session_state["last_synced_level"] = selected_level

        st.info("💡 لا يُفتح الدرس للتلميذ إلا إذا كان **مفعّلاً (🟢)** **وله مرجع محفوظ** (رابط PDF في العمود C أو كود LaTeX في العمود D). الحفظ هنا يُحدّث العمود F فقط دون المساس بروابطك أو أكواد LaTeX.")
        
        q_col1, q_col2 = st.columns(2)
        if q_col1.button("✅ تحديد الكل كمفعّل", use_container_width=True):
            for idx_l in range(1, 13):
                st.session_state[f"chk_{selected_level}_الدرس {idx_l}"] = True
            st.rerun()
        if q_col2.button("🔒 إلغاء تفعيل (إغلاق) الكل", use_container_width=True):
            for idx_l in range(1, 13):
                st.session_state[f"chk_{selected_level}_الدرس {idx_l}"] = False
            st.rerun()

        cols_grid = st.columns(3)
        lesson_toggles = {}
        for i in range(1, 13):
            l_title = f"الدرس {i}"
            pdf_db, latex_db, _, _ = get_lesson_details(selected_level, l_title, df_lessons)
            has_ref_db = bool(pdf_db or latex_db)
            chk_key = f"chk_{selected_level}_{l_title}"
            if chk_key not in st.session_state:
                _, _, current_active, _ = get_lesson_details(selected_level, l_title, df_lessons)
                st.session_state[chk_key] = current_active
            with cols_grid[(i - 1) % 3]:
                ref_badge = "📄 مرجع محفوظ" if has_ref_db else "⚠️ بدون مرجع"
                lesson_toggles[l_title] = st.checkbox(
                    f"{'🟢' if st.session_state[chk_key] else '🔴'} {l_title} ({ref_badge})",
                    key=chk_key
                )
        
        if st.button(f"💾 حفظ حالة تفعيل الدروس لمستوى ({selected_level})", use_container_width=True):
            with st.spinner("جاري تحديث العمود F (حالة_التفعيل) دون المساس بالروابط أو أكواد LaTeX..."):
                try:
                    client = get_gspread_client()
                    sh = client.open("les classes")
                    ws_lessons = sh.worksheet("Lessons")
                    all_vals = ws_lessons.get_all_values()
                    
                    if not all_vals:
                        ws_lessons.update("A1:F1", [["المستوى", "الدرس", "رابط_PDF", "الملاحظات_المرجعية", "تاريخ_التحديث", "حالة_التفعيل"]])
                        all_vals = ws_lessons.get_all_values()
                    elif len(all_vals[0]) < 6 or all_vals[0][5].strip() != "حالة_التفعيل":
                        ws_lessons.update_cell(1, 6, "حالة_التفعيل")
                        
                    missing_refs = []
                    for l_title, is_act in lesson_toggles.items():
                        status_str = "مفعل" if is_act else "مغلق"
                        row_idx_found = None
                        existing_pdf = ""
                        existing_latex = ""
                        
                        for r_idx, row in enumerate(all_vals[1:], start=2):
                            if len(row) >= 2 and row[0].strip() == selected_level.strip() and row[1].strip() == l_title.strip():
                                row_idx_found = r_idx
                                existing_pdf = row[2].strip() if len(row) > 2 else ""
                                existing_latex = row[3].strip() if len(row) > 3 else ""
                                break
                                
                        if row_idx_found is not None:
                            ws_lessons.update_cell(row_idx_found, 6, status_str)
                            if is_act and not (existing_pdf or existing_latex):
                                missing_refs.append(l_title)
                        else:
                            ws_lessons.append_row([selected_level, l_title, "", "", datetime.now().strftime("%Y-%m-%d %H:%M"), status_str])
                            if is_act:
                                missing_refs.append(l_title)
                            
                    st.cache_data.clear()
                    if "last_synced_level" in st.session_state:
                        del st.session_state["last_synced_level"]
                        
                    if missing_refs:
                        st.warning(f"✅ تم الحفظ بأمان! تنبيه: الدروس ({', '.join(missing_refs)}) ستبقى مغلقة عند التلميذ حتى تضع لها رابط PDF أو كود LaTeX المرجعي أسفله.")
                    else:
                        st.success(f"✅ تم بنجاح حفظ حالة الإرسال لدروس ({selected_level}) في العمود F مع الحفاظ التام على جميع المراجع!")
                    time.sleep(1.5)
                    st.rerun()
                except Exception as toggle_err:
                    st.error(f"حدث خطأ أثناء حفظ حالة التفعيل: {toggle_err}")

        st.divider()
        st.markdown("<div class='section-title'>📂 إدخال وتعديل المراجع (رابط_PDF / كود LaTeX) للدرس</div>", unsafe_allow_html=True)
        
        lesson_list_options = [f"الدرس {i}" for i in range(1, 13)]
        selected_lesson_num = st.selectbox("2️⃣ اختر الدرس لإدخال أو تعديل مرجعه:", lesson_list_options)
        
        current_pdf_link, current_latex, current_is_active, _ = get_lesson_details(selected_level, selected_lesson_num, df_lessons)
        
        st.info(
            f"📋 حالة الدرس في السجل الحالي:\n"
            f"- المستوى: {selected_level}\n"
            f"- الدرس: {selected_lesson_num}\n"
            f"- حالة الإرسال للتلميذ: {'🟢 مفتوح ويستقبل الإرسالات' if current_is_active else '🔴 مغلق حالياً'}\n"
            f"- رابط PDF (العمود C): {current_pdf_link if current_pdf_link else 'غير مدخل'}\n"
            f"- كود LaTeX / الملاحظات (العمود D): {'✅ موجود ومحفوظ' if current_latex else '⚠️ غير مدخل بعد'}"
        )
        
        input_drive_link = st.text_input("3️⃣ رابط ملف الـ PDF من Google Drive (العمود C - اختياري):", value=current_pdf_link).strip()
        ref_note = st.text_area("4️⃣ كود LaTeX المرجعي أو عناوين وملاحظات الدرس (العمود D):", height=220, value=current_latex).strip()

        if st.button("💾 حفظ المرجع وتفعيل الدرس في Google Sheets", use_container_width=True):
            if not input_drive_link and not ref_note:
                st.warning("⚠️ يرجى إدخال رابط PDF أو كود LaTeX المرجعي للدرس أولاً.")
            else:
                with st.spinner("جاري حفظ المرجع في الأعمدة C و D وتحديث تاريخ التحديث..."):
                    try:
                        client = get_gspread_client()
                        sh = client.open("les classes")
                        ws_lessons = sh.worksheet("Lessons")
                        all_vals = ws_lessons.get_all_values()
                        
                        if not all_vals:
                            ws_lessons.update("A1:F1", [["المستوى", "الدرس", "رابط_PDF", "الملاحظات_المرجعية", "تاريخ_التحديث", "حالة_التفعيل"]])
                            all_vals = ws_lessons.get_all_values()
                        elif len(all_vals[0]) < 6 or all_vals[0][5].strip() != "حالة_التفعيل":
                            ws_lessons.update_cell(1, 6, "حالة_التفعيل")
                        
                        row_idx_found = None
                        for r_idx, row in enumerate(all_vals[1:], start=2):
                            if len(row) >= 2 and row[0].strip() == selected_level.strip() and row[1].strip() == selected_lesson_num.strip():
                                row_idx_found = r_idx
                                break
                                
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        if row_idx_found is not None:
                            ws_lessons.update(f"C{row_idx_found}:F{row_idx_found}", [[input_drive_link, ref_note, now_str, "مفعل"]])
                        else:
                            ws_lessons.append_row([selected_level, selected_lesson_num, input_drive_link, ref_note, now_str, "مفعل"])
                        
                        st.cache_data.clear()
                        if "last_synced_level" in st.session_state:
                            del st.session_state["last_synced_level"]
                        st.success(f"🎉 تم بنجاح حفظ المرجع وتفعيل ({selected_lesson_num} - {selected_level})!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as ex:
                        st.error(f"خطأ أثناء التحديث السحابي: {ex}")

    with tab3:
        st.markdown("<div class='section-title'>👥 تتبع وتقارير التلاميذ (إبراز حالات الغش بلون مميز)</div>", unsafe_allow_html=True)
        if not df_reports.empty:
            df_display = df_reports.copy()
            df_display.insert(0, "الحالة", df_display.apply(lambda r: "🚨 حالة غش / مخالفة" if is_cheating_row(r) else "✅ سليم", axis=1))
            
            filter_choice = st.radio(
                "تصفية السجلات:", 
                ["عرض جميع السجلات", "🚨 عرض حالات الغش والمخالفات فقط (0%)"], 
                horizontal=True
            )
            if "حالات الغش" in filter_choice:
                df_display = df_display[df_display["الحالة"].str.contains("غش")]
            
            def highlight_cheat_rows(row):
                if "غش" in str(row.get("الحالة", "")):
                    return ['background-color: #fee2e2; color: #991b1b; font-weight: bold'] * len(row)
                return [''] * len(row)
                
            styled_df = df_display.style.apply(highlight_cheat_rows, axis=1)
            st.dataframe(styled_df, use_container_width=True)
        else:
            st.info("لا توجد تقارير مرسلة حالياً.")
            
        st.divider()
        st.markdown("<div class='section-title'>🗑️ لوحة الإلغاء والتصفير (منح فرصة ثانية للتلميذ)</div>", unsafe_allow_html=True)
        
        if not df_reports.empty and 'القسم' in df_reports.columns:
            available_classes = ["---"] + sorted(df_reports['القسم'].dropna().unique().tolist())
            chosen_class = st.selectbox("1️⃣ اختر قسم التلميذ المراد تصفيره:", available_classes, key="reset_class_select")
            
            if chosen_class != "---":
                df_filtered_class = df_reports[df_reports['القسم'] == chosen_class]
                student_options = []
                student_mapping = {}
                
                for idx, r in df_filtered_class.iterrows():
                    m_id = str(r.get('رقم مسار', '')).strip().upper()
                    s_name = str(r.get('الاسم', '')).strip()
                    cheat_tag = " 🚨 [غش]" if is_cheating_row(r) else ""
                    display_text = f"👤 {s_name} (مسار: {m_id}){cheat_tag}"
                    if display_text not in student_options:
                        student_options.append(display_text)
                        student_mapping[display_text] = m_id
                
                chosen_student_profile = st.selectbox("2️⃣ اختر التلميذ المستهدف بالتصفير:", ["---"] + student_options, key="reset_student_select")
                target_lesson_to_reset = st.selectbox("3️⃣ حدد النطاق المراد حذفه وتصفيره:", ["كل الدروس"] + [f"الدرس {i}" for i in range(1, 13)], key="reset_lesson_select")
                
                if chosen_student_profile != "---":
                    target_massar_id = student_mapping[chosen_student_profile]
                    
                    if st.button("🔥 تصفير وإعادة تعيين معطيات التلميذ الآن", use_container_width=True):
                        with st.spinner("جاري الاتصال السحابي وإلغاء القيود..."):
                            try:
                                client = get_gspread_client()
                                sh = client.open("les classes")
                                ws_reports = sh.worksheet("Reports")
                                all_rows = ws_reports.get_all_values()
                                
                                if all_rows and len(all_rows) > 1:
                                    headers = all_rows[0]
                                    old_records = all_rows[1:]
                                    new_records = []
                                    deleted_count = 0
                                    
                                    for row in old_records:
                                        if len(row) >= 5:
                                            row_massar = str(row[1]).strip().upper()
                                            row_lesson = str(row[4]).strip()
                                            
                                            match_massar = (row_massar == target_massar_id)
                                            match_lesson = (target_lesson_to_reset == "كل الدروس" or row_lesson == target_lesson_to_reset)
                                            
                                            if match_massar and match_lesson:
                                                deleted_count += 1
                                                continue
                                        new_records.append(row)
                                    
                                    ws_reports.clear()
                                    ws_reports.update([headers] + new_records)
                                    st.cache_data.clear()
                                    st.success(f"✅ تم بنجاح تصفير وحذف ({deleted_count}) سجل للتلميذ.")
                                    time.sleep(1)
                                    st.rerun()
                            except Exception as reset_err:
                                st.error(f"حدث خطأ أثناء محاولة التصفير: {reset_err}")

    with tab4:
        st.markdown("<div class='section-title'>⚙️ إعدادات الصيانة والأمان</div>", unsafe_allow_html=True)
        loaded_keys = get_all_api_keys()
        st.success(f"🔑 عدد مفاتيح Gemini API المفعّلة للتبديل التلقائي: **{len(loaded_keys)}** مفاتيح (يدعم الموديلين `gemini-3.8-flash` و `gemini-2.5-flash` تلقائياً).")

# --- واجهة التلميذ ---
def student_space(df_students, df_reports, df_lessons):
    st.markdown("""
        <div style='background: linear-gradient(135deg, #10b981 0%, #1a365d 100%); padding: 35px; border-radius: 15px; margin-bottom: 25px; text-align: center; border: 2px solid #C5A059;'>
            <h2 class='golden-title' style='font-size: 2.5rem;'>🇲🇦 الفضاء الرقمي للتلميذات والتلاميذ</h2>
            <p class='golden-sub'>منصة ذ.منصوري للتدقيق الفوري للدفاتر المدرسية مدعومة بالذكاء الاصطناعي (AI)</p>
        </div>
    """, unsafe_allow_html=True)
    
    if df_students.empty:
        st.warning("🔄 جاري تهيئة الاتصال السحابي الآمن...")
        return

    col_class = 'القسم'
    col_name = 'اسم التلميذ'
    col_id = 'رقم التلميذ'  
    col_birth = 'تاريخ الإزدياد'
    col_serial = 'الرقم التسلسلي'

    if not st.session_state.auth:
        st.markdown("<div class='section-title'>🔑 تسجيل الدخول الآمن لمنظومة التدقيق</div>", unsafe_allow_html=True)
        sel_class = st.selectbox("الرجاء تحديد قسمك الفعلي:", ["---"] + sorted(df_students[col_class].astype(str).str.strip().unique().tolist()))
        col_input1, col_input2 = st.columns(2)
        input_massar = col_input1.text_input("أدخل رقم مسار الخاص بك:").strip()
        input_birth = col_input2.text_input("أدخل تاريخ ازديادك الموثق (سنة-شهر-يوم):").strip()
        
        if st.button("التحقق والولوج الآمن للمنصة 🚀", use_container_width=True):
            if sel_class != "---" and input_massar and input_birth:
                df_students[col_id] = df_students[col_id].astype(str).str.strip()
                df_students[col_birth] = df_students[col_birth].astype(str).str.strip()
                df_students[col_class] = df_students[col_class].astype(str).str.strip()
                
                matched_student = df_students[
                    (df_students[col_class] == sel_class) & 
                    (df_students[col_id].str.upper() == input_massar.upper()) & 
                    (df_students[col_birth] == input_birth)
                ]
                if not matched_student.empty:
                    row_std = matched_student.iloc[0]
                    raw_level = str(row_std.get('المستوى', '')).strip() if 'المستوى' in row_std else ""
                    student_level_val = detect_level_from_class(sel_class, raw_level)
                    student_serial_val = str(row_std.get(col_serial, 'غير محدد')).strip() if col_serial in row_std else 'غير محدد'
                    
                    st.session_state.auth = True
                    st.session_state.user = {
                        "name": str(row_std[col_name]).strip(), 
                        "class": sel_class,
                        "massar": input_massar.strip().upper(),
                        "serial": student_serial_val,
                        "level": student_level_val
                    }
                    st.success("🎉 تم التحقق من الهوية بنجاح!")
                    st.rerun()
                else:
                    st.error("❌ عذراً، المعلومات المدخلة غير متطابقة.")
    else:
        student_name = st.session_state.user['name']
        student_massar = st.session_state.user.get('massar', '')
        student_serial = st.session_state.user.get('serial', 'غير محدد')
        student_level = detect_level_from_class(st.session_state.user['class'], st.session_state.user.get('level', ''))
        
        st.success(f"🏫 التلميذ(ة): **{student_name}** | الرقم التسلسلي: **{student_serial}** | مسار: **{student_massar}** | المستوى: **{student_level}** | القسم: **{st.session_state.user['class']}**")
        
        student_all_submissions = pd.DataFrame()
        if not df_reports.empty and 'رقم مسار' in df_reports.columns and 'الدرس' in df_reports.columns:
            df_reports['massar_clean'] = df_reports['رقم مسار'].astype(str).str.strip().str.upper()
            df_reports['الدرس_نظيف'] = df_reports['الدرس'].astype(str).str.strip()
            student_all_submissions = df_reports[df_reports['massar_clean'] == student_massar.upper()]
            
        submitted_lessons = student_all_submissions['الدرس_نظيف'].tolist() if not student_all_submissions.empty else []
        
        lesson_percentages = {}
        lesson_full_reports = {}
        if not student_all_submissions.empty:
            for _, row in student_all_submissions.iterrows():
                l_clean = str(row['الدرس_نظيف'])
                rep_content = str(row.get('التقرير', ''))
                lesson_full_reports[l_clean] = rep_content
                
                extracted_from_rep = extract_percentage_from_report(rep_content)
                if extracted_from_rep != "0%":
                    lesson_percentages[l_clean] = extracted_from_rep
                else:
                    col_h_val = str(row.get('بصمة_الخط', '')).strip()
                    lesson_percentages[l_clean] = col_h_val if "%" in col_h_val else "0%"
        
        st.markdown("<div class='section-title'>📊 وضعيتك الحالية في السجل الرقمي:</div>", unsafe_allow_html=True)
        
        lesson_names_12 = [f"الدرس {i}" for i in range(1, 13)]
        
        if len(submitted_lessons) > 0:
            status_text = "📢 <b>حالة إرسال الدفاتر والتدقيق:</b><br>"
            for l_sub in lesson_names_12:
                if l_sub in submitted_lessons:
                    pct = lesson_percentages.get(l_sub, "0%")
                    if pct == "0%":
                        status_text += f"🚨 تم تدقيق <b>{l_sub}</b> وتم رصد <b>مخالفة/حالة غش في الرقم التسلسلي</b> (النسبة: <span style='color:white; background:#dc2626; padding:2px 8px; border-radius:4px;'><b>0%</b></span>)<br>"
                    else:
                        status_text += f"✅ نسبة تدوينك وإنجازك لـ <b>{l_sub}</b> هي: <span style='color:#ffffff; background:#1e3a8a; padding:2px 10px; border-radius:5px;'><b>{pct}</b></span><br>"
            st.markdown(f"<div class='status-box'>{status_text}</div>", unsafe_allow_html=True)
        else:
            st.info("اختر الدرس المفعّل من التبويبات أسفله لرفع صور دفترك.")

        tab_labels = []
        for i in range(1, 13):
            l_tmp = f"الدرس {i}"
            _, _, active_tmp, _ = get_lesson_details(student_level, l_tmp, df_lessons)
            if l_tmp in submitted_lessons:
                tab_labels.append(f"✅ {l_tmp}")
            elif active_tmp:
                tab_labels.append(f"📚 {l_tmp}")
            else:
                tab_labels.append(f"🔒 {l_tmp}")

        lesson_tabs = st.tabs(tab_labels)
        
        for i, tab in enumerate(lesson_tabs):
            with tab:
                l_name = f"الدرس {i+1}"
                saved_pdf_link, saved_note, is_lesson_active, _ = get_lesson_details(student_level, l_name, df_lessons)
                
                if l_name in submitted_lessons:
                    current_p = lesson_percentages.get(l_name, "0%")
                    if current_p == "0%":
                        st.error(f"🚨 **تنبيه نظام التدقيق والنزاهة الرقمية:**")
                        st.markdown(f"<div style='background-color:#fee2e2; border-right:6px solid #dc2626; padding:15px; border-radius:8px; color:#991b1b; font-weight:bold;'>⚠️ تم رصد حالة غش / عدم تطابق الرقم التسلسلي في الصفحات. تجد تفاصيل التحليل الكامل وملاحظة المخالفة في الفقرة الأخيرة أسفله.</div>", unsafe_allow_html=True)
                        st.markdown(f"### 📋 تفاصيل التقرير الكامل وملاحظة المخالفة المحفوظة إدارياً:")
                        st.info(lesson_full_reports.get(l_name, "لا يوجد نص تقرير محفوظ."))
                    else:
                        st.success(f"🔒 **تم تدقيق {l_name} بنجاح:** نسبة تدوين الدرس المسجلة هي (**{current_p}**).")
                        with st.expander(f"📄 اضغط هنا لعرض تقرير تدقيق التدوين المفصل لـ {l_name}", expanded=True):
                            st.markdown(f"""
                            <div style='background-color: #f8fafc; padding: 20px; border-radius: 10px; border: 1px solid #cbd5e1; color: #1e293b;'>
                                <h4>📊 نسبة تدوين الدرس المحققة: <b>{current_p}</b></h4>
                                <hr>
                                <p style='white-space: pre-wrap; line-height: 1.6;'>{lesson_full_reports.get(l_name, "لا يوجد نص تقرير محفوظ.")}</p>
                            </div>
                            """, unsafe_allow_html=True)
                
                elif not is_lesson_active:
                    st.error(f"🔒 **لم يتم تفعيل الإرسال لهذا الدرس ({l_name})** من طرف الأستاذ عبد الباسط منصوري حالياً (إما أن الدرس غير مبرمج في هذه الفترة أو لم يُفعّل مرجعه بعد).")
                    st.info("📌 لا يمكن تحميل أي صور لهذا الدرس إلا بعد تفعيله من طرف الأستاذ. يرجى اختيار درس مفعّل (📚).")
                
                else:
                    st.markdown(f"#### 📸 centre de dépôt des cahiers - {l_name} ({student_level})")
                    st.success(f"🔗 تم رصد مرجع الدرس للأستاذ ({student_level})؛ سيتم تدقيق تدوين الفقرات وتصحيح التمارين والتحقق من رقمك التسلسلي.")

                    up_files = st.file_uploader(
                        f"اختر صور صفحات الدفتر لـ {l_name} (🚨 يشترط تحميل 8 صور على الأقل مع كتابة رقمك التسلسلي '{student_serial}' في هوامش جميع الصفحات):", 
                        accept_multiple_files=True, 
                        key=f"up_{student_level}_{l_name}", 
                        type=['jpg','jpeg','png']
                    )
                    
                    if st.button(f"بدء المعالجة وتدقيق نسبة التدوين لـ {l_name}", key=f"btn_{student_level}_{l_name}"):
                        if up_files:
                            if len(up_files) < 8:
                                st.error(f"⚠️ **خطأ في معايير قبول الدفتر:** لقد قمت برفع ({len(up_files)}) صور فقط! ميثاق المادة يشترط رفع **8 صور على الأقل** للدرس.")
                            else:
                                with st.spinner("🔄 جاري تدقيق تدوين الدرس والتمارين والتحقق من الرقم التسلسلي على الصفحات..."):
                                    current_hashes = []
                                    optimized_images = []
                                    
                                    for f in up_files:
                                        f_bytes = f.read()
                                        f.seek(0)
                                        current_hashes.append(calculate_image_hash(f_bytes))
                                        optimized_img = optimize_image_for_api(f)
                                        optimized_images.append(optimized_img)
                                    
                                    hashes_to_save = ",".join(current_hashes)
                                    
                                    pdf_reference_text = ""
                                    if saved_pdf_link:
                                        pdf_reference_text = extract_text_from_drive_pdf(saved_pdf_link)

                                    try:
                                        client = get_gspread_client()
                                        live_sh = client.open("les classes").worksheet("Reports")
                                        live_rows = live_sh.get_all_values()
                                        
                                        if live_rows and len(live_rows) > 1:
                                            live_headers = [h.strip() for h in live_rows[0]]
                                            df_live_reports = pd.DataFrame(live_rows[1:], columns=live_headers)
                                            df_live_reports = normalize_reports_df(df_live_reports)
                                        else:
                                            df_live_reports = pd.DataFrame(columns=["التاريخ", "رقم مسار", "الاسم", "القسم", "الدرس", "التقرير", "بصمات_الصور", "بصمة_الخط"])
                                    except Exception as check_err:
                                        st.error(f"❌ تعذر الاتصال بالسيرفر للتحقق من الأرشيف: {check_err}")
                                        st.stop()
                                
                                if not df_live_reports.empty and 'رقم مسار' in df_live_reports.columns and 'الدرس' in df_live_reports.columns:
                                    already_exists = df_live_reports[
                                        (df_live_reports['رقم مسار'].astype(str).str.strip().str.upper() == student_massar.upper()) &
                                        (df_live_reports['الدرس'].astype(str).str.strip() == l_name.strip())
                                    ]
                                    if not already_exists.empty:
                                        st.warning("⚠️ تم تسجيل هذا الدرس مسبقاً في السجل! جاري تحديث الواجهة...")
                                        st.cache_data.clear()
                                        st.rerun()

                                students_serial_lookup = ""
                                if not df_students.empty and col_serial in df_students.columns and col_name in df_students.columns:
                                    serial_entries = []
                                    for _, s_row in df_students.iterrows():
                                        s_ser = str(s_row.get(col_serial, '')).strip()
                                        s_nm = str(s_row.get(col_name, '')).strip()
                                        s_cl = str(s_row.get(col_class, '')).strip()
                                        if s_ser and s_ser != str(student_serial).strip():
                                            serial_entries.append(f"{s_ser}: {s_nm} ({s_cl})")
                                    students_serial_lookup = " | ".join(serial_entries)

                                with st.spinner("🔄 جاري إتمام التحليل الكامل والتحقق من الرقم التسلسلي..."):
                                    try:
                                        prompt_instructions = f"""
                                        أنت مساعد أستاذ الرياضيات عبد الباسط منصوري بالثانوية التأهيلية المغربية. مهمتك هي **تدقيق تدوين الدرس والتمارين** في دفتر التلميذ(ة): {student_name}
                                        - الرقم التسلسلي الرسمي للتلميذ(ة) المرسل: {student_serial}
                                        - رقم مسار: {student_massar}
                                        - المستوى الدراسي: {student_level}
                                        - القسم: {st.session_state.user['class']}
                                        - الدرس المستهدف: {l_name}
                                        
                                        النص المستخرج من ملف الـ PDF المرجعي (إن وُجد):
                                        \"\"\"{pdf_reference_text[:15000]}\"\"\"

                                        المخطط/كود LaTeX المرجعي المعتمد من الأستاذ (المصدر الوحيد للعناوين والفقرات المطلوبة):
                                        \"\"\"{saved_note}\"\"\"

                                        مرجع الأرقام التسلسلية لباقي التلاميذ (للتحقق فقط في حال رصد رقم مخالف):
                                        \"\"\"{students_serial_lookup}\"\"\"
                              
                                        قواعد التدقيق الصارمة (يجب الالتزام بها حرفياً):
                                        1. **الالتزام الحصري بمرجع الأستاذ (قاعدة الصندوق المغلق):**
                                           - يُمنع منعاً باتاً افتراض أو استدعاء أي أنشطة (Activités) أو تمارين إضافية من ذاكرتك الخارجية إذا لم تكن مذكورة في مرجع الأستاذ أعلاه أو غير مكتوبة في دفتر التلميذ.
                                           - إذا كان مرجع الأستاذ عبارة عن عناوين الفقرات الأساسية للدرس (مثل \\section*{{...}} و \\subsection*{{...}}) فقط، تحقق من تدوين كل عنوان ومحتواه المناسب، ولا تخصم أي نقطة على تمارين غير موجودة في المرجع.
                                        2. **التدقيق الدقيق في أسئلة التمارين المكتوبة في الدفتر (عدّ الأسئلة ومطابقتها مع التصحيح):**
                                           - بالنسبة لكل تمرين (Exercice / Application) مكتوب في دفتر التلميذ(ة) أو في المرجع:
                                             * احصر **العدد الإجمالي للأسئلة** الواردة في نص التمرين (مثلاً: سؤالان 1 و 2، أو خمسة أسئلة 1، 2، 3، 4، 5، أو أسئلة فرعية a, b, c).
                                             * افحص فقرة **التصحيح/الحل** في دفتر التلميذ(ة) وتأكد هل تم تدوين الإجابة على **جميع الأسئلة** أم على جزء منها فقط!
                                             * إذا كان التمرين يتكون من 5 أسئلة مثلاً، وتم تدوين تصحيح سؤالين فقط، نبّه التلميذ(ة) بدقة: ("في التمرين ...: نص التمرين يضم 5 أسئلة، لكن تم نقل تصحيح السؤالين 1 و 2 فقط، وبقيت الأسئلة 3 و 4 و 5 بدون تصحيح")، واخصم النسبة المتبقية من وزن هذا التمرين (مثلاً يُحتسب له 2/5 فقط من نقطة التمرين).
                                             * أما إذا تم تدوين تصحيح جميع أسئلة التمرين (مثلاً السؤالين من أصل سؤالين)، فيحصل التمرين على نقطته كاملة.
                                        3. **لغة تدقيق التدوين فقط:** التلميذ ينقل ما كتبه الأستاذ في السبورة. استخدم عبارات مثل: ("تم تدوين فقرة..."، "تم نقل تصحيح جميع أسئلة التمرين..."، "نقص في نقل تصحيح الأسئلة...").
                                        4. **إكمال التحليل للنهاية ثم فحص الرقم التسلسلي ({student_serial}) في الفقرة الأخيرة:**
                                           - **أكمل دائماً التحليل البيداغوجي للدرس والتمارين إلى نهايته** (أولاً: الفقرات والتمارين المدونة، وثانياً: الملاحظات والنواقص) مهما كانت نتيجة فحص الرقم التسلسلي.
                                           - بعد إتمام التحليل، افحص هوامش الصفحات المرفقة للتحقق من الرقم التسلسلي الرسمي للتلميذ(ة) المرسل: **{student_serial}**.
                                           - **قاعدة التثبّت البصري قبل الحكم:** راعِ جودة التصوير وطبيعة خط يد التلميذ(ة) (فقد يكتب `1` مائلاً فيبدو كأنه `7`، أو `4` مفتوحة فتبدو كأنها `9`، أو `3` متصلة فتبدو كأنها `8`). إذا كان الرقم المكتوب هو ({student_serial}) أو محاولة واضحة لكتابته بخط يد غير دقيق، اعتمد نسبة التدوين المحسوبة كاملة، وأضف في نهاية التقرير سطراً: "تنبيه إداري: خط الرقم التسلسلي ({student_serial}) غير واضح تماماً في بعض الهوامش، يرجى كتابته بخط أوضح وأكبر."
                                           - **إيداع حالة الغش في الفقرة الأخيرة من التحليل (عند ثبوت رقم مخالف):** فقط إذا ثبت بوضوح ويقين تام أن الرقم التسلسلي المكتوب في الصفحات لا يطابق ({student_serial}) بل يطابق رقماً تسلسلياً لتلميذ آخر (من اللائحة أعلاه أو رقماً مختلفاً بوضوح)، أضف في **الفقرة الأخيرة من التقرير** فقرة مستقلة بعنوان:
                                             **ثالثاً: إشعار حالة غش وعدم تطابق الهوية**
                                             توضح فيها الرقم التسلسلي المخالف الذي تم رصده في الصفحات واسم التلميذ صاحب ذلك الرقم (إن وُجد في اللائحة أعلاه)، وتقرر بناءً عليه إلغاء النسبة ومنح **0%**.
                                        5. **هيكلة التقرير الإلزامية:**
                                           - **أولاً: الفقرات والتمارين المدونة بشكل سليم**
                                           - **ثانياً: الملاحظات والنواقص (فقرات ناقصة من المرجع أو أسئلة تمارين لم يُكتب تصحيحها)**
                                           - **ثالثاً: إشعار حالة غش وعدم تطابق الهوية** (تُكتب هذه الفقرة الأخيرة فقط إذا ثبت تطابق الرقم التسلسلي في الصفحات مع رقم مخالف غير {student_serial}، وتُجعل النسبة النهائية 0%).
                                        6. اختم التقرير في آخر سطر حصرياً بدون أي نجمات أو تنسيق عريض بالصيغة الحرفية التالية (مع إجبارية وضع علامة %):
                                           النسبة النهائية: X%
                                        """
                                        
                                        api_keys_list = get_all_api_keys()
                                        models_to_try = ["gemini-3.8-flash", "gemini-2.5-flash"]
                                        
                                        response_success = False
                                        report_text = ""
                                        last_error_msg = ""
                                        
                                        for current_key in api_keys_list:
                                            genai.configure(api_key=current_key)
                                            for model_name in models_to_try:
                                                try:
                                                    model = genai.GenerativeModel(model_name)
                                                    content_payload = [prompt_instructions] + optimized_images
                                                    res = model.generate_content(
                                                        content_payload,
                                                        request_options={"timeout": 120}
                                                    )
                                                    report_text = res.text
                                                    response_success = True
                                                    break
                                                except Exception as api_err:
                                                    err_str = str(api_err)
                                                    last_error_msg = err_str
                                                    if "no longer available" in err_str or "not found" in err_str or "404" in err_str:
                                                        continue
                                                    elif any(code in err_str for code in ["429", "ResourceExhausted", "quota"]):
                                                        break
                                                    else:
                                                        time.sleep(3)
                                            if response_success:
                                                break
                                        
                                        if not response_success:
                                            st.error(f"🚨 تعذر إتمام التحليل بجميع المفاتيح المتوفرة. آخر خطأ: {last_error_msg}")
                                            st.stop()
                                            
                                        calculated_percentage = extract_percentage_from_report(report_text)

                                        live_sh.append_row([
                                            datetime.now().strftime("%Y-%m-%d"),          # A (التاريخ)
                                            student_massar.upper(),                       # B (رقم مسار)
                                            student_name,                                 # C (الاسم)
                                            st.session_state.user['class'],               # D (القسم)
                                            l_name,                                       # E (الدرس)
                                            report_text,                                  # F (التقرير)
                                            hashes_to_save,                               # G (بصمات_الصور)
                                            calculated_percentage                         # H (النسبة)
                                        ])
                                        
                                        st.cache_data.clear()
                                        
                                        if calculated_percentage == "0%":
                                            st.error("🚨 تم رصد حالة غش / عدم تطابق الرقم التسلسلي في الفقرة الأخيرة من التقرير وتسجيل نسبة 0%!")
                                        else:
                                            st.success(f"تم تدقيق التدوين بنجاح! نسبة إنجازك للدرس هي: {calculated_percentage} ✅")
                                            
                                        st.rerun() 
                                        
                                    except Exception as gemini_err:
                                        st.error(f"❌ حدث خطأ غير متوقع أثناء معالجة الدفتر: {gemini_err}")
                        else:
                            st.warning("⚠️ المرجو تزويد المنصة بصور الدفتر أولاً.")                        

# --- توزيع مسارات العرض ---
if st.session_state.role == "student":
    student_space(df_students, df_reports, df_lessons)
elif st.session_state.role == "admin":
    if not st.session_state.auth:
        st.markdown("<div class='section-title'>🔑 فضاء الأستاذ والإدارة التربوية</div>", unsafe_allow_html=True)
        admin_pwd = st.text_input("الرجاء إدخال كلمة سر الولوج الإدارية المخصصة:", type="password")
        if st.button("تأكيد الهوية 👨‍🏫", use_container_width=True):
            try:
                if admin_pwd == st.secrets["credentials"]["prof_password"]:
                    st.session_state.auth = True
                    st.session_state.user = {"name": "الأستاذ عبد الباسط المنصوري"}
                    st.success("مرحباً بك يا أستاذ!")
                    st.rerun()
                else: st.error("❌ رمز المرور الإداري غير صحيح.")
            except KeyError:
                st.error("⚙️ خطأ في النظام في لوحة التحكم.")
    else: 
        admin_space(df_students, df_reports, df_lessons)
