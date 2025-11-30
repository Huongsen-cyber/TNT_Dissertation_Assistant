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
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Dissertation Master AI (Ultra)",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- HÀM HỖ TRỢ KẾT NỐI DRIVE (Dùng chung) ---
def get_drive_service():
    if "gcp_json" not in st.secrets:
        st.error("Lỗi: Chưa cấu hình Secrets gcp_json!")
        return None
    key_dict = json.loads(st.secrets["gcp_json"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return build('drive', 'v3', credentials=creds)

# --- HÀM 1: UPLOAD LÊN DRIVE ---
def upload_to_drive(file_obj, filename):
    try:
        service = get_drive_service()
        if not service: return "Lỗi kết nối"

        # ✅ ID THƯ MỤC CỦA BẠN
        folder_id = "1eojKKKoMk4uLBCLfCpVhgWnaoTtOiu8p"

        file_metadata = {'name': filename, 'parents': [folder_id]}
        file_obj.seek(0)
        media = MediaIoBaseUpload(file_obj, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except Exception as e:
        return f"Error: {str(e)}"

# --- HÀM 2: LẤY DANH SÁCH FILE TỪ DRIVE (MỚI) ---
def list_drive_files():
    try:
        service = get_drive_service()
        folder_id = "1eojKKKoMk4uLBCLfCpVhgWnaoTtOiu8p"
        # Lấy danh sách file trong thư mục, chưa bị xóa
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name, mimeType)",
            orderBy="createdTime desc" # File mới nhất lên đầu
        ).execute()
        return results.get('files', [])
    except: return []

# --- HÀM 3: ĐỌC NỘI DUNG FILE TỪ DRIVE (MỚI) ---
def read_drive_file(file_id, filename):
    try:
        service = get_drive_service()
        request = service.files().get_media(fileId=file_id)
        file_stream = BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        file_stream.seek(0)
        
        # Xử lý tùy theo đuôi file
        if filename.endswith(".pdf"):
            return get_pdf_text(file_stream)
        elif filename.endswith(".docx"):
            doc = Document(file_stream)
            return "\n".join([p.text for p in doc.paragraphs])
        else:
            return "⚠️ Định dạng file này chưa được hỗ trợ đọc (chỉ hỗ trợ PDF và DOCX)."
            
    except Exception as e:
        return f"Lỗi đọc file Drive: {e}"

# --- HÀM 4: ĐỌC FILE PDF TỪ MÁY TÍNH ---
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
    
    # 3. Nguồn tài liệu (TÍNH NĂNG MỚI)
    st.subheader("📂 Nguồn tài liệu")
    source_option = st.radio("Chọn nguồn:", ["Tải từ máy tính (Upload)", "Chọn từ Google Drive"])
    
    context_text = ""
    
    if source_option == "Tải từ máy tính (Upload)":
        uploaded_files = st.file_uploader("Tải lên PDF:", type="pdf", accept_multiple_files=True)
        if uploaded_files:
            with st.spinner("Đang đọc tài liệu..."):
                for pdf in uploaded_files:
                    text = get_pdf_text(pdf)
                    context_text += f"\n--- DOC: {pdf.name} ---\n{text}\n"
                st.success(f"Đã nạp {len(uploaded_files)} file!")
                
    else: # Chọn từ Google Drive
        if "gcp_json" in st.secrets:
            with st.spinner("Đang kết nối Drive..."):
                drive_files = list_drive_files()
                if drive_files:
                    # Tạo danh sách tên file để chọn
                    file_options = {f['name']: f['id'] for f in drive_files}
                    selected_filename = st.selectbox("Chọn file trên Drive:", list(file_options.keys()))
                    
                    if st.button("📖 Đọc file này"):
                        file_id = file_options[selected_filename]
                        with st.spinner(f"Đang tải và đọc {selected_filename}..."):
                            content = read_drive_file(file_id, selected_filename)
                            context_text += f"\n--- DRIVE DOC: {selected_filename} ---\n{content}\n"
                            st.success("Đã đọc xong! AI đã ghi nhớ nội dung.")
                            with st.expander("Xem nội dung trích xuất"):
                                st.write(content[:1000] + "...")
                else:
                    st.warning("Thư mục Drive trống hoặc không truy cập được.")
        else:
            st.error("Chưa cấu hình Secrets để kết nối Drive.")

# --- CẤU HÌNH AI & PROMPT ---
system_instruction = "Bạn là trợ lý học thuật Dissertation Master AI chuyên sâu."
if work_mode == "LaTeX Conversion":
    system_instruction += " Nhiệm vụ: Chuyển đổi nội dung sang code LaTeX chuẩn Overleaf."
elif work_mode == "Academic Review":
    system_instruction += " Nhiệm vụ: Đóng vai Reviewer khó tính, phản biện logic."

if context_text:
    system_instruction += f"\n\nCONTEXT TỪ TÀI LIỆU:\n{context_text}"

# --- SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- GIAO DIỆN CHÍNH ---
st.title("🎓 Dissertation Master AI (2-Way Sync)")
st.caption("Hỗ trợ: Voice Chat | Xuất Word | Lưu & Đọc Google Drive")
st.markdown("---")

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- XỬ LÝ INPUT (GIỌNG NÓI HOẶC PHÍM) ---
prompt = None

# Xử lý file ghi âm
if audio_bytes and audio_bytes['bytes']:
    with st.spinner("🎧 Đang xử lý giọng nói..."):
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
        except Exception as e:
            st.warning("Không nghe rõ. Vui lòng thử lại.")

# Nếu không có giọng, lấy từ ô chat
if not prompt:
    prompt = st.chat_input("Nhập câu hỏi hoặc yêu cầu...")

# --- XỬ LÝ TRẢ LỜI ---
if prompt:
    if not api_key:
        st.error("⚠️ Thiếu API Key! Vui lòng nhập bên trái."); st.stop()
    
    genai.configure(api_key=api_key)
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        try:
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

        except Exception as e:
            st.error(f"Lỗi hệ thống: {e}")

# --- CÔNG CỤ CHO TIN NHẮN CUỐI CÙNG ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    
    st.divider()
    st.write("### 🛠️ Công cụ xử lý:")
    
    # Tạo file Word
    doc = Document()
    doc.add_heading('Dissertation Assistant Draft', 0)
    doc.add_paragraph(last_msg)
    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)

    c1, c2, c3 = st.columns(3)
    
    # Nút 1: Tải về
    with c1:
        st.download_button("📥 Tải về máy", data=bio, file_name="draft.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    
    # Nút 2: Lưu lên Drive
    with c2:
        if st.button("☁️ Lưu lên Drive"):
            with st.spinner("Đang đẩy lên mây..."):
                file_id = upload_to_drive(bio, f"Draft_{len(st.session_state.messages)}.docx")
                if "Error" not in file_id:
                    st.success("✅ Đã lưu thành công!")
                else:
                    st.error(f"Lỗi: {file_id}")
                
    # Nút 3: Đọc giọng nói
    with c3:
        if st.button("🔊 Đọc to"):
            try:
                with st.spinner("🔊 Đang tạo giọng..."):
                    tts = gTTS(text=last_msg, lang='vi')
                    mp3_fp = BytesIO()
                    tts.write_to_fp(mp3_fp)
                    st.audio(mp3_fp, format='audio/mp3')
            except: st.warning("Lỗi đọc giọng.")