import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader
from docx import Document
from io import BytesIO

# --- THƯ VIỆN XỬ LÝ GIỌNG NÓI ---
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
from gtts import gTTS
import tempfile
import os
# --------------------------------

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Dissertation Master AI (Pro Max)",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- HÀM XỬ LÝ FILE PDF ---
def get_pdf_text(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return f"Lỗi đọc file: {e}"

# --- SIDEBAR ---
with st.sidebar:
    st.title("🎙️ Cấu hình & Voice")
    
    api_key = st.text_input("Nhập Google AI API Key:", type="password")
    
    st.divider()
    
    # --- KHU VỰC VOICE CHAT (MỚI) ---
    st.subheader("🎤 Voice Chat")
    st.info("Nhấn nút bên dưới để nói (thay vì gõ phím)")
    
    # Widget ghi âm
    audio_bytes = mic_recorder(
        start_prompt="🔴 Bấm để Ghi âm",
        stop_prompt="⏹️ Bấm để Dừng",
        just_once=True,
        key='recorder'
    )
    # --------------------------------
    
    st.divider()
    
    # 1. Chế độ
    work_mode = st.radio(
        "Quy trình xử lý:",
        ["Research (Nghiên cứu)", "Drafting (Viết nháp)", "Academic Review (Phản biện)", "LaTeX Conversion"]
    )
    
    st.divider()
    
    # 2. Upload
    st.subheader("📂 Tài liệu tham khảo")
    uploaded_files = st.file_uploader("Tải lên PDF:", type="pdf", accept_multiple_files=True)
    
    context_text = ""
    if uploaded_files:
        with st.spinner("Đang đọc tài liệu..."):
            for pdf in uploaded_files:
                text = get_pdf_text(pdf)
                context_text += f"\n--- TÀI LIỆU: {pdf.name} ---\n{text}\n"
            st.success(f"Đã nạp {len(uploaded_files)} file!")

# --- SYSTEM PROMPT ---
base_instruction = """
Bạn là 'Dissertation Master AI', trợ lý học thuật chuyên sâu.
Nhiệm vụ: Hỗ trợ viết, phản biện và định dạng luận văn khoa học.
QUY TẮC: Academic Tone, Evidence-Based, LaTeX format.
"""
if work_mode == "LaTeX Conversion":
    system_instruction = base_instruction + "\nNhiệm vụ: Chuyển đổi sang LaTeX chuẩn Overleaf."
elif work_mode == "Academic Review (Phản biện)":
    system_instruction = base_instruction + "\nNhiệm vụ: Đóng vai Reviewer khó tính."
else:
    system_instruction = base_instruction

if context_text:
    system_instruction += f"\n\nCONTEXT TỪ PDF:\n{context_text}"

# --- SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- GIAO DIỆN CHÍNH ---
st.title("🎓 Dissertation Master AI (Voice Edition)")
st.caption("Hỗ trợ: Đọc PDF | Xuất Word | Trò chuyện Giọng nói")
st.markdown("---")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- XỬ LÝ INPUT (ƯU TIÊN GIỌNG NÓI TRƯỚC) ---
prompt = None

# 1. Kiểm tra xem có dữ liệu âm thanh từ Sidebar không
if audio_bytes and audio_bytes['bytes']:
    with st.spinner("🎧 Đang nghe bạn nói..."):
        # Lưu file tạm để thư viện SpeechRecognition đọc
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(audio_bytes['bytes'])
            temp_audio_path = temp_audio.name
        
        # Dùng Google để chuyển Âm thanh -> Văn bản
        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_audio_path) as source:
            audio_data = recognizer.record(source)
            try:
                # Nhận diện tiếng Việt
                voice_text = recognizer.recognize_google(audio_data, language="vi-VN")
                prompt = voice_text # Gán văn bản nói vào biến prompt
                # Xóa file tạm
                os.remove(temp_audio_path)
            except Exception as e:
                st.warning("Không nghe rõ, vui lòng nói lại hoặc gõ phím.")

# 2. Nếu không nói, thì kiểm tra ô chat nhập phím
if not prompt:
    prompt = st.chat_input("Hỏi về tài liệu hoặc yêu cầu viết...")

# --- XỬ LÝ CHAT & TRẢ LỜI ---
if prompt:
    if not api_key:
        st.error("⚠️ Chưa nhập API Key!")
        st.stop()
        
    genai.configure(api_key=api_key)
    
    # Hiển thị câu hỏi của người dùng
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # AI Trả lời
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        try:
            # Dùng model xịn nhất bạn có
            model = genai.GenerativeModel(
                model_name="models/gemini-2.0-flash", 
                system_instruction=system_instruction
            )
            
            chat_history = [{"role": m["role"], "parts": [m["content"]]} for m in st.session_state.messages if m["role"] != "system"]
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(prompt, stream=True)
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
            
            message_placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

            # --- TÍNH NĂNG 1: TẠO FILE WORD ---
            doc = Document()
            doc.add_heading('Dissertation Assistant Draft', 0)
            doc.add_paragraph(full_response)
            bio = BytesIO()
            doc.save(bio)
            
            col1, col2 = st.columns([1, 1])
            with col1:
                st.download_button(
                    label="📥 Tải Word (.docx)",
                    data=bio.getvalue(),
                    file_name="Luan_van_draft.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            
            # --- TÍNH NĂNG 2: ĐỌC THÀNH TIẾNG (TTS) ---
            with col2:
                # Chỉ đọc nếu văn bản không quá dài (để tránh lỗi load lâu)
                if len(full_response) < 1000: 
                    try:
                        tts = gTTS(text=full_response, lang='vi')
                        # Lưu vào buffer bộ nhớ thay vì file cứng để nhanh hơn
                        mp3_fp = BytesIO()
                        tts.write_to_fp(mp3_fp)
                        st.audio(mp3_fp, format='audio/mp3')
                    except:
                        st.info("Văn bản quá dài hoặc lỗi kết nối TTS.")
                else:
                    st.info("🔇 Văn bản dài, tự động tắt đọc tiếng để tối ưu.")

        except Exception as e:
            st.error(f"Lỗi: {e}")