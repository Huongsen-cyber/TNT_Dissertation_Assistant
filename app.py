import streamlit as st
import traceback

# --- 1. CẤU HÌNH TRANG (BẮT BUỘC ĐẦU TIÊN) ---
st.set_page_config(
    page_title="Dissertation Master AI",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- BẮT ĐẦU KHỐI AN TOÀN (TRY-EXCEPT TOÀN CỤC) ---
try:
    # Import thư viện
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

    # --- ID THƯ MỤC GỐC (Luu_Tru_Luan_Van) ---
    ROOT_FOLDER_ID = "1eojKKKoMk4uLBCLfCpVhgWnaoTtOiu8p"

    # ==========================================
    # CÁC HÀM XỬ LÝ (DRIVE, FILE, AI)
    # ==========================================
    
    # 1. Kết nối Drive
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

    # 2. Upload File
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

    # 3. Liệt kê thư mục con (Tạo cây thư mục)
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

    # 4. Liệt kê file trong thư mục
    def list_files_in_folder(service, folder_id):
        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name, mimeType)", orderBy="name").execute()
            return results.get('files', [])
        except: return []

    # 5. Đọc nội dung file từ Drive (Hỗ trợ PDF, Docx, GDocs)
    def read_drive_file(service, file_id, filename, mimeType):
        try:
            file_stream = BytesIO()
            # Xử lý Google Docs (Phải Export ra Word mới đọc được)
            if mimeType == 'application/vnd.google-apps.document':
                request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            # Xử lý file thường (PDF, Word) - Tải trực tiếp
            else:
                request = service.files().get_media(fileId=file_id)
                
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while done is False: status, done = downloader.next_chunk()
            file_stream.seek(0)
            
            if filename.endswith(".pdf") or mimeType == 'application/pdf': return get_pdf_content(file_stream)
            else: return get_docx_content(file_stream)
        except Exception as e: return f"[Lỗi đọc file {filename}: {str(e)}]"

    # 6. Các hàm đọc nội dung chi tiết
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
    # GIAO DIỆN CHÍNH & LOGIC
    # ==========================================
    
    # Khởi tạo Session State
    if 'global_context' not in st.session_state: st.session_state.global_context = ""
    if 'memory_status' not in st.session_state: st.session_state.memory_status = "Chưa có dữ liệu"
    if 'current_folder_id' not in st.session_state: st.session_state.current_folder_id = ROOT_FOLDER_ID
    if 'saved_files' not in st.session_state: st.session_state.saved_files = []

    with st.sidebar:
        st.title("🎙️ Trung tâm Điều khiển")
        api_key = st.text_input("Nhập Google AI API Key:", type="password")
        
        st.divider()
        st.subheader("🎤 Ra lệnh giọng nói")
        audio_bytes = mic_recorder(start_prompt="🔴 Ghi âm", stop_prompt="⏹️ Dừng", key='recorder')
        
        st.divider()
        work_mode = st.radio("Chế độ:", ["Nghiên cứu", "Viết nháp", "Phản biện", "LaTeX"])
        
        st.divider()
        # --- NÚT DỌN DẸP BỘ NHỚ ---
        st.info(f"🧠 **Bộ nhớ:** {st.session_state.memory_status}")
        if st.button("🗑️ Xóa bộ nhớ (Giải phóng RAM)"):
            st.session_state.global_context = ""
            st.session_state.memory_status = "Đã xóa sạch"
            st.rerun()
            
        st.divider()
        st.subheader("📂 Nguồn Dữ liệu")
        source_option = st.radio("Chọn:", ["Tải từ máy tính", "📁 Duyệt Google Drive"])

        # ---------------------------------------------------------
        # CHỨC NĂNG 1: TẢI TỪ MÁY TÍNH (CÓ AUTO-SAVE)
        # ---------------------------------------------------------
        if source_option == "Tải từ máy tính":
            uploaded_files = st.file_uploader("Chọn file:", type=["pdf", "docx"], accept_multiple_files=True)
            if uploaded_files:
                with st.spinner("Đang đọc & Lưu Drive..."):
                    temp_ctx = ""
                    for f in uploaded_files:
                        # Auto-Save: Chỉ lưu nếu chưa lưu
                        if f.name not in st.session_state.saved_files:
                            fid, fname = upload_to_drive(f, f.name, ROOT_FOLDER_ID)
                            if fid: 
                                st.toast(f"✅ Đã lưu '{f.name}'", icon="☁️")
                                st.session_state.saved_files.append(f.name)
                        
                        # Đọc nội dung
                        temp_ctx += f"\n=== UPLOAD: {f.name} ===\n{get_local_content(f)}\n"
                    
                    st.session_state.global_context = temp_ctx
                    st.session_state.memory_status = f"Đã nạp {len(uploaded_files)} file."
                    st.success("Đã nạp xong!")

        # ---------------------------------------------------------
        # CHỨC NĂNG 2: DUYỆT DRIVE (CÓ CHỌN THƯ MỤC)
        # ---------------------------------------------------------
        elif source_option == "📁 Duyệt Google Drive":
            service = get_drive_service()
            if service:
                # Bước 1: Chọn Thư mục
                subfolders = list_folders_recursive(service, ROOT_FOLDER_ID)
                folder_options = {"📂 Thư mục gốc (Luu_Tru_Luan_Van)": ROOT_FOLDER_ID}
                for f in subfolders: folder_options[f"📁 {f['name']}"] = f['id']
                
                sel_label = st.selectbox("Chọn Thư mục chủ đề:", list(folder_options.keys()))
                sel_id = folder_options[sel_label]
                
                # Cập nhật ID hiện tại để tí nữa lưu file về đúng chỗ này
                st.session_state.current_folder_id = sel_id

                # Bước 2: Liệt kê file trong thư mục đó
                files = list_files_in_folder(service, sel_id)
                if files:
                    st.write(f"Tìm thấy {len(files)} file.")
                    
                    # --- THANH TRƯỢT GIỚI HẠN (QUAN TRỌNG ĐỂ TRÁNH SẬP) ---
                    max_files = len(files)
                    limit = st.slider("Số lượng file muốn đọc:", 1, max_files, min(5, max_files))
                    
                    # Nút đọc hàng loạt
                    if st.button(f"📚 Đọc {limit} file trong thư mục này"):
                        with st.spinner("Đang đọc... (Vui lòng chờ)"):
                            all_ctx = ""
                            prog = st.progress(0)
                            
                            files_to_read = files[:limit]
                            for i, f in enumerate(files_to_read):
                                try:
                                    content = read_drive_file(service, f['id'], f['name'], f['mimeType'])
                                    if len(content) > 50:
                                        all_ctx += f"\n=== TÀI LIỆU: {f['name']} ===\n{content}\n"
                                except: pass
                                prog.progress((i+1)/limit)
                            
                            st.session_state.global_context = all_ctx
                            st.session_state.memory_status = f"Đã nhớ {limit} file: {sel_label}"
                            st.success("✅ Đã học xong!")
                else: st.warning("Thư mục trống.")

    # --- CẤU HÌNH AI ---
    sys_prompt = "Bạn là trợ lý học thuật Dissertation Master AI."
    if work_mode == "Phản biện": sys_prompt += " Nhiệm vụ: Phản biện gay gắt."
    if st.session_state.global_context:
        sys_prompt += f"\n\nDỮ LIỆU THAM KHẢO:\n{st.session_state.global_context}"

    if "messages" not in st.session_state: st.session_state.messages = []

    # --- KHUNG CHAT CHÍNH ---
    st.title("🎓 Dissertation Master AI")
    st.caption(f"Trạng thái: {st.session_state.memory_status}")
    st.markdown("---")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    # XỬ LÝ INPUT
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
            except: st.warning("Không nghe rõ.")

    if not prompt: prompt = st.chat_input("Nhập câu hỏi...")

    # XỬ LÝ TRẢ LỜI
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

    # --- CÔNG CỤ (LUÔN HIỂN THỊ) ---
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        last_msg = st.session_state.messages[-1]["content"]
        st.divider()
        st.write("### 🛠️ Công cụ xử lý:")
        
        doc = Document(); doc.add_heading('Dissertation Draft', 0); doc.add_paragraph(last_msg)
        bio = BytesIO(); doc.save(bio); bio.seek(0)
        
        c1, c2, c3 = st.columns(3)
        # Nút 1: Tải về máy
        with c1: st.download_button("📥 Tải về", data=bio, file_name="Review.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        
        # Nút 2: Lưu Drive (Lưu đúng vào thư mục đang chọn)
        with c2:
            if st.button("☁️ Lưu vào Thư mục này"):
                with st.spinner("Lưu..."):
                    fid, fname = upload_to_drive(bio, "Ket_Qua_AI.docx", st.session_state.current_folder_id)
                    if fid: st.success(f"✅ Đã lưu: {fname}")
                    else: st.error(f"Lỗi: {fid}")
        
        # Nút 3: Đọc
        with c3:
            if st.button("🔊 Đọc"):
                try:
                    tts = gTTS(text=last_msg, lang='vi'); mp3 = BytesIO(); tts.write_to_fp(mp3); st.audio(mp3, format='audio/mp3')
                except: pass

# --- BẮT LỖI TOÀN CỤC ---
except Exception as e:
    st.error("🚨 HỆ THỐNG GẶP LỖI! Chi tiết bên dưới:")
    st.code(traceback.format_exc())