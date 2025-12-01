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
    # CÁC HÀM XỬ LÝ DRIVE (QUÉT SÂU)
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

    # --- HÀM ĐỆ QUY: LẤY TOÀN BỘ CÂY THƯ MỤC ---
    # Hàm này sẽ chạy sâu vào trong các thư mục con để lấy đường dẫn
    def get_all_folders_recursive(service, parent_id, path_prefix=""):
        all_folders = []
        try:
            results = service.files().list(
                q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)", orderBy="name"
            ).execute()
            
            for item in results.get('files', []):
                current_path = f"{path_prefix}📂 {item['name']}"
                all_folders.append({'id': item['id'], 'name': current_path})
                # Gọi lại chính nó để tìm con của thư mục này
                sub_folders = get_all_folders_recursive(service, item['id'], current_path + " / ")
                all_folders.extend(sub_folders)
        except: pass
        return all_folders

    # --- HÀM ĐỆ QUY: LẤY TẤT CẢ FILE TRONG THƯ MỤC VÀ CON CỦA NÓ ---
    def list_files_deep(service, folder_id):
        all_files = []
        try:
            # 1. Lấy file ở thư mục hiện tại
            files = service.files().list(
                q=f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name, mimeType)", orderBy="name"
            ).execute().get('files', [])
            all_files.extend(files)
            
            # 2. Tìm các thư mục con để chui vào lấy tiếp
            subfolders = service.files().list(
                q=f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id)"
            ).execute().get('files', [])
            
            for sub in subfolders:
                all_files.extend(list_files_deep(service, sub['id']))
                
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
        except Exception as e: return f""

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
    # QUẢN LÝ TRẠNG THÁI (SESSION STATE)
    # ==========================================
    if 'global_context' not in st.session_state: st.session_state.global_context = ""
    if 'read_history' not in st.session_state: st.session_state.read_history = [] # Danh sách tên file đã đọc
    if 'current_folder_id' not in st.session_state: st.session_state.current_folder_id = ROOT_FOLDER_ID
    if 'folder_tree_cache' not in st.session_state: st.session_state.folder_tree_cache = [] # Cache danh sách thư mục cho nhanh

    with st.sidebar:
        st.title("🎙️ Điều khiển")
        api_key = st.text_input("Nhập Google AI Key:", type="password")
        
        st.divider()
        audio_bytes = mic_recorder(start_prompt="🔴 Ghi âm", stop_prompt="⏹️ Dừng", key='recorder')
        st.divider()
        work_mode = st.radio("Chế độ:", ["Nghiên cứu", "Viết nháp", "Phản biện", "LaTeX"])
        
        st.divider()
        # Hiển thị những gì AI đang nhớ
        with st.expander("🧠 Bộ nhớ AI (Đã đọc)", expanded=False):
            if st.session_state.read_history:
                for f in st.session_state.read_history:
                    st.write(f"✅ {f}")
                if st.button("🗑️ Quên hết (Reset)"):
                    st.session_state.global_context = ""
                    st.session_state.read_history = []
                    st.rerun()
            else:
                st.write("(Chưa có dữ liệu)")

        st.divider()
        st.subheader("📂 Quản lý Dữ liệu")
        
        source_option = st.radio("Nguồn:", ["Tải từ máy tính", "📁 Duyệt Google Drive"])

        # 1. TẢI TỪ MÁY
        if source_option == "Tải từ máy tính":
            uploaded_files = st.file_uploader("Chọn file:", type=["pdf", "docx"], accept_multiple_files=True)
            if uploaded_files:
                with st.spinner("Đang đọc..."):
                    new_ctx = ""
                    new_files = []
                    for f in uploaded_files:
                        upload_to_drive(f, f.name, ROOT_FOLDER_ID)
                        new_ctx += f"\n=== UPLOAD: {f.name} ===\n{get_local_content(f)}\n"
                        new_files.append(f.name)
                    
                    # Cộng dồn vào bộ nhớ
                    st.session_state.global_context += new_ctx
                    st.session_state.read_history.extend(new_files)
                    st.success(f"Đã nạp thêm {len(new_files)} file!")

        # 2. DUYỆT DRIVE (CÂY THƯ MỤC THÔNG MINH)
        elif source_option == "📁 Duyệt Google Drive":
            service = get_drive_service()
            if service:
                # Load danh sách thư mục (chỉ load 1 lần cho nhanh)
                if not st.session_state.folder_tree_cache:
                    with st.spinner("Đang quét cấu trúc thư mục..."):
                        # Thêm gốc
                        tree = [{'id': ROOT_FOLDER_ID, 'name': '🏠 Thư mục gốc'}]
                        # Thêm con
                        tree.extend(get_all_folders_recursive(service, ROOT_FOLDER_ID))
                        st.session_state.folder_tree_cache = tree
                
                # Dropdown chọn thư mục
                folder_map = {item['name']: item['id'] for item in st.session_state.folder_tree_cache}
                selected_folder_name = st.selectbox("Chọn Chủ đề / Thư mục:", list(folder_map.keys()))
                
                # Lưu ID để tí nữa lưu file về đây
                selected_folder_id = folder_map[selected_folder_name]
                st.session_state.current_folder_id = selected_folder_id

                # Tùy chọn đọc
                read_mode = st.radio("Phạm vi đọc:", ["Chỉ file trong thư mục này", "🚀 Quét sâu (Cả thư mục con)"])
                
                # Nút Quét file
                if st.button("🔍 Tìm file trong thư mục này"):
                    with st.spinner("Đang tìm file..."):
                        if read_mode == "🚀 Quét sâu (Cả thư mục con)":
                            files = list_files_deep(service, selected_folder_id)
                        else:
                            # Chỉ lấy cấp 1
                            files = service.files().list(
                                q=f"'{selected_folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false",
                                fields="files(id, name, mimeType)", orderBy="name").execute().get('files', [])
                        
                        # Lưu danh sách file tìm được vào session để không bị mất khi reload
                        st.session_state.found_files = files
                        st.rerun() # Tải lại để hiển thị danh sách bên dưới

                # Hiển thị danh sách file đã tìm thấy
                if 'found_files' in st.session_state and st.session_state.found_files:
                    files = st.session_state.found_files
                    st.write(f"📂 Tìm thấy **{len(files)} file**.")
                    
                    # Thanh trượt chọn số lượng
                    limit = 1
                    if len(files) > 1:
                        limit = st.slider("Số lượng file muốn đọc:", 1, len(files), min(5, len(files)))
                    
                    # Nút Đọc thật sự
                    if st.button(f"📚 Đọc {limit} file vào bộ nhớ AI"):
                        with st.spinner("Đang đọc và học..."):
                            added_ctx = ""
                            added_names = []
                            prog = st.progress(0)
                            
                            files_to_read = files[:limit]
                            for i, f in enumerate(files_to_read):
                                content = read_drive_file(service, f['id'], f['name'], f['mimeType'])
                                if len(content) > 50:
                                    added_ctx += f"\n=== TÀI LIỆU DRIVE: {f['name']} ===\n{content}\n"
                                    added_names.append(f['name'])
                                prog.progress((i+1)/limit)
                            
                            # CỘNG DỒN VÀO BỘ NHỚ (KHÔNG GHI ĐÈ)
                            st.session_state.global_context += added_ctx
                            st.session_state.read_history.extend(added_names)
                            
                            # Thông báo Chat
                            msg = f"✅ **Đã nạp thêm {len(added_names)} tài liệu vào bộ nhớ:**\n- " + "\n- ".join(added_names)
                            st.session_state.messages.append({"role": "assistant", "content": msg})
                            st.rerun()

    # --- AI & CHAT ---
    sys_prompt = "Bạn là trợ lý học thuật Dissertation Master AI."
    if work_mode == "Phản biện": sys_prompt += " Nhiệm vụ: Phản biện gay gắt."
    if st.session_state.global_context:
        sys_prompt += f"\n\nKIẾN THỨC NỀN TẢNG (TÍCH LŨY):\n{st.session_state.global_context}"

    if "messages" not in st.session_state: st.session_state.messages = []

    st.title("🎓 Dissertation Master AI")
    # Hiển thị folder đang chọn để biết sẽ lưu file vào đâu
    st.caption(f"📂 Thư mục làm việc hiện tại: {selected_folder_name if 'selected_folder_name' in locals() else 'Thư mục gốc'}")
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
                    if fid: st.success(f"✅ Đã lưu vào Drive!")
                    else: st.error(f"Lỗi: {fid}")
        with c3:
            if st.button("🔊 Đọc"):
                try:
                    tts = gTTS(text=last_msg, lang='vi'); mp3 = BytesIO(); tts.write_to_fp(mp3); st.audio(mp3, format='audio/mp3')
                except: pass

# --- BẮT LỖI ---
except Exception as e:
    st.error("🚨 HỆ THỐNG GẶP LỖI! Chi tiết:")
    st.code(traceback.format_exc())