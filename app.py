import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader
from docx import Document
from io import BytesIO
import json
import os
import tempfile

# --- THƯ VIỆN VOICE & AUDIO ---
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
from gtts import gTTS
from pydub import AudioSegment

# --- THƯ VIỆN GOOGLE DRIVE (OAUTH) ---
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Dissertation Master AI (Final)",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- HÀM 1: KẾT NỐI DRIVE BẰNG OAUTH (QUAN TRỌNG) ---
def get_drive_service():
    # Kiểm tra xem Secrets đã có token chưa
    if "oauth_token" not in st.secrets:
        st.error("Lỗi: Chưa cấu hình 'oauth_token' trong Secrets! Hãy chạy file get_token.py để lấy mã.")
        return None
    
    try:
        # Lấy thông tin token từ Secrets
        token_info = json.loads(st.secrets["oauth_token"])
        creds = Credentials.from_authorized_user_info(token_info)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Lỗi xác thực Google: {e}")
        return None

# --- HÀM 2: UPLOAD FILE ---
def upload_to_drive(file_obj, filename):
    try:
        service = get_drive_service()
        if not service: return "Lỗi kết nối"

        # ✅ ID THƯ MỤC DRIVE CỦA BẠN
        folder_id = "1eojKKKoMk4uLBCLfCpVhgWnaoTtOiu8p"

        # Xác định loại file
        if filename.endswith(".pdf"): mime = 'application/pdf'
        elif filename.endswith(".docx"): mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else: mime = 'application/octet-stream'

        file_metadata = {'name': filename, 'parents': [folder_id]}
        
        # Reset file để đọc từ đầu
        file_obj.seek(0)
        media = MediaIoBaseUpload(file_obj, mimetype=mime)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except Exception as e:
        return f"Error: {str(e)}"

# --- HÀM 3: ĐỌC FILE TỪ MÁY TÍNH ---
def get_pdf_text(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return f"Lỗi đọc file: {e}"

# --- GIAO DIỆN SIDEBAR ---
with st.sidebar:
    st.title("🎙️ Cấu hình & Drive")
    api_key = st.text_input("Nhập Google AI API Key:", type="password")
    
    st.divider()
    
    # Voice Chat
    st.subheader("🎤 Voice Chat")
    audio_bytes = mic_recorder(
        start_prompt="🔴 Bấm để Ghi âm",
        stop_prompt="⏹️ Bấm để Dừng",
        just_once=True,
        key='recorder'
    )
    
    st.divider()
    
    # Chế độ
    work_mode = st.radio(
        "Quy trình xử lý:",
        ["Research (Nghiên cứu)", "Drafting (Viết nháp)", "Academic Review (Phản biện)", "LaTeX Conversion"]
    )
    
    st.divider()
    
    # Upload & Auto-Save
    st.subheader("📂 Nạp & Lưu trữ")
    uploaded_files = st.file_uploader("Tải lên PDF:", type="pdf", accept_multiple_files=True)
    
    # Quản lý trạng thái đã lưu để không lưu trùng
    if 'saved_files' not in st.session_state:
        st.session_state.saved_files = []

    context_text = ""
    if uploaded_files:
        with st.spinner("Đang xử lý & Lưu Cloud..."):
            for f in uploaded_files:
                # --- TỰ ĐỘNG LƯU BẰNG OAUTH ---
                if f.name not in st.session_state.saved_files:
                    file_id = upload_to_drive(f, f.name)
                    if "Error" not in file_id:
                        st.toast(f"✅ Đã lưu '{f.name}' lên Drive!", icon="☁️")
                        st.session_state.saved_files.append(f.name)
                    else:
                        st.error(f"Lỗi lưu file '{f.name}': {file_id}")
                
                # Đọc nội dung
                text = get_pdf_text(f)
                context_text += f"\n--- TÀI LIỆU: {f.name} ---\n{text}\n"
            
            st.success(f"Đã nạp {len(uploaded_files)} file!")

# --- CẤU HÌNH AI ---
system_instruction = "Bạn là trợ lý học thuật Dissertation Master AI chuyên sâu."
if work_mode == "LaTeX Conversion": system_instruction += " Nhiệm vụ: Chuyển đổi sang LaTeX."
elif work_mode == "Academic Review": system_instruction += " Nhiệm vụ: Phản biện logic."
if context_text: system_instruction += f"\n\nCONTEXT TỪ PDF:\n{context_text}"

if "messages" not in st.session_state: st.session_state.messages = []

# --- GIAO DIỆN CHÍNH ---
st.title("🎓 Dissertation Master AI (Final)")
st.caption("Phiên bản OAuth: Lưu trữ không giới hạn vào Drive cá nhân")
st.markdown("---")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- XỬ LÝ INPUT ---
prompt = None

# Xử lý Voice
if audio_bytes and audio_bytes['bytes']:
    with st.spinner("🎧 Đang dịch giọng nói..."):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_webm:
                temp_webm.write(audio_bytes['bytes'])
                temp_webm_path = temp_webm.name
            
            wav_path = temp_webm_path.replace(".webm", ".wav")
            AudioSegment.from_file(temp_webm_path).export(wav_path, format="wav")
            
            r = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
                prompt = r.recognize_google(audio_data, language="vi-VN")
            
            os.remove(temp_webm_path); os.remove(wav_path)
        except: st.warning("Không nghe rõ.")

if not prompt: prompt = st.chat_input("Nhập câu hỏi...")

# --- TRẢ LỜI ---
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

# --- CÔNG CỤ CHO TIN NHẮN CUỐI CÙNG (CỐ ĐỊNH) ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    st.divider()
    st.write("### 🛠️ Công cụ xử lý:")
    
    doc = Document(); doc.add_heading('Draft', 0); doc.add_paragraph(last_msg)
    bio = BytesIO(); doc.save(bio); bio.seek(0)

    c1, c2, c3 = st.columns(3)
    with c1: st.download_button("📥 Tải về", data=bio, file_name="draft.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with c2:
        if st.button("☁️ Lưu bản nháp"):
            with st.spinner("Đang lưu..."):
                fid = upload_to_drive(bio, f"Response_{len(st.session_state.messages)}.docx")
                if "Error" not in fid: st.success("✅ Đã lưu!")
                else: st.error(f"Lỗi: {fid}")
    with c3:
        if st.button("🔊 Đọc"):
            try:
                with st.spinner("Đang đọc..."):
                    tts = gTTS(text=last_msg, lang='vi')
                    mp3 = BytesIO(); tts.write_to_fp(mp3); st.audio(mp3, format='audio/mp3')
            except: pass