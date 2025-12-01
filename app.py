import streamlit as st
import traceback

# --- 1. CẤU HÌNH TRANG (BẮT BUỘC ĐẦU TIÊN) ---
st.set_page_config(
    page_title="Dissertation Master AI",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- BẮT ĐẦU KHỐI AN TOÀN ---
try:
    # Import các thư viện nặng
    import google.generativeai as genai
    from pypdf import PdfReader
    from docx import Document
    from io import BytesIO
    import json
    import os
    import tempfile
    import datetime
    
    # Thư viện Voice & Drive
    from streamlit_mic_recorder import mic_recorder
    from gtts import gTTS
    from pydub import AudioSegment
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
    import speech_recognition as sr

    # --- ID THƯ MỤC GỐC ---
    ROOT_FOLDER_ID = "1eojKKKoMk4uLBCLfCpVhgWnaoTtOiu8p"

    # ==========================================
    # CÁC HÀM XỬ LÝ (DRIVE, FILE, AI)
    # ==========================================
    def get_drive_service():
        if "oauth_token" not in st.secrets:
            st.error("❌ Lỗi: Chưa cấu hình 'oauth_token' trong Secrets!")
            return None
        try:
            token_info = json.loads(st.secrets["oauth_token"])
            creds = Credentials.from_authorized_user_info(token_info)
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            st.error(f"❌ Lỗi xác thực Google: {e}")
            return None

    def upload_to_drive(file_obj, filename, folder_id):
        try:
            service = get_drive_service()
            if not service: return None, "Lỗi kết nối"
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            final_filename = f"{filename.replace('.docx', '')}_{timestamp}.docx"
            file_metadata = {'name': final_filename, 'parents': [folder_id]}
            file_obj.seek(0)
            media = MediaIoBaseUpload(file_obj, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            return file.get('id'), final_filename
        except Exception as e: return None, str(e)

    def list_folders_recursive(service, parent_id):
        folders = []
        try:
            results = service.files().list(
                q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)", orderBy="name").execute()
            for item in results.get('files', []):
                folders.append({'id': item['id'], 'name': item['name']})
        except: pass
        return folders

    def list_files_in_folder(service, folder_id):
        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name, mimeType)", orderBy="name").execute()
            return results.get('files', [])
        except: return []

    def read_drive_file(service, file_id, filename, mimeType):
        try:
            file_stream = BytesIO()
            if mimeType == 'application/vnd.google-apps.document':
                request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            else:
                request = service.files().get_media(fileId=file_id)
                
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while done is False: status, done = downloader.next_chunk()
            file_stream.seek(0)
            
            if filename.endswith(".pdf") or mimeType == 'application/pdf': return get_pdf_content(file_stream)
            else: return get_docx_content(file_stream)
        except Exception as e: return f"[Lỗi đọc: {e}]"

    def get_pdf_content(f):
        try:
            reader = PdfReader(f); text = ""
            for p in reader.pages: text += p.extract_text() + "\n"
            return text
        except: return ""

    def get_docx_content(f):
        try:
            doc = Document(f)
            return "\n".join([p.text for p in doc.paragraphs])
        except: return ""

    def get_local_content(f):
        f.seek(0)
        if f.name.endswith(".pdf"): return get_pdf_content(f)
        else: return get_docx_content(f)

    # ==========================================
    # GIAO DIỆN CHÍNH
    # ==========================================
    if 'global_context' not in st.session_state: st.session_state.global_context = ""
    if 'memory_status' not in st.session_state: st.session_state.memory_status = "Chưa có dữ liệu"
    if 'current_folder_id' not in st.session_state: st.session_state.current_folder_id = ROOT_FOLDER_ID

    with st.sidebar:
        st.title("🎙️ Điều khiển")
        api_key = st.text_input("Nhập Google AI Key:", type="password")
        st.divider()
        audio_bytes = mic_recorder(start_prompt="🔴 Ghi âm", stop_prompt="⏹️ Dừng", key='recorder')
        st.divider()
        work_mode = st.radio("Chế độ:", ["Nghiên cứu", "Viết nháp", "Phản biện", "LaTeX"])
        
        st.divider()
        st.info(f"🧠 **Trạng thái:**\n{st.session_state.memory_status}")
        if st.button("🗑️ Xóa bộ nhớ (Reset)"):
            st.session_state.global_context = ""
            st.session_state.memory_status = "Đã xóa sạch"
            st.rerun()
            
        st.divider()
        st.subheader("📂 Nguồn Dữ liệu")
        source_option = st.radio("Chọn:", ["Tải từ máy", "📁 Duyệt Drive"])

        # 1. TẢI TỪ MÁY
        if source_option == "Tải từ máy":
            uploaded_files = st.file_uploader("Chọn file:", type=["pdf", "docx"], accept_multiple_files=True)
            if uploaded_files:
                with st.spinner("Đang đọc..."):
                    temp_ctx = ""
                    for f in uploaded_files:
                        upload_to_drive(f, f.name, ROOT_FOLDER_ID)
                        temp_ctx += f"\n=== UPLOAD: {f.name} ===\n{get_local_content(f)}\n"
                    st.session_state.global_context = temp_ctx
                    st.session_state.memory_status = f"Đã nạp {len(uploaded_files)} file."
                    st.success("Đã nạp xong!")

        # 2. DUYỆT DRIVE
        elif source_option == "📁 Duyệt Drive":
            service = get_drive_service()
            if service:
                subfolders = list_folders_recursive(service, ROOT_FOLDER_ID)
                folder_options = {"📂 Thư mục gốc": ROOT_FOLDER_ID}
                for f in subfolders: folder_options[f"📁 {f['name']}"] = f['id']
                
                sel_label = st.selectbox("Chọn Thư mục:", list(folder_options.keys()))
                sel_id = folder_options[sel_label]
                st.session_state.current_folder_id = sel_id

                files = list_files_in_folder(service, sel_id)
                if files:
                    st.write(f"Tìm thấy {len(files)} file.")
                    if st.button(f"📚 Đọc TOÀN BỘ '{sel_label}'"):
                        with st.spinner("Đang đọc... (Có thể lâu)"):
                            all_ctx = ""
                            prog = st.progress(0)
                            # Giới hạn đọc tối đa 5 file đầu tiên để tránh sập RAM
                            # Nếu muốn đọc hết, bỏ [:5] đi, nhưng cẩn thận lỗi OOM
                            limit_files = files[:10] 
                            
                            for i, f in enumerate(limit_files):
                                content = read_drive_file(service, f['id'], f['name'], f['mimeType'])
                                if len(content) > 50:
                                    all_ctx += f"\n=== TÀI LIỆU: {f['name']} ===\n{content}\n"
                                prog.progress((i+1)/len(limit_files))
                            
                            st.session_state.global_context = all_ctx
                            st.session_state.memory_status = f"Đã nhớ {len(limit_files)} file trong '{sel_label}'"
                            st.success("✅ Đã học xong!")
                            if len(files) > 10:
                                st.warning("⚠️ Lưu ý: Chỉ đọc 10 file đầu để tránh sập hệ thống.")
                else: st.warning("Thư mục trống.")

    # --- AI & CHAT ---
    sys_prompt = "Bạn là trợ lý học thuật Dissertation Master AI."
    if work_mode == "Phản biện": sys_prompt += " Nhiệm vụ: Phản biện gay gắt."
    if st.session_state.global_context:
        sys_prompt += f"\n\nDỮ LIỆU:\n{st.session_state.global_context}"

    if "messages" not in st.session_state: st.session_state.messages = []

    st.title("🎓 Dissertation Master AI (Debug Mode)")
    st.caption(f"Trạng thái bộ nhớ: {st.session_state.memory_status}")
    st.markdown("---")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    prompt = None
    if audio_bytes:
        with st.spinner("🎧 Đang nghe..."):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tf:
                    tf.write(audio_bytes['bytes']); tf_path = tf.name
                wav = tf_path.replace(".webm", ".wav")
                AudioSegment.from_file(tf_path).export(wav, format="wav")
                r = sr.Recognizer()
                with sr.AudioFile(wav) as s: prompt = r.recognize_google(r.record(s), language="vi-VN")
                os.remove(tf_path); os.remove(wav)
            except: st.warning("Lỗi Mic.")

    if not prompt: prompt = st.chat_input("Nhập câu hỏi...")

    if prompt:
        if not api_key: st.error("Thiếu API Key!"); st.stop()
        genai.configure(api_key=api_key)
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        with st.chat_message("assistant"):
            ph = st.empty(); full_res = ""
            try:
                model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=sys_prompt)
                chat = model.start_chat(history=[{"role": m["role"], "parts": [m["content"]]} for m in st.session_state.messages if m["role"] != "system"])
                for chunk in chat.send_message(prompt, stream=True):
                    if chunk.text: full_res += chunk.text; ph.markdown(full_res + "▌")
                ph.markdown(full_res)
                st.session_state.messages.append({"role": "assistant", "content": full_res})
            except Exception as e: st.error(f"Lỗi AI: {e}")

    # TOOLS
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        last_msg = st.session_state.messages[-1]["content"]
        st.divider()
        doc = Document(); doc.add_paragraph(last_msg); bio = BytesIO(); doc.save(bio); bio.seek(0)
        
        c1, c2, c3 = st.columns(3)
        with c1: st.download_button("📥 Tải về", data=bio, file_name="Review.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        with c2:
            if st.button("☁️ Lưu vào Thư mục này"):
                with st.spinner("Lưu..."):
                    fid, fname = upload_to_drive(bio, "Ket_Qua_AI.docx", st.session_state.current_folder_id)
                    if fid: st.success(f"✅ Đã lưu: {fname}")
                    else: st.error(f"Lỗi: {fname}")
        with c3:
            if st.button("🔊 Đọc"):
                try:
                    tts = gTTS(text=last_msg, lang='vi'); mp3 = BytesIO(); tts.write_to_fp(mp3); st.audio(mp3, format='audio/mp3')
                except: pass

# --- BẮT LỖI TOÀN CỤC ---
except Exception as e:
    st.error("🚨 ỨNG DỤNG BỊ LỖI! Hãy chụp ảnh màn hình này gửi kỹ thuật:")
    st.code(traceback.format_exc())