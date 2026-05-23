import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import time
import base64
import re  
import hashlib 

# --- 1. الإعدادات الأولية وإضفاء الطابع الاحترافي للوزارة ---
st.set_page_config(
    page_title="منصة ذ عبد الباسط منصوري", 
    layout="wide",
    page_icon="math🇲🇦"
)

# دالة الخلفية السحابية المحدثة
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
        background-color: rgba(26, 54, 93, 0.05);
        border-right: 5px solid #10b981;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
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

def upload_pdf_to_drive(file_name, file_bytes):
    try:
        creds = get_gcp_credentials()
        drive_service = build('drive', 'v3', credentials=creds)
        SHARED_FOLDER_ID = "1SwrvnMPTYLPSiV4B3Lyr6TiDCpurx_24"
        file_metadata = {'name': file_name, 'parents': [SHARED_FOLDER_ID]}
        fh = io.BytesIO(file_bytes)
        media = MediaIoBaseUpload(fh, mimetype='application/pdf', resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink', supportsAllDrives=True).execute()
        return file.get('webViewLink')
    except:
        return "N/A"

def calculate_image_hash(file_bytes):
    return hashlib.md5(file_bytes).hexdigest()

@st.cache_data(ttl=2) # تقليل مدة الكاش للتحديث الفوري بعد الحذف
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
            df_students = pd.DataFrame(columns=["رقم التلميذ", "اسم التلميذ", "تاريخ الإزدياد", "القسم"])
    except:
        df_students = pd.DataFrame(columns=["رقم التلميذ", "اسم التلميذ", "تاريخ الإزدياد", "القسم"])

    try:
        reports_worksheet = sh.worksheet("Reports")
        reports_rows = reports_worksheet.get_all_values()
        if reports_rows and len(reports_rows) > 1:
            reports_headers = [h.strip() for h in reports_rows[0]]
            df_reports = pd.DataFrame(reports_rows[1:], columns=reports_headers)
            df_reports.columns = df_reports.columns.str.strip()
            
            for col in df_reports.columns:
                if col in ["إسم", "اسم", "اسم التلميذ", "إسم التلميذ"]:
                    df_reports = df_reports.rename(columns={col: "الاسم"})
        else:
            df_reports = pd.DataFrame(columns=["التاريخ", "رقم مسار", "الاسم", "القسم", "الدرس", "التقرير", "النسبة", "بصمات_الصور", "بصمة_الخط"])
    except:
        df_reports = pd.DataFrame(columns=["التاريخ", "رقم مسار", "الاسم", "القسم", "الدرس", "التقرير", "النسبة", "بصمات_الصور", "بصمة_الخط"])
        
    try:
        lessons_worksheet = sh.worksheet("Lessons")
        lessons_rows = lessons_worksheet.get_all_values()
        if lessons_rows and len(lessons_rows) > 1:
            lessons_headers = [h.strip() for h in lessons_rows[0]]
            df_lessons = pd.DataFrame(lessons_rows[1:], columns=lessons_headers)
            df_lessons.columns = df_lessons.columns.str.strip()
        else:
            df_lessons = pd.DataFrame(columns=["الدرس", "الملاحظات_المرجعية", "تاريخ_التحديث"])
    except:
        df_lessons = pd.DataFrame(columns=["الدرس", "الملاحظات_المرجعية", "تاريخ_التحديث"])
        
    return df_students, df_reports, df_lessons

df_students, df_reports, df_lessons = load_data()

def get_lesson_ref(lesson_name, df_lessons):
    DRIVE_LINKS = {
        "الدرس 1": "https://drive.google.com/file/d/1WiHUq1rTQPX-VdzKvB6BT50K_vP3ZaQt/view?usp=sharing",
        "الدرس 2": "https://drive.google.com/file/d/1XMLhrjUkjzTQuUYKqNGj-BslSFSztKyz/view?usp=sharing",
        "الدرس 3": "" 
    }
    clean_name = lesson_name.strip()
    if clean_name in DRIVE_LINKS and DRIVE_LINKS[clean_name] != "":
        return f"🔗 رابط ملف الدرس المرجعي الثابت المعتمد في Google Drive:\n{DRIVE_LINKS[clean_name]}"
    if not df_lessons.empty and "الدرس" in df_lessons.columns:
        clean_target = clean_name.replace(" ", "")
        for _, row in df_lessons.iterrows():
            clean_db_name = str(row["الدرس"]).strip().replace(" ", "")
            if clean_target in clean_db_name or clean_db_name in clean_target:
                return row["الملاحظات_المرجعية"]
    return "لا توجد ملاحظات مرجعية ثابتة محددة لهذا الدرس من طرف الأستاذ."

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
            st.info(f"🏫 القسم: {st.session_state.user.get('class')}")
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
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 لوحة الإحصائيات", "📂 إضافة ورفع الدروس المرجعية", "👥 تتبع سجلات التلاميذ وتصفيرها", "⚙️ الإعدادات"])
    
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
        st.markdown("<div class='section-title'>📂 مركز إدارة المراجع السحابية</div>", unsafe_allow_html=True)
        lesson_choice = st.selectbox("اختر الدرس المستهدف بالتحديث أو الإضافة:", ["الدرس 1", "الدرس 2", "الدرس 3"])
        current_ref = get_lesson_ref(lesson_choice, df_lessons)
        st.info(f"📋 المرجع الحالي المحفوظ سحابياً للدرس:\n\n{current_ref}")
        
        uploaded_ref_file = st.file_uploader(f"📸 📤 ارفع ملف الدرس المرجعي الرسمي:", type=['pdf', 'jpg', 'jpeg', 'png'], key="admin_file_uploader")
        ref_note = st.text_area("أدخل عناصر الدرس الأساسية أو التوجيهات المكتوبة للذكاء الاصطناعي:", height=120, value=current_ref if "لا توجد ملاحظات" not in current_ref else "")

        if st.button("💾 حفظ ونشر الدرس في المنصة بشكل دائم", use_container_width=True):
            with st.spinner("جاري التحديث..."):
                drive_link = ""
                if uploaded_ref_file is not None:
                    drive_link = upload_pdf_to_drive(f"{lesson_choice}_{uploaded_ref_file.name}", uploaded_ref_file.read())
                
                full_reference_text = f"{ref_note}\n\n🔗 رابط ملف الدرس المرجعي الثابت in Google Drive:\n{drive_link}" if drive_link else ref_note
                
                try:
                    client = get_gspread_client()
                    sh = client.open("les classes")
                    ws_lessons = sh.worksheet("Lessons")
                    all_vals = ws_lessons.get_all_values()
                    headers = all_vals[0] if all_vals else ["الدرس", "الملاحظات_المرجعية", "تاريخ_التحديث"]
                    rows = all_vals[1:] if all_vals else []
                    
                    updated = False
                    for row in rows:
                        if row and row[0].strip() == lesson_choice.strip():
                            row[1] = full_reference_text
                            row[2] = datetime.now().strftime("%Y-%m-%d %H:%M")
                            updated = True
                            break
                    if not updated: rows.append([lesson_choice, full_reference_text, datetime.now().strftime("%Y-%m-%d %H:%M")])
                    ws_lessons.clear()
                    ws_lessons.update([headers] + rows)
                    st.cache_data.clear()
                    st.success(f"🎉 تم تحديث سجل المرجع بنجاح!")
                except Exception as ex:
                    st.error(f"خطأ أثناء تحديث الإكسيل: {ex}")
                st.rerun()

    with tab3:
        st.markdown("<div class='section-title'>👥 تتبع وتقارير التلاميذ الحالية</div>", unsafe_allow_html=True)
        if not df_reports.empty:
            st.dataframe(df_reports, use_container_width=True)
        else:
            st.info("لا توجد تقارير مرسلة حالياً.")
            
        st.divider()
        
        st.markdown("<div class='section-title'>🗑️ لوحة الإلغاء والتصفير (منح فرصة ثانية للتلميذ)</div>", unsafe_allow_html=True)
        st.write("يمكنك من هنا اختيار تلميذ معين لحذف تقاريره من قاعدة البيانات ليعيد المحاولة والإرسال:")
        
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
                target_lesson_to_reset = st.selectbox("3️⃣ حدد النطاق المراد حذفه وتصفيره:", ["كل الدروس", "الدرس 1", "الدرس 2", "الدرس 3"], key="reset_lesson_select")
                
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
                                    st.success(f"✅ تم بنجاح تصفير وحذف ({deleted_count}) سجل للتلميذ. يمكنه الآن الدخول والإرسال من جديد بكل حرية!")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("الجدول فارغ بالفعل.")
                            except Exception as reset_err:
                                st.error(f"حدث خطأ أثناء محاولة التصفير السحابي: {reset_err}")
        else:
            st.info("لا توجد بيانات كافية في السجلات لتفعيل ميزة التصفير.")

    with tab4:
        st.markdown("<div class='section-title'>⚙️ إعدادات الصيانة والأمان</div>", unsafe_allow_html=True)
        st.info("تم دمج نظام التصفير التلقائي الذكي أعلاه ليوفر عليك عناء الحذف اليدوي من Google Sheets.")

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

    if not st.session_state.auth:
        st.markdown("<div class='section-title'>🔑 تسجيل الدخول الآمن لمنظومة التدقيق</div>", unsafe_allow_html=True)
        sel_class = st.selectbox("الرجاء تحديد قسمك الفعلي:", ["---"] + df_students[col_class].unique().tolist())
        col_input1, col_input2 = st.columns(2)
        input_massar = col_input1.text_input("أدخل رقم مسار الخاص بك:").strip()
        input_birth = col_input2.text_input("أدخل تاريخ ازديادك الموثق (سنة-شهر-يوم):").strip()
        
        if st.button("التحقق والولوج الآمن للمنصة 🚀", use_container_width=True):
            if sel_class != "---" and input_massar and input_birth:
                df_students[col_id] = df_students[col_id].astype(str).str.strip()
                df_students[col_birth] = df_students[col_birth].astype(str).str.strip()
                
                matched_student = df_students[
                    (df_students[col_class] == sel_class) & 
                    (df_students[col_id].str.upper() == input_massar.upper()) & 
                    (df_students[col_birth] == input_birth)
                ]
                if not matched_student.empty:
                    st.session_state.auth = True
                    st.session_state.user = {
                        "name": str(matched_student.iloc[0][col_name]).strip(), 
                        "class": sel_class,
                        "massar": input_massar.strip().upper()
                    }
                    st.success("🎉 تم التحقق من الهوية بنجاح!")
                    st.rerun()
                else:
                    st.error("❌ عذراً، المعلومات المدخلة غير متطابقة.")
    else:
        student_name = st.session_state.user['name']
        student_massar = st.session_state.user.get('massar', '')
        st.success(f"🏫 مرحباً بالتلميذ(ة): **{student_name}** | رقم مسار: **{student_massar}** | القسم: **{st.session_state.user['class']}**")
        
        student_all_submissions = pd.DataFrame()
        if not df_reports.empty and 'رقم مسار' in df_reports.columns:
            df_reports['massar_clean'] = df_reports['رقم مسار'].astype(str).str.strip().str.upper()
            df_reports['الدرس_نظيف'] = df_reports['الدرس'].astype(str).str.strip()
            student_all_submissions = df_reports[df_reports['massar_clean'] == student_massar.upper()]
            
        submitted_lessons = student_all_submissions['الدرس_نظيف'].tolist() if not student_all_submissions.empty else []
        
        lesson_percentages = {}
        lesson_full_reports = {}
        if not student_all_submissions.empty:
            for _, row in student_all_submissions.iterrows():
                l_clean = str(row['الدرس_نظيف'])
                lesson_percentages[l_clean] = str(row['النسبة']).strip()
                lesson_full_reports[l_clean] = row['التقرير']
        
        st.markdown("<div class='section-title'>📊 وضعيتك الحالية في السجل الرقمي:</div>", unsafe_allow_html=True)
        
        if len(submitted_lessons) > 0:
            status_text = "📢 <b>حالة إرسال الفروض والدفاتر:</b><br>"
            for l_sub in ["الدرس 1", "الدرس 2", "الدرس 3"]:
                if l_sub in submitted_lessons:
                    pct = lesson_percentages.get(l_sub, "N/A")
                    if pct == "0%":
                        status_text += f"🚨 تم تدقيق <b>{l_sub}</b> وتم رصد <b>مخالفة/تكرار صور أو محتوى مأخوذ من زميل آخر</b> (النسبة: <span style='color:white; background:red; padding:2px 6px; border-radius:4px;'><b>0%</b></span>)<br>"
                    else:
                        status_text += f"📉 نسبة إنجازك لـ <b>{l_sub}</b> هي: <span style='color:#e0f2fe; background:#1e3a8a; padding:2px 8px; border-radius:5px;'><b>{pct}</b></span><br>"
            st.markdown(f"<div class='status-box'>{status_text}</div>", unsafe_allow_html=True)
        else:
            st.warning("لم تقم بإرسال أي دروس بعد. المرجو اختيار الدرس من التبويبات أسفله ورفع 13 صورة على الأقل.")

        lesson_tabs = st.tabs(["📘 المجزوءة / الدرس 1", "📗 المجزوءة / الدرس 2", "📙 المجزوءة / الدرس 3"])
        
        for i, tab in enumerate(lesson_tabs):
            with tab:
                l_name = f"الدرس {i+1}"
                
                if l_name in submitted_lessons:
                    current_p = lesson_percentages.get(l_name, "N/A")
                    
                    if current_p == "0%":
                        st.error(f"🚨 **تنبيه نظام التدقيق والنزاهة الرقمية:**")
                        st.markdown(f"<div style='background-color:#fee2e2; border-right:6px solid #dc2626; padding:15px; border-radius:8px; color:#991b1b; font-weight:bold;'>⚠️ لقد تم رفض هذا الإرسال وحصلت على نسبة 0% بسبب رصد تكرار بصرى أو تطابق خط الكتابة والمحتوى مع تلميذ آخر بالمؤسسة.</div>", unsafe_allow_html=True)
                        st.markdown(f"### 📋 تفاصيل تقرير المخالفة المحفوظ إدارياً وتوبيخ الذكاء الاصطناعي:")
                        st.info(lesson_full_reports.get(l_name, "لا يوجد نص تقرير محفوظ."))
                    else:
                        st.warning(f"ℹ️ **لقد أرسلت صور {l_name} مسبقاً** بنجاح، ونسبة إنجازك المحفوظة هي: **{current_p}**.")
                        st.markdown(f"### 📋 تقرير التدقيق المخزن لـ {l_name}:")
                        st.info(lesson_full_reports.get(l_name, "لا يوجد نص تقرير محفوظ."))
                
                else:
                    st.markdown(f"#### 📸 centre de dépôt des cahiers - {l_name}")
                    saved_lesson_reference = get_lesson_ref(l_name, df_lessons)
                    
                    up_files = st.file_uploader(
                        f"اختر صور صفحات الدفتر لـ {l_name} (🚨 تنبيه: يشترط تحميل 13 صورة على الأقل)", 
                        accept_multiple_files=True, 
                        key=f"up_{l_name}", 
                        type=['jpg','jpeg','png']
                    )
                    
                    if st.button(f"بدء المعالجة والتدقيق الفوري لـ {l_name}", key=f"btn_{l_name}"):
                        if up_files:
                            if len(up_files) < 13:
                                st.error(f"⚠️ **خطأ في معايير قبول الدفتر:** لقد قمت برفع ({len(up_files)}) صور فقط! ميثاق المادة يشترط رفع **14 صورة على الأقل** للدرس لضمان تدقيق المحتوى كاملاً.")
                            else:
                                with st.spinner("🔄 جاري التحقق الفوري من سجلاتك وفحص جودة الصور..."):
                                    current_hashes = []
                                    for f in up_files:
                                        f_bytes = f.read()
                                        f.seek(0)
                                        current_hashes.append(calculate_image_hash(f_bytes))
                                    
                                    try:
                                        client = get_gspread_client()
                                        live_sh = client.open("les classes").worksheet("Reports")
                                        live_rows = live_sh.get_all_values()
                                        
                                        if live_rows and len(live_rows) > 1:
                                            live_headers = [h.strip() for h in live_rows[0]]
                                            df_live_reports = pd.DataFrame(live_rows[1:], columns=live_headers)
                                            df_live_reports.columns = df_live_reports.columns.str.strip()
                                            for col in df_live_reports.columns:
                                                if col in ["اسم", "إسم", "اسم التلميذ", "إسم التلميذ"]:
                                                    df_live_reports = df_live_reports.rename(columns={col: "الاسم"})
                                        else:
                                            df_live_reports = pd.DataFrame(columns=["التاريخ", "رقم مسار", "الاسم", "القسم", "الدرس", "التقرير", "النسبة", "بصمات_الصور", "بصمة_الخط"])
                                    except Exception as check_err:
                                        st.error(f"❌ تعذر الاتصال بالسيرفر للتحقق من الأرشيف: {check_err}")
                                        st.stop()
                                
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
                                        f"لا يمكن لتلميذين إرسال نفس صور الدفتر! تم رصد محاولة التكرار وإلغاء العملية."
                                    )
                                else:
                                    with st.spinner("🔄 جاري قياس نسبة الإنجاز والتحقق من أصالة خط الكتابة مع الأرشيف..."):
                                        try:
                                            # بناء سياق أرشيف بصمات الخطوط السابقة لنفس الدرس لمنع التحايل بتصوير نفس الدفتر
                                            past_records_context = ""
                                            if not df_live_reports.empty and 'الدرس' in df_live_reports.columns and 'بصمة_الخط' in df_live_reports.columns:
                                                same_lesson_df = df_live_reports[df_live_reports['الدرس'] == l_name]
                                                for idx, row in same_lesson_df.iterrows():
                                                    if str(row.get('massar_clean', '')).strip().upper() != student_massar.upper():
                                                        past_records_context += f"- التلميذ(ة): {row.get('الاسم', 'مجهول')} | بصمة خطه الموثقة: {row.get('بصمة_الخط', 'لا يوجد')}\n\n"

                                            prompt_instructions = f"""
                                            أنت مساعد أستاذ الرياضيات عبد الباسط منصوري بالثانوية التأهلية المغربية. 
                                            التلميذ {student_name} (القسم: {st.session_state.user['class']}) أرسل صور دفتره لدرس ({l_name}).
                                            
                                            المرجع والمخطط الملزم الذي حدده الأستاذ لك هو:
                                            \"\"\"{saved_lesson_reference}\"\"\"
                                            
                                            ⚠️ أرشيف بصمات الخطوط للتلاميذ الآخرين الذين أرسلوا قبله لنفس الدرس:
                                            \"\"\"{past_records_context}\"\"\"
                                  
                                            🚨 معيار صارم وحاسم ضد الغش والتحايل (تصوير نفس الدفتر الفعلي بهاتف آخر):
                                            1. افحص الصور الحالية واستخرج "بصمة بصرية فريدة للخط والكتابة والتنسيق" في سطرين (تصف خصائص الخط، ألوان الأقلام، الرموز الرياضية، طريقة التسطير، وعيوب فريدة بالدفتر).
                                            
                                            2. قارن هذه الصور الحالية بـ "أرشيف بصمات الخطوط للتلاميذ الآخرين" المرفق بالأعلى. إذا وجدت تطابقاً بصرياً تاماً (أي أن هذه الصور تعود لنفس الدفتر المكتوب الذي استعمله تلميذ آخر سابقاً بالمؤسسة، والتلميذ الحالي يقوم فقط بإعادة تصوير الدفتر بهاتفه من زوايا أخرى للتحايل وسرقة مجهود صديقه)، فنفذ ما يلي فوراً:
                                               - اكتب تقريراً حازماً وتوبيخياً تخبره فيه بأنه تم رصد سرقة دفتر مجهود تلميذ آخر ومخالفة ميثاق المادة والنزاهة الإدارية.
                                               - ضع النسبة هكذا في السطر الأخير تماماً وبشكل حتمي:
                                               النسبة النهائية: 0%
                                            
                                            3. إذا كانت الصور سليمة، مختلفة، وفريدة لدفتر التلميذ الخاص به:
                                               - تفقد العناوين والفقرات والتمارين المكتوبة بدقة  سطرا بسطر وقارنها بالدرس المرجعي.
                                               - احسب بدقة "نسبة مئوية تقديرية" لإنجاز التلميذ لكتابة الدرس وحل التمارين.
                                               - صغ تقريراً تربوياً مشجعاً وموجزاً باللغة العربية.
                                               - يجب أن تنهي تقريرك بكتابة هذه العبارة بالنص في السطر الأخير تماماً:
                                               النسبة النهائية: X%
                                               
                                            🚨 شرط برمجي إلزامي للتخزين المستقبلي: أضف دائماً في سطر مستقل في نهاية ردك العبارة التالية:
                                            بصمة الخط المستخرجة حالياً: [ضع هنا الوصف البصري الدقيق جدا الفريد المستخرج للخط والتنسيق لكل الصور]
                                            """
                                            
                                            model = genai.GenerativeModel("gemini-2.5-flash")
                                            imgs = [Image.open(f) for f in up_files]
                                            
                                            response_success = False
                                            report_text = ""
                                            
                                            # --- الحماية المحصنة والذكية ضد توقف السيرفر والضغط اللحظي Rate Limits ---
                                            for retry_attempt in range(3):
                                                try:
                                                    res = model.generate_content([prompt_instructions, *imgs])
                                                    report_text = res.text
                                                    response_success = True
                                                    break
                                                except Exception as api_err:
                                                    if "429" in str(api_err) or "ResourceExhausted" in str(api_err):
                                                        st.warning(f"⚠️ الخادم ذو ضغط عالٍ حالياً بسبب إرسالات التلاميذ. محاولة إعادة الاتصال الذكي رقم ({retry_attempt + 1}/3)...")
                                                        time.sleep(15)
                                                    else:
                                                        raise api_err
                                            
                                            if not response_success:
                                                st.error("🚨 خادم الفحص السحابي لـ Google غير مستقر حالياً بسبب كثرة الضغط. يرجى إعادة الضغط على الزر بعد ثوانٍ قليلة.")
                                                st.stop()
                                                
                                            calculated_percentage = "100%"
                                            match_pct = re.search(r"النسبة\s+النهائية:\s*(\d+%)", report_text)
                                            if match_pct: calculated_percentage = match_pct.group(1)

                                            extracted_handwriting_profile = "خط قياسي غير مصنف."
                                            match_profile = re.search(r"بصمة الخط المستخرجة حالياً:\s*(.*)", report_text)
                                            if match_profile: extracted_handwriting_profile = match_profile.group(1).strip()

                                            hashes_to_save = ",".join(current_hashes)

                                            live_sh.append_row([
                                                datetime.now().strftime("%Y-%m-%d"),          # A: التاريخ
                                                student_massar.upper(),                       # B: رقم مسار
                                                student_name,                                 # C: الاسم
                                                st.session_state.user['class'],               # D: القسم
                                                l_name,                                       # E: الدرس
                                                report_text,                                  # F: التقرير
                                                calculated_percentage,                        # G: النسبة
                                                hashes_to_save,                               # H: بصمات_الصور
                                                extracted_handwriting_profile                 # I: بصمة_الخط للأرشيف
                                            ])
                                            
                                            st.cache_data.clear()
                                            
                                            if calculated_percentage == "0%":
                                                st.error("🚨 تم رفض الملف وتسجيل نسبة 0% بسبب رصد مخالفة في المحتوى المرفوع!")
                                            else:
                                                st.success(f"تم حفظ التقرير بنجاح! نسبة الإنجاز المسجلة للأستاذ: {calculated_percentage} ✅")
                                                
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
