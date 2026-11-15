# --- داخل واجهة التلميذ (student_space) عند عرض التقارير السابقة أو الجديدة ---
                if l_name in submitted_lessons:
                    current_p = lesson_percentages.get(l_name, "N/A")
                    st.warning(f"🔒 **هذا الدرس مقفول:** لقد قمت بإرسال صور {l_name} مسبقاً بنجاح وتم تسجيل تقريرك (النسبة: {current_p}).")
                    
                    # عرض التقرير المفصل للتلميذ داخل صندوق منسدل واضح وموسع
                    with st.expander("📄 اضغط هنا لعرض تقرير التصحيح المفصل والملاحظات الخاصة بك", expanded=True):
                        st.markdown(f"""
                        <div style='background-color: #f8fafc; padding: 20px; border-radius: 10px; border: 1px solid #cbd5e1; color: #1e293b;'>
                            <h4>📊 نتيجة التدقيق: <b>{current_p}</b></h4>
                            <hr>
                            <p style='white-space: pre-wrap; line-height: 1.6;'>{lesson_full_reports.get(l_name, "لا يوجد نص تقرير محفوظ.")}</p>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # (باقي كود رفع الصور وإرسالها للتدقيق...)
