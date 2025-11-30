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

# --- ID THƯ MỤC DRIVE CỦA BẠN ---
# Tất cả file sẽ được đọc từ đây và lưu vào đây
FOLDER_ID = "1eojKKKoMk4uLBCLfCpVhgWnaoTtOiu8p"

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

def upload_to_drive(file_obj, filename):
    """Upload file lên Drive (Tạo mới)"""
    try:
        service = get_drive_service()
        if not service: return "Lỗi kết nối"

        # Tự động thêm thời gian vào tên file để không bị trùng
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        final_filename = f"{filename.replace('.docx', '')}_{timestamp}.docx"

        file_metadata = {'name': final_filename, 'parents': [FOLDER_ID]}
        file_obj.seek(0)
        media = MediaIoBaseUpload(file_obj, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except Exception as e:
        return f"Error: {str(e)}"

def list_drive_files():
    """Lấy danh sách tất cả file trong thư mục"""
    try:
        service = get_drive_service()
        if not service: return []
        # Lấy file trong thư mục, không bị xóa, sắp xếp theo tên
        results = service.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed=false",
            fields="files(id, name, mimeType)",
            orderBy="name" 
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
            return "" 
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
    st.title("🎙️ Trung tâm Điều khiển")
    api_key = st.text_input("Nhập Google AI API Key:", type="password")
    
    st.divider()
    # Voice
    st.subheader("🎤 Ra lệnh giọng nói")
    audio_bytes = mic_recorder(start_prompt="🔴 Ghi âm", stop_prompt="⏹️ Dừng", just_once=True, key='recorder')
    
    st.divider()
    work_mode = st.radio("Chế độ làm việc:", ["Nghiên cứu & Tóm tắt", "Viết nháp (Drafting)", "Phản biện & Kiểm tra chéo", "Chuyển đổi LaTeX"])
    
    st.divider()
    # --- NGUỒN TÀI LIỆU ---
    st.subheader("📂 Dữ liệu Luận án")
    source_option = st.radio("Nguồn dữ liệu:", ["Tải từ máy tính", "Chọn 1 file trên Drive", "🚀 ĐỌC TOÀN BỘ DRIVE"])
    
    # Biến toàn cục lưu nội dung
    if 'global_context' not in st.session_state: st.session_state.global_context = ""
    if 'file_list_str' not in st.session_state: st.session_state.file_list_str = ""

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

    # 2. CHỌN 1 FILE DRIVE
    elif source_option == "Chọn 1 file trên Drive":
        with st.spinner("Đang tải danh sách..."):
            drive_files = list_drive_files()
            if drive_files:
                file_opts = {f['name']: f['id'] for f in drive_files}
                selected_name = st.selectbox("Chọn file:", list(file_opts.keys()))
                if st.button("📖 Đọc file này"):
                    with st.spinner("Đang đọc..."):
                        content = read_drive_file(file_opts[selected_name], selected_name)
                        st.session_state.global_context = f"\n=== TÀI LIỆU DRIVE: {selected_name} ===\n{content}\n"
                        st.success(f"Đã đọc xong!")
            else: st.warning("Thư mục Drive trống.")

    # 3. ĐỌC TOÀN BỘ (DÀNH CHO KIỂM TRA CHÉO)
    elif source_option == "🚀 ĐỌC TOÀN BỘ DRIVE":
        st.info("Chế độ này sẽ đọc tất cả các chương trong thư mục để AI có cái nhìn tổng thể.")
        if st.button("📚 Quét & Đọc tất cả"):
            drive_files = list_drive_files()
            if drive_files:
                progress_bar = st.progress(0)
                temp_all_ctx = ""
                file_names = []
                total = len(drive_files)
                status = st.empty()
                
                for i, f in enumerate(drive_files):
                    status.text(f"Đang đọc ({i+1}/{total}): {f['name']}...")
                    content = read_drive_file(f['id'], f['name'])
                    if content:
                        temp_all_ctx += f"\n=== CHƯƠNG/TÀI LIỆU: {f['name']} ===\n{content}\n"
                        file_names.append(f['name'])
                    progress_bar.progress((i + 1) / total)
                
                st.session_state.global_context = temp_all_ctx
                st.session_state.file_list_str = ", ".join(file_names)
                status.empty()
                st.success(f"✅ Đã thuộc lòng {total} tài liệu! Sẵn sàng kiểm tra chéo.")
            else: st.warning("Thư mục trống.")

# --- CẤU HÌNH AI ---
system_instruction = "Bạn là 'Dissertation Master AI', trợ lý nghiên cứu sinh Tiến sĩ chuyên nghiệp."
if work_mode == "Phản biện & Kiểm tra chéo":
    system_instruction += """
    NHIỆM VỤ: Kiểm tra tính nhất quán giữa các chương, tìm lỗ hổng logic, so sánh đối chiếu các luận điểm.
    YÊU CẦU: Chỉ ra cụ thể mâu thuẫn nằm ở file nào, chương nào.
    """
elif work_mode == "Viết nháp (Drafting)":
    system_instruction += " NHIỆM VỤ: Hỗ trợ viết nội dung học thuật, văn phong trang trọng."

# Nhồi toàn bộ kiến thức đã đọc vào não AI
if st.session_state.global_context:
    system_instruction += f"\n\nDỮ LIỆU NỀN TẢNG TỪ CÁC FILE ĐÃ ĐỌC:\n{st.session_state.global_context}"

if "messages" not in st.session_state: st.session_state.messages = []

# --- GIAO DIỆN CHÍNH ---
st.title("🎓 Dissertation Master AI")
if st.session_state.file_list_str:
    st.caption(f"🧠 Đang nhớ kiến thức từ: {st.session_state.file_list_str}")
else:
    st.caption("☁️ Đã kết nối Google Drive: Luu_Tru_Luan_Van")
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

if not prompt: prompt = st.chat_input("Nhập câu hỏi (Ví dụ: Kiểm tra mâu thuẫn giữa Chương 1 và 3)...")

# GENERATE
if prompt:
    if not api_key: st.error("Thiếu API Key!"); st.stop()
    genai.configure(api_key=api_key)
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    with st.chat_message("assistant"):
        ph = st.empty(); full_res = ""
        try:
            # Dùng Gemini 2.0 Flash (Context lớn) để chứa hết nội dung các chương
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
    
    # Tạo file Word
    doc = Document(); doc.add_heading('AI Response / Review Note', 0); doc.add_paragraph(last_msg)
    bio = BytesIO(); doc.save(bio); bio.seek(0)

    c1, c2, c3 = st.columns(3)
    
    # Nút Tải về máy
    with c1: st.download_button("📥 Tải về máy", data=bio, file_name="AI_Review.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    
    # Nút Lưu Drive (Tạo file mới để sửa online)
    with c2:
        if st.button("☁️ Lưu file Review lên Drive"):
            with st.spinner("Đang lưu lên đám mây..."):
                # Tên file sẽ là: Review_Result_20251030_1200.docx
                fid = upload_to_drive(bio, "Review_Result.docx")
                if "Error" not in fid: st.success("✅ Đã lưu! Bạn có thể mở Drive để sửa online.")
                else: st.error(f"Lỗi: {fid}")
    
    # Nút Đọc
    with c3:
        if st.button("🔊 Đọc to"):
            try:
                with st.spinner("Đang đọc..."):
                    tts = gTTS(text=last_msg, lang='vi')
                    mp3 = BytesIO(); tts.write_to_fp(mp3); st.audio(mp3, format='audio/mp3')
            except: pass