import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader
from docx import Document
from io import BytesIO
import json
import os
import tempfile

# --- THƯ VIỆN VOICE ---
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
from gtts import gTTS
from pydub import AudioSegment

# --- THƯ VIỆN GOOGLE DRIVE (OAUTH) ---
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Dissertation Master AI (Ultimate)",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ID THƯ MỤC DRIVE CỦA BẠN ---
FOLDER_ID = "1eojKKKoMk4uLBCLfCpVhgWnaoTtOiu8p"

# ==========================================
# 1. CÁC HÀM XỬ LÝ GOOGLE DRIVE
# ==========================================

def get_drive_service():
    """Kết nối Drive bằng Token OAuth trong Secrets"""
    if "oauth_token" not in st.secrets:
        st.error("Lỗi: Chưa cấu hình 'oauth_token' trong Secrets!")
        return None
    try:
        token_info = json.loads(st.secrets["oauth_token"])
        creds = Credentials.from_authorized_user_info(token_info)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Lỗi xác thực Google: {e}")
        return None

def upload_to_drive(file_obj, filename):
    """Upload file lên Drive"""
    try:
        service = get_drive_service()
        if not service: return "Lỗi kết nối"

        # Xác định loại file
        if filename.endswith(".pdf"): mime = 'application/pdf'
        elif filename.endswith(".docx"): mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else: mime = 'application/octet-stream'

        file_metadata = {'name': filename, 'parents': [FOLDER_ID]}
        file_obj.seek(0)
        media = MediaIoBaseUpload(file_obj, mimetype=mime)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except Exception as e:
        return f"Error: {str(e)}"

def list_drive_files():
    """Lấy danh sách file trong thư mục Drive"""
    try:
        service = get_drive_service()
        if not service: return []
        # Lấy file trong thư mục FOLDER_ID và không bị xóa
        results = service.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed=false",
            fields="files(id, name, mimeType)",
            orderBy="createdTime desc"
        ).execute()
        return results.get('files', [])
    except: return []

def read_drive_file(file_id, filename):
    """Tải và đọc nội dung file từ Drive"""
    try:
        service = get_drive_service()
        request = service.files().get_media(fileId=file_id)
        file_stream = BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        file_stream.seek(0)
        
        if filename.endswith(".pdf"):
            return get_pdf_content(file_stream)
        elif filename.endswith(".docx"):
            return get_docx_content(file_stream)
        else:
            return "" # Bỏ qua file không đọc được
    except Exception as e:
        return f"Lỗi đọc file: {e}"

# ==========================================
# 2. CÁC HÀM ĐỌC FILE LOCAL
# ==========================================

def get_pdf_content(file_stream):
    try:
        reader = PdfReader(file_stream)
        text = ""
        for page in reader.pages: text += page.extract_text() + "\n"
        return text
    except: return ""

def get_docx_content(file_stream):
    try:
        doc = Document(file_stream)
        return "\n".join([p.text for p in doc.paragraphs])
    except: return ""

def get_file_content(uploaded_file):
    uploaded_file.seek(0)
    if uploaded_file.name.endswith(".pdf"): return get_pdf_content(uploaded_file)
    elif uploaded_file.name.endswith(".docx"): return get_docx_content(uploaded_file)
    return ""

# ==========================================
# 3. GIAO DIỆN & LOGIC CHÍNH
# ==========================================

with st.sidebar:
    st.title("🎙️ Cấu hình & Drive")
    api_key = st.text_input("Nhập Google AI API Key:", type="password")
    
    st.divider()
    st.subheader("🎤 Voice Chat")
    audio_bytes = mic_recorder(start_prompt="🔴 Ghi âm", stop_prompt="⏹️ Dừng", just_once=True, key='recorder')
    
    st.divider()
    work_mode = st.radio("Quy trình:", ["Research", "Drafting", "Academic Review", "LaTeX Conversion"])
    
    st.divider()
    st.subheader("📂 Nguồn Tài liệu")
    source_option = st.radio("Chọn nguồn:", ["Tải từ máy tính", "Google Drive (Cá nhân)", "Google Drive (Toàn bộ thư mục)"])
    
    if 'saved_files' not in st.session_state: st.session_state.saved_files = []
    
    # Biến lưu nội dung toàn cục
    if 'global_context' not in st.session_state: st.session_state.global_context = ""

    # --- LOGIC NGUỒN TÀI LIỆU ---
    
    # 1. TẢI TỪ MÁY TÍNH
    if source_option == "Tải từ máy tính":
        uploaded_files = st.file_uploader("Upload PDF/Word:", type=["pdf", "docx"], accept_multiple_files=True)
        if uploaded_files:
            with st.spinner("Đang xử lý & Auto-Save..."):
                temp_context = ""
                for f in uploaded_files:
                    # Auto-Save
                    if f.name not in st.session_state.saved_files:
                        fid = upload_to_drive(f, f.name)
                        if "Error" not in fid:
                            st.toast(f"✅ Đã lưu '{f.name}'!", icon="☁️")
                            st.session_state.saved_files.append(f.name)
                    # Đọc
                    content = get_file_content(f)
                    temp_context += f"\n--- TÀI LIỆU: {f.name} ---\n{content}\n"
                
                st.session_state.global_context = temp_context
                st.success(f"Đã nạp {len(uploaded_files)} file!")

    # 2. CHỌN 1 FILE TỪ DRIVE
    elif source_option == "Google Drive (Cá nhân)":
        with st.spinner("Đang tải danh sách..."):
            drive_files = list_drive_files()
            if drive_files:
                file_opts = {f['name']: f['id'] for f in drive_files}
                selected_name = st.selectbox("Chọn file:", list(file_opts.keys()))
                
                if st.button("📖 Đọc file này"):
                    with st.spinner("Đang đọc..."):
                        content = read_drive_file(file_opts[selected_name], selected_name)
                        st.session_state.global_context = f"\n--- DRIVE DOC: {selected_name} ---\n{content}\n"
                        st.success(f"Đã đọc xong '{selected_name}'!")
            else: st.warning("Thư mục trống.")

    # 3. ĐỌC TOÀN BỘ THƯ MỤC (TÍNH NĂNG MỚI)
    elif source_option == "Google Drive (Toàn bộ thư mục)":
        st.info("Tính năng này sẽ đọc TẤT CẢ file trong thư mục để đối chiếu tổng hợp.")
        if st.button("📚 Đọc TẤT CẢ file để đối chiếu"):
            drive_files = list_drive_files()
            if drive_files:
                progress_bar = st.progress(0)
                temp_all_context = ""
                total_files = len(drive_files)
                
                status_text = st.empty()
                
                for i, file_info in enumerate(drive_files):
                    file_name = file_info['name']
                    file_id = file_info['id']
                    status_text.text(f"⏳ Đang đọc ({i+1}/{total_files}): {file_name}...")
                    
                    content = read_drive_file(file_id, file_name)
                    if content:
                        temp_all_context += f"\n=== TÀI LIỆU ĐỐI CHIẾU: {file_name} ===\n{content}\n"
                    
                    progress_bar.progress((i + 1) / total_files)
                
                st.session_state.global_context = temp_all_context
                status_text.text("✅ Đã đọc xong tất cả!")
                st.success(f"Đã nạp {total_files} tài liệu vào bộ nhớ để đối chiếu!")
            else:
                st.warning("Thư mục trống.")

# --- MAIN APP ---
system_instruction = "Bạn là trợ lý học thuật Dissertation Master AI chuyên sâu."
if work_mode == "LaTeX Conversion": system_instruction += " Chuyển đổi sang LaTeX."
elif work_mode == "Academic Review": system_instruction += " Phản biện logic."

# Dùng nội dung từ Session State
if st.session_state.global_context:
    system_instruction += f"\n\nCONTEXT TỪ CÁC TÀI LIỆU:\n{st.session_state.global_context}"

if "messages" not in st.session_state: st.session_state.messages = []

st.title("🎓 Dissertation Master AI (Ultimate)")
st.caption("Full Feature: Voice | Auto-Save | Multi-File Analysis")
st.markdown("---")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]): st.markdown(msg["content"])

# INPUT
prompt = None
if audio_bytes and audio_bytes['bytes']:
    with st.spinner("🎧 Đang dịch..."):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_webm:
                temp_webm.write(audio_bytes['bytes'])
                temp_webm_path = temp_webm.name
            wav_path = temp_webm_path.replace(".webm", ".wav")
            AudioSegment.from_file(temp_webm_path).export(wav_path, format="wav")
            r = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                prompt = r.recognize_google(r.record(source), language="vi-VN")
            os.remove(temp_webm_path); os.remove(wav_path)
        except: st.warning("Không nghe rõ.")

if not prompt: prompt = st.chat_input("Nhập câu hỏi...")

# GENERATE
if prompt:
    if not api_key: st.error("Thiếu API Key!"); st.stop()
    genai.configure(api_key=api_key)
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    with st.chat_message("assistant"):
        ph = st.empty(); full_res = ""
        try:
            model = genai.GenerativeModel("models/gemini-2.0-flash", system_instruction=system_instruction)
            chat = model.start_chat(history=[{"role": m["role"], "parts": [m["content"]]} for m in st.session_state.messages if m["role"] != "system"])
            for chunk in chat.send_message(prompt, stream=True):
                if chunk.text: full_res += chunk.text; ph.markdown(full_res + "▌")
            ph.markdown(full_res)
            st.session_state.messages.append({"role": "assistant", "content": full_res})
        except Exception as e: st.error(f"Lỗi: {e}")

# TOOLS (CỐ ĐỊNH CUỐI CÙNG - KHÔNG MẤT KHI RELOAD)
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    st.divider()
    st.write("### 🛠️ Công cụ:")
    
    doc = Document(); doc.add_heading('Draft', 0); doc.add_paragraph(last_msg)
    bio = BytesIO(); doc.save(bio); bio.seek(0)

    c1, c2, c3 = st.columns(3)
    with c1: st.download_button("📥 Tải về", data=bio, file_name="draft.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with c2:
        if st.button("☁️ Lưu bản nháp"):
            with st.spinner("Lưu..."):
                fid = upload_to_drive(bio, f"Response_{len(st.session_state.messages)}.docx")
                if "Error" not in fid: st.success("✅ Đã lưu!")
                else: st.error(f"Lỗi: {fid}")
    with c3:
        if st.button("🔊 Đọc"):
            try:
                with st.spinner("Đọc..."):
                    tts = gTTS(text=last_msg, lang='vi')
                    mp3 = BytesIO(); tts.write_to_fp(mp3); st.audio(mp3, format='audio/mp3')
            except: pass