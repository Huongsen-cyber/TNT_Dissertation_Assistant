from google_auth_oauthlib.flow import InstalledAppFlow
import os
import json

# --- QUAN TRỌNG: QUYỀN TRUY CẬP TOÀN BỘ DRIVE ---
# Thay vì 'drive.file', ta dùng 'drive' để đọc được cả file cũ của bạn
SCOPES = ['https://www.googleapis.com/auth/drive']

def main():
    if not os.path.exists('credentials.json'):
        print("❌ LỖI: Không tìm thấy file 'credentials.json'.")
        return

    print("🚀 Đang mở trình duyệt... Hãy cấp quyền cho App nhé!")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        
        # Chạy server xác thực
        creds = flow.run_local_server(port=0)
        
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
            "universe_domain": "googleapis.com",
            "account": "",
            "expiry": "2025-01-01T00:00:00Z"
        }

        json_str = json.dumps(token_data, indent=4)

        print("\n" + "="*60)
        print("✅ ĐÃ LẤY TOKEN TOÀN QUYỀN - COPY ĐOẠN DƯỚI ĐÂY VÀO SECRETS:")
        print("="*60)
        print(f'oauth_token = """\n{json_str}\n"""')
        print("="*60)
        input("Nhấn Enter để thoát...")
        
    except Exception as e:
        print(f"❌ Có lỗi: {e}")

if __name__ == '__main__':
    main()