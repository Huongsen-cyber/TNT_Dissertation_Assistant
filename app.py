import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader
from docx import Document
from io import BytesIO
import json
import os
import tempfile
import datetime

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
    page_title="Dissertation Master AI",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ID THƯ MỤC GỐC DRIVE CỦA BẠN ---
ROOT_FOLDER_ID = "1eojKKKoMk4uLBCLfCpVhgWnaoTtOiu8p"

# ==========================================
# 1. CÁC HÀM XỬ LÝ GOOGLE DRIVE
# ==========================================

def get_drive_service():
    """Kết nối Drive bằng Token OAuth"""
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

def upload_to_drive(file_obj, filename, target_folder_id=ROOT_FOLDER_ID):
    """Upload file lên Drive (Mặc định vào thư mục gốc, hoặc thư mục con nếu chọn)"""
    try:
        service = get_drive_service()
        if not service: return "Lỗi kết nối"

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        final_filename = f"{filename.replace('.docx', '')}_{timestamp}.docx"

        file_metadata = {'name': final_filename, 'parents': [target_folder_id]}
        file_obj.seek(0)
        media = MediaIoBaseUpload(file_obj, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except Exception as e:
        return f"Error: {str(e)}"

def list_subfolders(parent_id):
    """Liệt kê các thư mục con"""
    try:
        service = get_drive_service()
        if not service: return []
        results = service.files().list(
            q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)",
            orderBy="name"
        ).execute()
        return results.get('files', [])
    except: return []

def list_files_in_folder(folder_id):
    """Liệt kê file trong một thư mục cụ thể"""
    try:
        service = get_drive_service()
        if not service: return []
        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name, mimeType)",
            orderBy="createdTime desc"
        ).execute()
        return results.get('files', [])
    except: return []

def read_drive_file(file_id, filename):
    """Đọc nội dung file từ Drive"""
    try:
        service = get_drive_service()
        request = service.files().get_media(fileId=file_id)
        file_stream = BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        file_stream.seek(0)
        
        if filename.endswith(".pdf"): return get_pdf_content(file_stream)
        elif filename.endswith(".docx"): return get_docx_content(file_stream)
        else: return "" 
    except Exception as e: return f"Lỗi đọc file: {e}"

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
    st.title("🎙️ Trung tâm Điều khiển")
    api_key = st.text_input("Nhập Google AI API Key:", type="password")
    
    st.divider()
    st.subheader("🎤 Ra lệnh giọng nói")
    audio_bytes = mic_recorder(start_prompt="🔴 Ghi âm", stop_prompt="⏹️ Dừng", just_once=True, key='recorder')
    
    st.divider()
    work_mode = st.radio("Chế độ:", ["Nghiên cứu", "Viết nháp", "Phản biện", "LaTeX Conversion"])
    
    st.divider()
    st.subheader("📂 Quản lý Dữ liệu")
    
    # Menu chọn nguồn dữ liệu nâng cấp
    source_option = st.radio(
        "Nguồn dữ liệu:", 
        ["Tải từ máy tính", "📁 Đọc theo Thư mục con (Topics)", "Chọn 1 file lẻ (Gốc)"]
    )
    
    # Biến toàn cục
    if 'global_context' not in st.session_state: st.session_state.global_context = ""
    if 'current_folder_id' not in st.session_state: st.session_state.current_folder_id = ROOT_FOLDER_ID

    # 1. TẢI TỪ MÁY
    if source_option == "Tải từ máy tính":
        uploaded_files = st.file_uploader("Upload PDF/Word:", type=["pdf", "docx"], accept_multiple_files=True)
        if uploaded_files:
            with st.spinner("Đang xử lý..."):
                temp_ctx = ""
                for f in uploaded_files:
                    content = get_file_content(f)
                    temp_ctx += f"\n=== TÀI LIỆU MỚI: {f.name} ===\n{content}\n"
                st.session_state.global_context = temp_ctx
                st.success(f"Đã nạp {len(uploaded_files)} file!")

    # 2. ĐỌC THEO THƯ MỤC CON (TÍNH NĂNG MỚI)
    elif source_option == "📁 Đọc theo Thư mục con (Topics)":
        with st.spinner("Đang quét các thư mục chủ đề..."):
            subfolders = list_subfolders(ROOT_FOLDER_ID)
            
            if subfolders:
                # Tạo danh sách chọn thư mục
                folder_opts = {f['name']: f['id'] for f in subfolders}
                selected_folder_name = st.selectbox("Chọn Chủ đề / Chương:", list(folder_opts.keys()))
                
                # Cập nhật ID thư mục hiện tại để lưu file về đúng chỗ này
                st.session_state.current_folder_id = folder_opts[selected_folder_name]
                
                if st.button(f"📚 Đọc tất cả trong '{selected_folder_name}'"):
                    target_id = folder_opts[selected_folder_name]
                    files_in_folder = list_files_in_folder(target_id)
                    
                    if files_in_folder:
                        progress_bar = st.progress(0)
                        temp_all_ctx = ""
                        total = len(files_in_folder)
                        status = st.empty()
                        
                        for i, f in enumerate(files_in_folder):
                            status.text(f"Đang đọc ({i+1}/{total}): {f['name']}...")
                            content = read_drive_file(f['id'], f['name'])
                            if content:
                                temp_all_ctx += f"\n=== TÀI LIỆU ({selected_folder_name}): {f['name']} ===\n{content}\n"
                            progress_bar.progress((i + 1) / total)
                        
                        st.session_state.global_context = temp_all_ctx
                        status.empty()
                        st.success(f"✅ Đã học xong chủ đề: {selected_folder_name}!")
                    else:
                        st.warning(f"Thư mục '{selected_folder_name}' đang trống.")
            else:
                st.warning("Không tìm thấy thư mục con nào trong Luu_Tru_Luan_Van.")
                st.info("💡 Mẹo: Hãy vào Google Drive và tạo các thư mục như 'Chương 1', 'Tài liệu tham khảo' bên trong thư mục gốc.")

    # 3. CHỌN 1 FILE LẺ
    elif source_option == "Chọn 1 file lẻ (Gốc)":
        st.session_state.current_folder_id = ROOT_FOLDER_ID # Reset về gốc
        drive_files = list_files_in_folder(ROOT_FOLDER_ID)
        if drive_files:
            file_opts = {f['name']: f['id'] for f in drive_files}
            selected_name = st.selectbox("Chọn file:", list(file_opts.keys()))
            if st.button("📖 Đọc file này"):
                with st.spinner("Đang đọc..."):
                    content = read_drive_file(file_opts[selected_name], selected_name)
                    st.session_state.global_context = f"\n=== FILE LẺ: {selected_name} ===\n{content}\n"
                    st.success("Đã đọc xong!")

# --- CẤU HÌNH AI ---
system_instruction = "Bạn là 'Dissertation Master AI', trợ lý nghiên cứu sinh Tiến sĩ."
if work_mode == "Phản biện": system_instruction += " NHIỆM VỤ: Phản biện gay gắt, tìm lỗ hổng logic."
if st.session_state.global_context:
    system_instruction += f"\n\nKIẾN THỨC NỀN TẢNG:\n{st.session_state.global_context}"

if "messages" not in st.session_state: st.session_state.messages = []

# --- GIAO DIỆN CHÍNH ---
st.title("🎓 Dissertation Master AI")
st.caption(f"📂 Đang làm việc với thư mục ID: ...{st.session_state.current_folder_id[-6:]}")
st.markdown("---")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]): st.markdown(msg["content"])

# INPUT
prompt = None
if audio_bytes and audio_bytes['bytes']:
    with st.spinner("🎧 Đang nghe..."):
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

# TOOLS (CỐ ĐỊNH)
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    st.divider()
    st.write("### 🛠️ Công cụ xử lý:")
    
    doc = Document(); doc.add_heading('Review Note', 0); doc.add_paragraph(last_msg)
    bio = BytesIO(); doc.save(bio); bio.seek(0)

    c1, c2, c3 = st.columns(3)
    with c1: st.download_button("📥 Tải về máy", data=bio, file_name="Review.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    
    # Nút Lưu Drive thông minh: Lưu thẳng vào thư mục đang chọn
    with c2:
        if st.button("☁️ Lưu vào Thư mục này"):
            with st.spinner("Đang lưu..."):
                # Lưu vào thư mục con đang chọn (hoặc gốc nếu chưa chọn)
                target_folder = st.session_state.current_folder_id
                fid = upload_to_drive(bio, "Review_Note.docx", target_folder)
                if "Error" not in fid: st.success("✅ Đã lưu vào đúng thư mục chủ đề!")
                else: st.error(f"Lỗi: {fid}")
    
    with c3:
        if st.button("🔊 Đọc"):
            try:
                with st.spinner("Đọc..."):
                    tts = gTTS(text=last_msg, lang='vi')
                    mp3 = BytesIO(); tts.write_to_fp(mp3); st.audio(mp3, format='audio/mp3')
            except: pass