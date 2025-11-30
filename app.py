import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader
# --- THÊM THƯ VIỆN XỬ LÝ WORD ---
from docx import Document
from io import BytesIO
# --------------------------------

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Dissertation Master AI (Pro)",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- HÀM XỬ LÝ FILE PDF ---
def get_pdf_text(uploaded_file):
    """Hàm đọc và lấy toàn bộ chữ từ file PDF"""
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return f"Lỗi đọc file: {e}"

# --- SIDEBAR: CẤU HÌNH & UPLOAD ---
with st.sidebar:
    st.title("📚 Tài liệu & Cấu hình")
    
    api_key = st.text_input("Nhập Google AI API Key:", type="password")
    
    # Nút kiểm tra model (Giữ lại cho bạn)
    if api_key:
        if st.button("🔴 Kiểm tra tên Model"):
            try:
                genai.configure(api_key=api_key)
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                st.info("👇 Danh sách Model tài khoản bạn dùng được:")
                st.code(models)
            except Exception as e:
                st.error(f"Lỗi Key: {e}")

    st.divider()
    
    # 1. Chọn chế độ làm việc
    work_mode = st.radio(
        "Quy trình xử lý:",
        ["Research (Nghiên cứu)", "Drafting (Viết nháp)", "Academic Review (Phản biện)", "LaTeX Conversion"]
    )
    
    st.divider()
    
    # 2. Upload Tài liệu tham khảo
    st.subheader("📂 Nạp tài liệu tham khảo")
    uploaded_files = st.file_uploader(
        "Tải lên file PDF (Luận văn mẫu, bài báo...)", 
        type="pdf", 
        accept_multiple_files=True
    )
    
    # Xử lý văn bản từ PDF
    context_text = ""
    if uploaded_files:
        with st.spinner("Đang đọc tài liệu..."):
            for pdf in uploaded_files:
                text = get_pdf_text(pdf)
                context_text += f"\n--- TÀI LIỆU: {pdf.name} ---\n{text}\n"
            st.success(f"Đã nạp {len(uploaded_files)} tài liệu vào bộ nhớ AI!")
            
            with st.expander("Xem nội dung thô đã trích xuất"):
                st.text(context_text[:1000] + "...") 

# --- SYSTEM PROMPT ---
base_instruction = """
Bạn là 'Dissertation Master AI', trợ lý học thuật chuyên sâu.
Nhiệm vụ: Hỗ trợ viết, phản biện và định dạng luận văn khoa học.

QUY TẮC CỐT LÕI:
1. **Academic Tone:** Giọng văn khách quan, trang trọng.
2. **Evidence-Based:** Khi người dùng cung cấp tài liệu tham khảo, hãy ưu tiên sử dụng thông tin từ đó để trả lời và TRÍCH DẪN RÕ RÀNG (Ví dụ: [Tên file]).
3. **LaTeX:** Sử dụng định dạng $...$ cho công thức toán.
"""

if work_mode == "LaTeX Conversion":
    system_instruction = base_instruction + "\nNhiệm vụ: Chuyển đổi nội dung sang code LaTeX chuẩn Overleaf."
elif work_mode == "Academic Review (Phản biện)":
    system_instruction = base_instruction + "\nNhiệm vụ: Đóng vai Reviewer khó tính, chỉ ra lỗ hổng logic và phương pháp."
else:
    system_instruction = base_instruction

if context_text:
    system_instruction += f"\n\nDƯỚI ĐÂY LÀ DỮ LIỆU NỀN TẢNG (CONTEXT) TỪ CÁC FILE PDF NGƯỜI DÙNG CUNG CẤP:\n{context_text}"

# --- SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- GIAO DIỆN CHÍNH ---
st.title("🎓 Dissertation Master AI")
st.caption("Hệ thống hỗ trợ luận văn tích hợp đọc hiểu tài liệu")
st.markdown(f"**Chế độ:** `{work_mode}` | **Tài liệu đã nạp:** `{len(uploaded_files) if uploaded_files else 0}` file")
st.markdown("---")

# Hiển thị lịch sử chat
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- XỬ LÝ CHAT & XUẤT FILE ---
if prompt := st.chat_input("Hỏi về tài liệu hoặc yêu cầu viết..."):
    
    if not api_key:
        st.error("⚠️ Chưa nhập API Key!")
        st.stop()
        
    genai.configure(api_key=api_key)
    
    # Cấu hình Model
    generation_config = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 8192,
    }

    try:
        # Model Gemini 2.0 Flash (Bản xịn nhất của bạn)
        model = genai.GenerativeModel(
            model_name="models/gemini-2.0-flash", 
            generation_config=generation_config,
            system_instruction=system_instruction
        )

        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            
            chat_history = [
                {"role": m["role"], "parts": [m["content"]]} 
                for m in st.session_state.messages if m["role"] != "system"
            ]
            
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(prompt, stream=True)
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
            
            message_placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

            # --- TÍNH NĂNG MỚI: TẠO FILE WORD ---
            # 1. Tạo file word ảo trong bộ nhớ
            doc = Document()
            doc.add_heading('Dissertation Assistant Draft', 0) # Tiêu đề file
            doc.add_paragraph(full_response) # Nội dung AI trả lời
            
            # 2. Lưu vào bộ đệm (RAM)
            bio = BytesIO()
            doc.save(bio)
            
            # 3. Hiển thị nút tải về
            st.download_button(
                label="📥 Tải câu trả lời này về máy (.docx)",
                data=bio.getvalue(),
                file_name="Luan_van_draft.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            # --------------------------------------
            
    except Exception as e:
        st.error(f"Đã xảy ra lỗi hệ thống: {e}")