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

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error("⚠️ لم يتم العثور على مفتاح 'GEMINI_API_KEY'.")

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

# دالة محصّنة لاستخراج النسبة المئوية بدقة مهما كان تنسيق الذكاء الاصطناعي (عريض، مسافات، إلخ)
def extract_percentage_from_report(report_str):
    text = str(report_str)
    # 1. البحث عن "النسبة النهائية" مع السماح بوجود نجمات ** أو مسافات قبل/بعد النقطتين وعلامة %
    match_pct = re.search(r"النسبة\s+النهائية[\s\*]*:[\s\*]*(\d+)\s*%", text)
    if match_pct:
        return f"{match_pct.group(1)}%"
    
    # 2. خطة بديلة: أخذ آخر نسبة مئوية مذكورة في التقرير إذا لم يلتزم النموذج بالصيغة الحرفية
    all_pcts = re.findall(r"(\d+)\s*%", text)
    if all_pcts:
        return f"{all_pcts[-1]}%"
        
    return "0%"

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
        if lessons_rows and len(lessons_rows) > 1:
            lessons_headers = [h.strip() for h in lessons_rows[0]]
            df_lessons = pd.DataFrame(lessons_rows[1:], columns=lessons_headers)
            df_lessons.columns = df_lessons.columns.str.strip()
        else:
            df_lessons = pd.DataFrame(columns=["المستوى", "الدرس", "الملاحظات_المرجعية", "رابط_PDF", "تاريخ_التحديث"])
    except:
        df_lessons = pd.DataFrame(columns=["المستوى", "الدرس", "الملاحظات_المرجعية", "رابط_PDF", "تاريخ_التحديث"])
        
    return df_students, df_reports, df_lessons

df_students, df_reports, df_lessons = load_data()

def get_lesson_ref_and_pdf(level_name, lesson_name, df_lessons):
    clean_level = level_name.strip()
    clean_lesson = lesson_name.strip()
    if not df_lessons.empty and "المستوى" in df_lessons.columns and "الدرس" in df_lessons.columns:
        match_row = df_lessons[(df_lessons["المستوى"].str.strip() == clean_level) & (df_lessons["الدرس"].str.strip() == clean_lesson)]
        if not match_row.empty:
            note = str(match_row.iloc[0].get("الملاحظات_المرجعية", ""))
            pdf_link = str(match_row.iloc[0].get("رابط_PDF", ""))
            return note, pdf_link
    return "", ""

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
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 لوحة الإحصائيات", "📂 ربط وإدارة روابط الدروس (Google Drive)", "👥 تتبع سجلات التلاميذ وتصفيرها", "⚙️ الإعدادات"])
    
    with tab1:
        st.markdown("<div class='section-title'>📈 المؤشرات التربوية العامة</div>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1: st.markdown(f"<div class='metric-card'><p style='color:#64748b; font-weight:bold;'>إجمالي التلاميذ</p><h2 style='margin:0; color:#1a365d;'>👥 {len(df_students)}</h2></div>", unsafe_allow_html=True)
        with col2: st.markdown(f"<div class='metric-card'><p style='color:#64748b; font-weight:bold;'>الدفاتر المدققة</p><h2 style='margin:0; color:#1a365d;'>📥 {len(df_reports)}</h2></div>", unsafe_allow_html=True)
        with col3: 
            num_classes = df_students['القسم'].nunique() if not df_students.empty and 'القسم' in df_students.columns else 0
            st.markdown(f"<div class='metric-card'><p style='color:#64748b; font-weight:bold;'>الأقسام</p><h2 style='margin:0; color:#1a365d;'>🏫 {num_classes}</h2></div>", unsafe_allow_html=True)
        
        if not df_reports.empty and 'القسم' in df_reports.columns:
            fig = px.bar(df_reports.groupby('القسم').size().reset_index(name='عدد الإرسالات'), x='القسم', y='عدد الإرسالات', title="📊 تفاعل الأقسام والالتزام بالدفاتر الرقمية", color_discrete_sequence=['#1a365d'])
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.markdown("<div class='section-title'>📂 إدخال وربط روابط الدروس (Google Drive)</div>", unsafe_allow_html=True)
        
        selected_level = st.selectbox("1️⃣ اختر المستوى الدراسي:", ["جذع مشترك علوم", "أولى باكالوريا علوم (1 باك SEF)"])
        lesson_list_options = [f"الدرس {i}" for i in range(1, 13)]
        selected_lesson_num = st.selectbox("2️⃣ اختر الدرس المستهدف:", lesson_list_options)
        
        current_note, current_pdf_link = get_lesson_ref_and_pdf(selected_level, selected_lesson_num, df_lessons)
        
        st.info(f"📋 حالة الدرس في السجل الحالي:\n- المستوى: {selected_level}\n- الدرس: {selected_lesson_num}\n- الرابط الحالي: {current_pdf_link if current_pdf_link else 'لا يوجد رابط مدخل بعد'}")
        
        input_drive_link = st.text_input("3️⃣ أدخل رابط ملف الـ PDF من Google Drive هنا:", value=current_pdf_link).strip()
        ref_note = st.text_area("أدخل ملاحظات أو توجيهات إضافية للذكاء الاصطناعي (اختياري):", height=100, value=current_note).strip()

        if st.button("💾 حفظ وتحديث السجل في Google Sheets", use_container_width=True):
            if not input_drive_link:
                st.warning("⚠️ يرجى إدخال رابط صالح من Google Drive أولاً.")
            else:
                with st.spinner("جاري تحديث جدول Lessons في Google Sheets..."):
                    try:
                        client = get_gspread_client()
                        sh = client.open("les classes")
                        ws_lessons = sh.worksheet("Lessons")
                        all_vals = ws_lessons.get_all_values()
                        headers = all_vals[0] if all_vals else ["المستوى", "الدرس", "الملاحظات_المرجعية", "رابط_PDF", "تاريخ_التحديث"]
                        rows = all_vals[1:] if all_vals else []
                        
                        updated = False
                        for row in rows:
                            if len(row) >= 2 and row[0].strip() == selected_level.strip() and row[1].strip() == selected_lesson_num.strip():
                                while len(row) < 5: row.append("")
                                row[2] = ref_note
                                row[3] = input_drive_link
                                row[4] = datetime.now().strftime("%Y-%m-%d %H:%M")
                                updated = True
                                break
                        if not updated: 
                            rows.append([selected_level, selected_lesson_num, ref_note, input_drive_link, datetime.now().strftime("%Y-%m-%d %H:%M")])
                        
                        ws_lessons.clear()
                        ws_lessons.update([headers] + rows)
                        st.cache_data.clear()
                        st.success(f"🎉 تم بنجاح حفظ الرابط والملاحظات في Google Sheets لـ ({selected_lesson_num} - {selected_level})!")
                    except Exception as ex:
                        st.error(f"خطأ أثناء التحديث السحابي: {ex}")
                    st.rerun()

    with tab3:
        st.markdown("<div class='section-title'>👥 تتبع وتقارير التلاميذ الحالية</div>", unsafe_allow_html=True)
        if not df_reports.empty:
            st.dataframe(df_reports, use_container_width=True)
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
                    display_text = f"👤 {s_name} (مسار: {m_id})"
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
        st.info("تم ضبط النظام للتدقيق النسبي الدقيق وتوحيد النسبة المستخرجة بين التقرير والشريط العلوي وجدول Google Sheets.")

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
                col_h_val = str(row.get('بصمة_الخط', '')).strip()
                # إذا كانت القيمة المخزنة في العمود H صالحة وأكبر من 0% نعتمدها، وإلا نستخرجها مباشرة من نص التقرير
                if "%" in col_h_val and col_h_val != "0%":
                    lesson_percentages[l_clean] = col_h_val
                else:
                    lesson_percentages[l_clean] = extract_percentage_from_report(rep_content)
        
        st.markdown("<div class='section-title'>📊 وضعيتك الحالية في السجل الرقمي:</div>", unsafe_allow_html=True)
        
        lesson_names_12 = [f"الدرس {i}" for i in range(1, 13)]
        
        if len(submitted_lessons) > 0:
            status_text = "📢 <b>حالة إرسال الدفاتر والتدقيق:</b><br>"
            for l_sub in lesson_names_12:
                if l_sub in submitted_lessons:
                    pct = lesson_percentages.get(l_sub, "0%")
                    if pct == "0%":
                        status_text += f"🚨 تم تدقيق <b>{l_sub}</b> وتم رصد <b>مخالفة/عدم تطابق الهوية</b> (النسبة: <span style='color:white; background:#dc2626; padding:2px 8px; border-radius:4px;'><b>0%</b></span>)<br>"
                    else:
                        status_text += f"✅ نسبة تدوينك وإنجازك لـ <b>{l_sub}</b> هي: <span style='color:#ffffff; background:#1e3a8a; padding:2px 10px; border-radius:5px;'><b>{pct}</b></span><br>"
            st.markdown(f"<div class='status-box'>{status_text}</div>", unsafe_allow_html=True)
        else:
            st.warning("لم تقم بإرسال أي دروس بعد. المرجو اختيار الدرس من التبويبات أسفله ورفع 8 صور على الأقل.")

        lesson_tabs = st.tabs([f"📚 الدرس {i}" for i in range(1, 13)])
        
        for i, tab in enumerate(lesson_tabs):
            with tab:
                l_name = f"الدرس {i+1}"
                
                if l_name in submitted_lessons:
                    current_p = lesson_percentages.get(l_name, "0%")
                    if current_p == "0%":
                        st.error(f"🚨 **تنبيه نظام التدقيق والنزاهة الرقمية:**")
                        st.markdown(f"<div style='background-color:#fee2e2; border-right:6px solid #dc2626; padding:15px; border-radius:8px; color:#991b1b; font-weight:bold;'>⚠️ تم رفض هذا الإرسال وحصلت على نسبة 0% بسبب عدم مطابقة الهوية أو إرسال محتوى لا يخص الدرس.</div>", unsafe_allow_html=True)
                        st.markdown(f"### 📋 تفاصيل تقرير المخالفة المحفوظ إدارياً:")
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
                
                else:
                    st.markdown(f"#### 📸 centre de dépôt des cahiers - {l_name} ({student_level})")
                    saved_note, saved_pdf_link = get_lesson_ref_and_pdf(student_level, l_name, df_lessons)
                    
                    if saved_pdf_link:
                        st.success(f"🔗 تم رصد ملف الدرس المرجعي للأستاذ ({student_level})؛ سيتم تدقيق نقل جميع الفقرات والأمثلة والتمارين واحتساب النسبة المئوية بناءً على ما هو مكتوب في دفترك.")
                    else:
                        st.warning(f"⚠️ تنبيه: لم يقم الأستاذ بإدخال رابط PDF لهذا الدرس ({student_level}) بعد، سيتم التدقيق بناءً على المقرر الرسمي المغربي.")

                    up_files = st.file_uploader(
                        f"اختر صور صفحات الدفتر لـ {l_name} (🚨 يشترط تحميل 8 صور على الأقل مع كتابة رقمك التسلسلي '{student_serial}' في الهوامش والتأكد من نقل جميع فقرات الدرس كاملة):", 
                        accept_multiple_files=True, 
                        key=f"up_{student_level}_{l_name}", 
                        type=['jpg','jpeg','png']
                    )
                    
                    if st.button(f"بدء المعالجة وتدقيق نسبة التدوين لـ {l_name}", key=f"btn_{student_level}_{l_name}"):
                        if up_files:
                            if len(up_files) < 8:
                                st.error(f"⚠️ **خطأ في معايير قبول الدفتر:** لقد قمت برفع ({len(up_files)}) صور فقط! ميثاق المادة يشترط رفع **8 صور على الأقل** للدرس.")
                            else:
                                with st.spinner("🔄 جاري جرد فقرات الدرس المرجعي ومقارنتها مع ما تم تدوينه في دفترك..."):
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

                                cheater_detected = False
                                original_student_name = ""
                                
                                if "بصمات_الصور" in df_live_reports.columns:
                                    df_live_reports['massar_clean'] = df_live_reports['رقم مسار'].astype(str).str.strip().str.upper() if "رقم مسار" in df_live_reports.columns else ""
                                        
                                    for idx, row in df_live_reports.iterrows():
                                        if str(row['massar_clean']) == student_massar.upper():
                                            continue
                                        saved_hashes_str = str(row['بصمات_الصور']).strip()
                                        if saved_hashes_str:
                                            saved_hashes_list = saved_hashes_str.split(",")
                                            for current_h in current_hashes:
                                                if current_h in saved_hashes_list:
                                                    cheater_detected = True
                                                    original_student_name = row['الاسم'] if 'الاسم' in row else "تلميذ آخر"
                                                    break
                                        if cheater_detected: break

                                if cheater_detected:
                                    st.error(
                                        f"🚨 **نظام كشف الغش والسرقة الرقمية:** \n\n"
                                        f"عذراً، هذه الصور تم إرسالها مسبقاً من طرف التلميذ(ة): **{original_student_name}**. \n"
                                        f"لا يمكن لتلميذين إرسال نفس صور الدفتر!"
                                    )
                                else:
                                    with st.spinner("🔄 جاري احتساب الوزن النسبي لكل فقرة وتحديد النسبة المئوية الدقيقة للتدوين..."):
                                        try:
                                            prompt_instructions = f"""
                                            أنت مساعد أستاذ الرياضيات عبد الباسط منصوري بالثانوية التأهيلية المغربية. مهمتك هي **التدقيق الكمّي والنوعي لتدوين الدرس** في دفتر التلميذ(ة): {student_name}
                                            - الرقم التسلسلي الرسمي: {student_serial}
                                            - رقم مسار: {student_massar}
                                            - المستوى الدراسي: {student_level}
                                            - القسم: {st.session_state.user['class']}
                                            - الدرس المستهدف: {l_name}
                                            
                                            النص المرجعي الكامل للدرس الذي كتبه الأستاذ في السبورة (مستخرج من ملف الـ PDF):
                                            \"\"\"{pdf_reference_text[:15000]}\"\"\"

                                            توجيهات إضافية من الأستاذ:
                                            \"\"\"{saved_note}\"\"\"
                                  
                                            قواعد التدقيق وحساب النسبة المئوية (يجب الالتزام بها بدقة صارمة):
                                            1. **طبيعة التقييم (تدقيق النقل والتدوين فقط):** التلميذ(ة) ينقل ما كتبه الأستاذ في السبورة، ولم يؤلف الأمثلة أو البراهين بنفسه. **يُمنع منعاً باتاً** قول ("قدمتِ مثالاً"، "أظهرتِ فهماً"، "أبدعتِ في البرهان"). استخدم فقط عبارات تدقيق التدوين: ("تم تدوين فقرة..."، "تم نقل التمرين التطبيقي وحله..."، "لم يتم تدوين فقرة..."، "نقص في نقل...").
                                            2. **طريقة احتساب النسبة المئوية الدقيقة (من 0% إلى 100%):**
                                               - قسّم محتوى الدرس المرجعي أعلاه إلى مجموع فقراته وعناصره الأساسية (التعاريف، الخاصيات، الأمثلة، والتمارين التطبيقية وحلولها)، واعتبر مجموع الدرس يساوي 100%.
                                               - احسب بدقة وزن كل فقرة:
                                                 * كل فقرة أو تمرين نُقل بالكامل وبشكل سليم يحصل على كامل نسبته.
                                                 * كل فقرة أو تمرين نُقل ناقصاً أو به أخطاء في نسخ المعطيات/الرموز يُخصم نصف وزنه.
                                                 * كل فقرة أو مثال أو تمرين **غير مكتوب في الدفتر** يُخصم وزنه بالكامل من المجموع!
                                               - لا تعطِ 100% إلا إذا كان الدفتر يحتوي على جميع فقرات وتمارين المرجع دون أي نقص. وإذا كتب التلميذ 70% فقط من فقرات الدرس أعطه 70%، وإذا كتب 20% أو 40% أو 95% أعطه النسبة الفعلية المطابقة لما دوّنه في دفترك!
                                            3. **التحقق من الرقم التسلسلي ({student_serial}):** افحص هوامش الصفحات بحثاً عن ({student_serial}).
                                               - إذا وُجد رقم تسلسلي آخر لتلميذ آخر بوضوح، امنح 0% واذكر ذلك.
                                               - إذا كان الرقم ({student_serial}) غير واضح في التصوير أو غير مكتوب في بعض الصفحات، لا تُلغِ نسبة التدوين المحسوبة، بل أضف في نهاية التقرير سطراً: "تنبيه إداري: الرقم التسلسلي ({student_serial}) غير واضح في بعض الهوامش، يرجى إبراز كتابته في جميع الصفحات."
                                            4. **هيكلة التقرير الواضحة للتلميذ(ة):**
                                               - **أولاً: الفقرات والتمارين المدونة بشكل سليم** (مع ذكر وزنها التقريبي).
                                               - **ثانياً: الفقرات والتمارين غير المكتوبة أو الناقصة** (تحديد كل فقرة أو سؤال لم يُكتب في الدفتر وسبب الخصم من النسبة).
                                            5. اختم التقرير في آخر سطر حصرياً بدون أي نجمات أو تنسيق عريض بالصيغة الحرفية التالية:
                                               النسبة النهائية: X%
                                            """
                                            
                                            model = genai.GenerativeModel("gemini-2.5-flash")
                                            content_payload = [prompt_instructions] + optimized_images
                                            
                                            response_success = False
                                            report_text = ""
                                            
                                            for retry_attempt in range(3):
                                                try:
                                                    res = model.generate_content(
                                                        content_payload,
                                                        request_options={"timeout": 120}
                                                    )
                                                    report_text = res.text
                                                    response_success = True
                                                    break
                                                except Exception as api_err:
                                                    if any(err_code in str(api_err) for err_code in ["429", "504", "ResourceExhausted", "DeadlineExceeded"]):
                                                        st.warning(f"⚠️ الخادم مشغول، جاري إعادة المحاولة ({retry_attempt + 1}/3)...")
                                                        time.sleep(10)
                                                    else:
                                                        raise api_err
                                            
                                            if not response_success:
                                                st.error("🚨 خادم الفحص السحابي ممتلئ أو استغرق وقتاً طويلاً. يرجى المحاولة بعد قليل.")
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
                                                st.error("🚨 تم رفض الملف وتسجيل نسبة 0% بسبب عدم مطابقة الهوية أو إرسال محتوى خاطئ!")
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
