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

# --- THƯ VIỆN GOOGLE DRIVE ---
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Dissertation Master AI (Ultra)",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- HÀM 1: KẾT NỐI GOOGLE DRIVE ---
def upload_to_drive(file_obj, filename):
    try:
        # Lấy chìa khóa từ Secrets (Két sắt Streamlit)
        if "gcp_json" not in st.secrets:
            return "Lỗi: Chưa cấu hình Secrets gcp_json trên Streamlit Cloud!"
            
        key_dict = json.loads(st.secrets["gcp_json"])
        creds = service_account.Credentials.from_service_account_info(key_dict)
        service = build('drive', 'v3', credentials=creds)

        # ✅ ĐÃ ĐIỀN SẴN ID THƯ MỤC CỦA BẠN (Luu_Tru_Luan_Van)
        folder_id = "1eojKKKoMk4uLBCLfCpVhgWnaoTtOiu8p"

        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaIoBaseUpload(file_obj, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except Exception as e:
        return f"Error: {str(e)}"

# --- HÀM 2: ĐỌC FILE PDF ---
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
    
    # 1. Voice Chat
    st.subheader("🎤 Voice Chat")
    st.info("Nhấn nút đỏ để nói:")
    audio_bytes = mic_recorder(
        start_prompt="🔴 Bấm để Ghi âm",
        stop_prompt="⏹️ Bấm để Dừng",
        just_once=True,
        key='recorder'
    )
    
    st.divider()
    
    # 2. Chế độ
    work_mode = st.radio(
        "Quy trình xử lý:",
        ["Research (Nghiên cứu)", "Drafting (Viết nháp)", "Academic Review (Phản biện)", "LaTeX Conversion"]
    )
    
    st.divider()
    
    # 3. Upload PDF
    st.subheader("📂 Tài liệu tham khảo")
    uploaded_files = st.file_uploader("Tải lên PDF:", type="pdf", accept_multiple_files=True)
    
    context_text = ""
    if uploaded_files:
        with st.spinner("Đang đọc tài liệu..."):
            for pdf in uploaded_files:
                text = get_pdf_text(pdf)
                context_text += f"\n--- DOC: {pdf.name} ---\n{text}\n"
            st.success(f"Đã nạp {len(uploaded_files)} file!")

# --- CẤU HÌNH AI & PROMPT ---
system_instruction = "Bạn là trợ lý học thuật Dissertation Master AI chuyên sâu."
if work_mode == "LaTeX Conversion":
    system_instruction += " Nhiệm vụ: Chuyển đổi nội dung sang code LaTeX chuẩn Overleaf."
elif work_mode == "Academic Review":
    system_instruction += " Nhiệm vụ: Đóng vai Reviewer khó tính, phản biện logic."

if context_text:
    system_instruction += f"\n\nCONTEXT TỪ PDF:\n{context_text}"

# --- SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- GIAO DIỆN CHÍNH ---
st.title("🎓 Dissertation Master AI (Drive Edition)")
st.caption("Hỗ trợ: Voice Chat | Xuất Word | Lưu Google Drive Tự động")
st.markdown("---")

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- XỬ LÝ INPUT (GIỌNG NÓI HOẶC PHÍM) ---
prompt = None

# Xử lý file ghi âm (Chuyển WebM -> WAV -> Text)
if audio_bytes and audio_bytes['bytes']:
    with st.spinner("🎧 Đang nghe và dịch giọng nói..."):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_webm:
                temp_webm.write(audio_bytes['bytes'])
                temp_webm_path = temp_webm.name
            
            # Chuyển đổi định dạng bằng Pydub (Sửa lỗi ValueError)
            wav_path = temp_webm_path.replace(".webm", ".wav")
            AudioSegment.from_file(temp_webm_path).export(wav_path, format="wav")
            
            # Nhận diện giọng nói
            r = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
                prompt = r.recognize_google(audio_data, language="vi-VN")
            
            # Dọn dẹp file tạm
            os.remove(temp_webm_path)
            os.remove(wav_path)
        except Exception as e:
            st.warning("Không nghe rõ. Vui lòng thử lại.")

# Nếu không có giọng nói, lấy từ ô chat
if not prompt:
    prompt = st.chat_input("Nhập câu hỏi hoặc yêu cầu...")

# --- XỬ LÝ TRẢ LỜI ---
if prompt:
    if not api_key:
        st.error("⚠️ Thiếu API Key! Vui lòng nhập bên trái."); st.stop()
    
    genai.configure(api_key=api_key)
    
    # Hiện câu hỏi
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # AI Trả lời
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        try:
            # Model Gemini 2.0 Flash
            model = genai.GenerativeModel("models/gemini-2.0-flash", system_instruction=system_instruction)
            
            chat_history = [{"role": m["role"], "parts": [m["content"]]} for m in st.session_state.messages if m["role"] != "system"]
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(prompt, stream=True)
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
            
            message_placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

            # --- CÁC NÚT CHỨC NĂNG SAU KHI TRẢ LỜI ---
            
            # Tạo file Word trong RAM
            doc = Document()
            doc.add_heading('Dissertation Assistant Draft', 0)
            doc.add_paragraph(full_response)
            bio = BytesIO()
            doc.save(bio)
            bio.seek(0)

            col1, col2, col3 = st.columns([1, 1, 1])
            
            # Nút 1: Tải về máy
            with col1:
                st.download_button(
                    label="📥 Tải về máy",
                    data=bio.getvalue(),
                    file_name="Luan_van_draft.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            
            # Nút 2: Lưu lên Drive
            with col2:
                if st.button("☁️ Lưu lên Drive"):
                    with st.spinner("Đang đẩy lên mây..."):
                        file_id = upload_to_drive(bio, f"Draft_{len(st.session_state.messages)}.docx")
                        if file_id and "Error" not in file_id:
                            st.success("✅ Đã lưu thành công!")
                        else:
                            st.error(f"Lỗi lưu Drive (Kiểm tra lại Secrets): {file_id}")
            
            # Nút 3: Đọc giọng nói (TTS)
            with col3:
                try:
                    with st.spinner("🔊 Đang tạo giọng..."):
                        tts = gTTS(text=full_response, lang='vi')
                        mp3_fp = BytesIO()
                        tts.write_to_fp(mp3_fp)
                        st.audio(mp3_fp, format='audio/mp3')
                except Exception as e:
                    st.warning(f"Lỗi đọc giọng: {e}")

        except Exception as e:
            st.error(f"Lỗi hệ thống: {e}")