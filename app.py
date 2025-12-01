import streamlit as st
import traceback

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Dissertation Master AI",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- BẮT ĐẦU KHỐI AN TOÀN ---
try:
    import google.generativeai as genai
    from pypdf import PdfReader
    from docx import Document
    from io import BytesIO
    import json
    import os
    import tempfile
    import datetime
    
    # Voice & Drive
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

    # --- HÀM MỚI: QUÉT TOÀN BỘ CÂY THƯ MỤC (ĐỆ QUY) ---
    def get_all_folders_recursive(service, parent_id, prefix="", folder_list=None):
        if folder_list is None: folder_list = []
        try:
            # Tìm thư mục con
            results = service.files().list(
                q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)", orderBy="name"
            ).execute()
            
            for item in results.get('files', []):
                # Tạo tên hiển thị kiểu cây (VD: Chương 1 > Mục 1.1)
                display_name = f"{prefix}📁 {item['name']}"
                folder_list.append({'id': item['id'], 'name': display_name})
                # Gọi lại chính nó để tìm con của thư mục này (Đệ quy)
                get_all_folders_recursive(service, item['id'], prefix + "-- ", folder_list)
        except: pass
        return folder_list

    # --- HÀM MỚI: LẤY FILE TRONG CẢ THƯ MỤC CON (ĐỆ QUY) ---
    def list_files_recursive(service, folder_id):
        all_files = []
        try:
            # 1. Lấy file trong thư mục hiện tại
            files = service.files().list(
                q=f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name, mimeType)", orderBy="name"
            ).execute().get('files', [])
            all_files.extend(files)
            
            # 2. Lấy các thư mục con
            subfolders = service.files().list(
                q=f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)"
            ).execute().get('files', [])
            
            # 3. Đệ quy vào trong
            for sf in subfolders:
                all_files.extend(list_files_recursive(service, sf['id']))
                
        except: pass
        return all_files

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
    if 'current_folder_name' not in st.session_state: st.session_state.current_folder_name = "Thư mục gốc"

    with st.sidebar:
        st.title("🎙️ Điều khiển")
        api_key = st.text_input("Nhập Google AI Key:", type="password")
        
        st.divider()
        audio_bytes = mic_recorder(start_prompt="🔴 Ghi âm", stop_prompt="⏹️ Dừng", key='recorder')
        
        st.divider()
        work_mode = st.radio("Chế độ:", ["Nghiên cứu", "Viết nháp", "Phản biện", "LaTeX"])
        
        st.divider()
        # Nút dọn dẹp RAM
        st.info(f"🧠 {st.session_state.memory_status}")
        if st.button("🗑️ Xóa bộ nhớ"):
            st.session_state.global_context = ""
            st.session_state.memory_status = "Đã xóa sạch"
            st.rerun()
            
        st.divider()
        st.subheader("📂 Quản lý Dữ liệu")
        
        source_option = st.radio("Nguồn:", ["Tải từ máy tính", "📁 Duyệt Google Drive (Toàn bộ)"])

        # 1. TẢI TỪ MÁY
        if source_option == "Tải từ máy tính":
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

        # 2. DUYỆT DRIVE (CÂY THƯ MỤC)
        elif source_option == "📁 Duyệt Google Drive (Toàn bộ)":
            service = get_drive_service()
            if service:
                # Bước 1: Quét toàn bộ cây thư mục
                st.write("🔽 **1. Chọn Thư mục (Đã quét sâu)**")
                # Lấy danh sách thư mục đệ quy
                all_folders = [{'id': ROOT_FOLDER_ID, 'name': '📂 Thư mục gốc (Luu_Tru_Luan_Van)'}]
                all_folders.extend(get_all_folders_recursive(service, ROOT_FOLDER_ID))
                
                # Tạo danh sách chọn
                folder_map = {item['name']: item['id'] for item in all_folders}
                selected_folder_name = st.selectbox("Cấu trúc thư mục:", list(folder_map.keys()))
                
                selected_folder_id = folder_map[selected_folder_name]
                st.session_state.current_folder_id = selected_folder_id
                st.session_state.current_folder_name = selected_folder_name

                # Bước 2: Quét file (Bao gồm cả file trong thư mục con nếu muốn)
                st.write("🔽 **2. Chọn chế độ đọc**")
                read_mode = st.radio("Chế độ:", ["Chỉ đọc file trong thư mục này", "🚀 Đọc sâu (Bao gồm cả thư mục con)"])
                
                files = []
                if read_mode == "🚀 Đọc sâu (Bao gồm cả thư mục con)":
                     if st.button(f"🔍 Quét tìm mọi file trong '{selected_folder_name}'"):
                        with st.spinner("Đang quét sâu..."):
                            files = list_files_recursive(service, selected_folder_id)
                else:
                    # Chỉ đọc file cấp 1 (như cũ)
                    files = service.files().list(
                        q=f"'{selected_folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false",
                        fields="files(id, name, mimeType)", orderBy="name").execute().get('files', [])

                # Hiển thị kết quả quét
                if files:
                    st.success(f"📂 Tìm thấy **{len(files)} file**.")
                    
                    # Thanh trượt giới hạn
                    max_val = len(files)
                    limit = 1
                    if max_val > 1:
                        limit = st.slider("Số lượng file muốn đọc:", 1, max_val, min(5, max_val))
                    
                    if st.button(f"📚 Đọc {limit} file đã tìm thấy"):
                        with st.spinner("Đang đọc..."):
                            all_ctx = ""
                            prog = st.progress(0)
                            files_to_read = files[:limit]
                            read_names = []
                            
                            for i, f in enumerate(files_to_read):
                                try:
                                    content = read_drive_file(service, f['id'], f['name'], f['mimeType'])
                                    if len(content) > 50:
                                        all_ctx += f"\n=== TÀI LIỆU: {f['name']} ===\n{content}\n"
                                        read_names.append(f['name'])
                                except: pass
                                prog.progress((i+1)/limit)
                            
                            st.session_state.global_context = all_ctx
                            st.session_state.memory_status = f"Đã nhớ {len(read_names)} file."
                            
                            # Gửi thông báo vào Chat
                            msg = f"✅ **Đã đọc xong các file sau:**\n- " + "\n- ".join(read_names)
                            if max_val > limit:
                                msg += f"\n\n⚠️ Còn **{max_val - limit} file** chưa đọc. Bạn có muốn tăng giới hạn và đọc tiếp không?"
                            
                            st.session_state.messages.append({"role": "assistant", "content": msg})
                            st.rerun()
                elif read_mode != "🚀 Đọc sâu (Bao gồm cả thư mục con)":
                     st.warning("Thư mục trống.")

    # --- AI & CHAT ---
    sys_prompt = "Bạn là trợ lý học thuật Dissertation Master AI."
    if work_mode == "Phản biện": sys_prompt += " Nhiệm vụ: Phản biện gay gắt."
    if st.session_state.global_context:
        sys_prompt += f"\n\nDỮ LIỆU THAM KHẢO:\n{st.session_state.global_context}"

    if "messages" not in st.session_state: st.session_state.messages = []

    st.title("🎓 Dissertation Master AI")
    st.caption(f"📂 Đang làm việc tại: {st.session_state.current_folder_name}")
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
                model = genai.GenerativeModel("models/gemini-2.0-flash", system_instruction=sys_prompt)
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
        st.write("### 🛠️ Công cụ xử lý:")
        
        doc = Document(); doc.add_paragraph(last_msg); bio = BytesIO(); doc.save(bio); bio.seek(0)
        
        c1, c2, c3 = st.columns(3)
        with c1: st.download_button("📥 Tải về", data=bio, file_name="Review.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        with c2:
            if st.button("☁️ Lưu vào Thư mục này"):
                with st.spinner("Lưu..."):
                    fid, fname = upload_to_drive(bio, "Ket_Qua_AI.docx", st.session_state.current_folder_id)
                    if fid: st.success(f"✅ Đã lưu vào '{st.session_state.current_folder_name}'!")
                    else: st.error(f"Lỗi: {fid}")
        with c3:
            if st.button("🔊 Đọc"):
                try:
                    tts = gTTS(text=last_msg, lang='vi'); mp3 = BytesIO(); tts.write_to_fp(mp3); st.audio(mp3, format='audio/mp3')
                except: pass

# --- BẮT LỖI TOÀN CỤC ---
except Exception as e:
    st.error("🚨 HỆ THỐNG GẶP LỖI! Chi tiết:")
    st.code(traceback.format_exc())