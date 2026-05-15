import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. الإعدادات والربط السحابي ---
genai.configure(api_key="AIzaSyAwhWzEseoWORwT8eBLWBNB57wkuFxaBeA")

def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

def load_data():
    client = get_gspread_client()
    sh = client.open("les classes")
    df_students = pd.DataFrame(sh.sheet1.get_all_records())
    try:
        df_reports = pd.DataFrame(sh.worksheet("Reports").get_all_records())
    except:
        df_reports = pd.DataFrame(columns=["التاريخ", "الاسم", "القسم", "الدرس", "التقرير", "النسبة"])
    return df_students, df_reports

# --- 2. واجهة الأستاذ الكاملة ---
def admin_space(df_students, df_reports):
    st.markdown("<h1 style='color: #1e3a8a;'>👨‍🏫 لوحة تحكم الأستاذ المنصوري</h1>", unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 الإحصائيات", "📚 إدارة المراجع", "👥 تتبع التلاميذ", "⚙️ الإعدادات"])
    
    with tab1:
        st.subheader("تحليل النشاط العام")
        col1, col2, col3 = st.columns(3)
        col1.metric("إجمالي التلاميذ", len(df_students))
        col2.metric("إجمالي الإرسالات", len(df_reports))
        col3.metric("الأقسام النشطة", df_students['القسم'].nunique())
        
        if not df_reports.empty:
            fig = px.bar(df_reports.groupby('القسم').size().reset_index(name='العدد'), x='القسم', y='العدد', title="تفاعل الأقسام")
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("رفع الدروس المرجعية (Model)")
        lesson_choice = st.selectbox("اختر الدرس لتحديث مرجعه:", ["الدرس 1", "الدرس 2", "الدرس 3"])
        ref_files = st.file_uploader(f"ارفع صور درس الأستاذ المرجعي لـ {lesson_choice}:", accept_multiple_files=True, type=['jpg','png','pdf'])
        ref_note = st.text_area("ملاحظات إضافية للذكاء الاصطناعي حول هذا الدرس:")
        if st.button("حفظ وتحديث المرجع"):
            st.session_state[f"ref_img_{lesson_choice}"] = ref_files
            st.session_state[f"ref_note_{lesson_choice}"] = ref_note
            st.success(f"تم تحديث مرجع {lesson_choice} بنجاح ✅")

    with tab3:
        st.subheader("البحث عن تلميذ")
        search_name = st.selectbox("اختر التلميذ لرؤية تاريخه:", df_students['اسم التلميذ'].unique())
        student_history = df_reports[df_reports['الاسم'] == search_name]
        st.table(student_history)

    with tab4:
        st.subheader("إدارة المنصة")
        if st.button("تصفير سجل التقارير (حذف الكل)"):
            st.warning("يرجى حذف الصفوف يدوياً من ملف Google Sheets حالياً لضمان الأمان.")

# --- 3. واجهة التلميذ الكاملة ---
def student_space(df_students):
    st.markdown("<h2 style='text-align: center;'>📝 فضاء التلميذ</h2>", unsafe_allow_html=True)
    
    if 'student_auth' not in st.session_state:
        # تسجيل الدخول
        with st.container():
            c1, c2 = st.columns(2)
            sel_class = c1.selectbox("القسم:", ["---"] + df_students['القسم'].unique().tolist())
            names = df_students[df_students['القسم'] == sel_class]['اسم التلميذ'].tolist() if sel_class != "---" else []
            sel_name = c2.selectbox("الاسم:", ["---"] + names)
            pwd = st.text_input("رقم مسار (القن السري):", type="password")
            
            if st.button("دخول"):
                real_pwd = df_students[df_students['اسم التلميذ'] == sel_name]['رقم التلميذ'].values[0]
                if str(pwd).strip() == str(real_pwd).strip():
                    st.session_state.student_auth = True
                    st.session_state.user = {"name": sel_name, "class": sel_class}
                    st.rerun()
                else:
                    st.error("❌ القن السري غير صحيح")
    else:
        # فضاء الرفع
        st.success(f"مرحباً {st.session_state.user['name']} | قسم: {st.session_state.user['class']}")
        
        lesson_tabs = st.tabs(["📘 الدرس 1", "📗 الدرس 2", "📙 الدرس 3"])
        
        for i, tab in enumerate(lesson_tabs):
            with tab:
                l_name = f"الدرس {i+1}"
                st.write(f"ارفع صور {l_name} (الحد الأقصى 20 صورة)")
                up_files = st.file_uploader(f"اختر الصور لـ {l_name}", accept_multiple_files=True, key=f"up_{l_name}")
                
                if st.button(f"تحليل وإرسال {l_name}", key=f"btn_{l_name}"):
                    if up_files:
                        with st.spinner("جاري التحليل..."):
                            # منطق Gemini
                            model = genai.GenerativeModel("gemini-2.5-flash")
                            imgs = [Image.open(f) for f in up_files]
                            res = model.generate_content([f"حلل صور هذا الدرس للتلميذ وقارنه بمرجع الأستاذ للدرس {l_name}", *imgs])
                            
                            # حفظ في جوجل شيت
                            client = get_gspread_client()
                            sh = client.open("les classes").worksheet("Reports")
                            sh.append_row([datetime.now().strftime("%Y-%m-%d"), st.session_state.user['name'], st.session_state.user['class'], l_name, res.text, "80%"])
                            
                            st.info(res.text)
                            st.success("تم الحفظ في سجلات الأستاذ ✅")

# --- 4. تشغيل التطبيق ---
st.set_page_config(page_title="منصة الأستاذ المنصوري", layout="wide")
df_students, df_reports = load_data()

# القائمة الجانبية للتنقل
menu = st.sidebar.radio("انتقل إلى:", ["🏠 فضاء التلميذ", "🔑 فضاء الأستاذ"])

if menu == "🏠 فضاء التلميذ":
    student_space(df_students)
elif menu == "🔑 فضاء الأستاذ":
    admin_pwd = st.sidebar.text_input("كلمة سر الإدارة:", type="password")
    if admin_pwd == "1234": # غيرها لاحقاً
        admin_space(df_students, df_reports)
    else:
        st.sidebar.warning("يرجى إدخال كلمة سر الأستاذ")