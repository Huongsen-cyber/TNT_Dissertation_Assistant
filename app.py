import streamlit as st
import traceback

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Dissertation Master AI (TNT)",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 0. BỘ NÃO TNT V1.1 (NHÚNG TRI THỨC)
# Trích xuất từ tài liệu "TNT Advanced AI Editor & Writer"
# ==========================================
TNT_MASTER_PROMPT = """
ROLE: You are "TNT Advanced AI Editor & Writer V1.1", the world's leading expert in assisting Doctoral Dissertations (Buddhist Studies & Humanities).

[KNOWLEDGE BASE - TNT COMMAND SYSTEM]:
You must map User's Natural Language requests to these specific Command Codes:

1. WORKFLOW (WF-*):
- WF-DMAI: Deep Structural Analysis (Phân tích cấu trúc, chia đoạn, tìm lỗ hổng).
- WF-QACHECK: Logic & Coherence Check (Kiểm tra mạch văn, mâu thuẫn, giọng văn học thuật).
- WF-MERGE: Consistency Check (Hợp nhất văn phong giữa các chương).
- WF-CITGEN: Citation Standardization (Chuẩn hóa trích dẫn sang APA 7/Chicago).

2. EDITING (ED-*):
- ED-STD (Standard): Academic Editing (Sửa ngữ pháp, chính tả, nâng cấp từ vựng học thuật, giữ nguyên ý).
- ED-EXT25 (Extend): Deepen Analysis (+25% length) (Mở rộng phân tích, thêm luận cứ, thêm chú thích sâu sắc).
- ED-RED05 (Reduce): Concise Editing (-5% length) (Lược bỏ dư thừa, làm gọn văn bản).

3. FORMATTING (FMT-*):
- FMT-FNAF02: Standard Chunk Format (5 trang/chunk + Glossary + Footnotes + Bibliography).
- FMT-OUT5LV01: 5-Level Outline (Dàn ý chi tiết 5 cấp: I, 1, a, i...).
- FMT-LSC01: List-Structured Commentary (Bình luận dạng danh sách).

4. TRANSLATION & QUOTES (TR/CQ-*):
- TR-ENVI: Translate English -> Vietnamese (Academic style).
- TR-PALVI: Translate Pali -> Vietnamese (Kèm chú thích thuật ngữ).
- CQ-VERIFY: Verify Citations (Kiểm tra độ chính xác nguồn kinh điển).

[OPERATING RULES - AUTO-DETECT MODE]:
1. IF the user speaks natural language (e.g., "Sửa lại đoạn này cho hay", "Kiểm tra xem có sai sót gì không"), YOU MUST:
   - Step A: Analyze the user's intent.
   - Step B: Select the most appropriate TNT Command Combination (e.g., ED-STD + FMT-FNAF02).
   - Step C: Display a "Meta-Tag" block at the start of your response showing what you are doing (in Vietnamese).
     Example: "**🔍 Phân tích:** Bạn muốn nâng cấp văn phong. **🛠️ Kích hoạt:** `ED-STD` (Biên tập chuẩn)."
   - Step D: Execute the task perfectly.

2. EP-NLSTRICT (NoLoad Mode): Do not hallucinate. Only use info provided in context or your internal knowledge base if explicitly asked.
"""

# --- BẮT ĐẦU KHỐI CODE CHÍNH ---
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

    # --- ID THƯ MỤC GỐC (CỦA BẠN) ---
    ROOT_FOLDER_ID = "1eojKKKoMk4uLBCLfCpVhgWnaoTtOiu8p"

    # ==========================================
    # CÁC HÀM XỬ LÝ (DRIVE, FILE)
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

    def list_subfolders(service, parent_id):
        folders = []
        try:
            results = service.files().list(
                q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)", orderBy="name").execute()
            folders.append({'id': parent_id, 'name': '📂 Thư mục gốc (Luu_Tru_Luan_Van)'})
            for item in results.get('files', []):
                folders.append({'id': item['id'], 'name': f"📁 {item['name']}"})
        except: pass
        return folders

    def list_files_in_folder(service, folder_id):
        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name, mimeType)", orderBy="createdTime desc").execute()
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
        except Exception as e: return ""

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
    # QUẢN LÝ SESSION STATE
    # ==========================================
    if 'global_context' not in st.session_state: st.session_state.global_context = ""
    if 'memory_status' not in st.session_state: st.session_state.memory_status = "Chưa có dữ liệu"
    if 'current_folder_id' not in st.session_state: st.session_state.current_folder_id = ROOT_FOLDER_ID
    if 'current_folder_name' not in st.session_state: st.session_state.current_folder_name = "Thư mục gốc"

    # ==========================================
    # GIAO DIỆN SIDEBAR
    # ==========================================
    with st.sidebar:
        st.title("🎙️ TNT Smart Center")
        api_key = st.text_input("Nhập Google AI Key:", type="password")
        
        st.divider()
        audio_bytes = mic_recorder(start_prompt="🔴 Ghi âm (Nói tự nhiên)", stop_prompt="⏹️ Dừng", key='recorder')
        
        st.divider()
        # Nút dọn dẹp RAM
        st.info(f"🧠 {st.session_state.memory_status}")
        if st.button("🗑️ Xóa bộ nhớ"):
            st.session_state.global_context = ""
            st.session_state.memory_status = "Đã xóa sạch"
            st.rerun()
            
        st.divider()
        st.subheader("📂 Quản lý Dữ liệu")
        source_option = st.radio("Nguồn:", ["Tải từ máy tính", "📁 Duyệt Google Drive"])

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

        # 2. DUYỆT DRIVE (THÔNG MINH)
        elif source_option == "📁 Duyệt Google Drive":
            service = get_drive_service()
            if service:
                # Chọn Thư mục
                subfolders = list_subfolders(service, ROOT_FOLDER_ID)
                folder_map = {item['name']: item['id'] for item in subfolders}
                selected_folder_name = st.selectbox("Chọn Chủ đề / Thư mục:", list(folder_map.keys()))
                
                selected_folder_id = folder_map[selected_folder_name]
                st.session_state.current_folder_id = selected_folder_id
                st.session_state.current_folder_name = selected_folder_name

                # Liệt kê file
                files = list_files_in_folder(service, selected_folder_id)
                if files:
                    st.write(f"📂 Có **{len(files)} file** trong '{selected_folder_name}'")
                    # Thanh trượt
                    max_val = len(files)
                    limit = 1
                    if max_val > 1:
                        limit = st.slider("Số lượng file muốn đọc:", 1, max_val, min(5, max_val))
                    
                    if st.button(f"📚 Đọc {limit} file"):
                        with st.spinner("Đang đọc và học..."):
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
                            st.session_state.memory_status = f"Đã nhớ {len(read_names)} file từ: {selected_folder_name}"
                            
                            msg = f"✅ **Đã đọc xong:**\n- " + "\n- ".join(read_names)
                            st.session_state.messages.append({"role": "assistant", "content": msg})
                            st.rerun()
                else: st.warning("Thư mục trống.")

    # ==========================================
    # CẤU HÌNH AI (NHÚNG TNT MASTER PROMPT)
    # ==========================================
    
    # Kết hợp Master Prompt + Dữ liệu
    full_system_instruction = TNT_MASTER_PROMPT
    if st.session_state.global_context:
        full_system_instruction += f"\n\n[USER PROVIDED CONTEXT]:\n{st.session_state.global_context}"

    if "messages" not in st.session_state: st.session_state.messages = []

    # --- GIAO DIỆN CHAT ---
    st.title("🎓 Dissertation Master AI (TNT Edition)")
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
            except: st.warning("Lỗi Mic.")

    if not prompt: prompt = st.chat_input("Nhập yêu cầu (VD: Sửa lại chương này cho hay hơn)...")

    if prompt:
        if not api_key: st.error("Thiếu API Key!"); st.stop()
        genai.configure(api_key=api_key)
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        with st.chat_message("assistant"):
            ph = st.empty(); full_res = ""
            try:
                # Dùng Gemini 2.0 Flash để xử lý thông minh
                model = genai.GenerativeModel("models/gemini-2.0-flash", system_instruction=full_system_instruction)
                chat = model.start_chat(history=[{"role": m["role"], "parts": [m["content"]]} for m in st.session_state.messages if m["role"] != "system"])
                for chunk in chat.send_message(prompt, stream=True):
                    if chunk.text: full_res += chunk.text; ph.markdown(full_res + "▌")
                ph.markdown(full_res)
                st.session_state.messages.append({"role": "assistant", "content": full_res})
            except Exception as e: st.error(f"Lỗi AI: {e}")

    # TOOLS (CỐ ĐỊNH)
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        last_msg = st.session_state.messages[-1]["content"]
        st.divider()
        st.write("### 🛠️ Công cụ xử lý:")
        
        doc = Document(); doc.add_paragraph(last_msg); bio = BytesIO(); doc.save(bio); bio.seek(0)
        
        c1, c2, c3 = st.columns(3)
        with c1: st.download_button("📥 Tải về", data=bio, file_name="TNT_Output.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        with c2:
            if st.button("☁️ Lưu vào Thư mục này"):
                with st.spinner("Lưu..."):
                    fid, fname = upload_to_drive(bio, "TNT_Output.docx", st.session_state.current_folder_id)
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