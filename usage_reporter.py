import json
import sqlite3
import requests
import os
import time

import config
# --- تنظیمات ---
# آدرس کامل فایل api.php در سرور ایران
API_URL = config.server_address
# این کلید باید دقیقا مشابه کلید در فایل api.php باشد
API_KEY = config.api_token

# --- پایان تنظیمات ---

DB_URL = "/etc/x-ui/x-ui.db"
# DB_URL = "x-ui.db"

def get_my_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        print(f"Could not get IP: {e}")
        return "127.0.0.1"

def send_api_request(endpoint, data=None, method='POST'):
    """یک تابع جامع برای ارسال درخواست به API"""
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }
    url = f"{API_URL}?action={endpoint}"
    
    try:
        if method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=30)
        elif method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")

        response.raise_for_status()  # برای خطاهای HTTP (4xx, 5xx) یک استثنا ایجاد می‌کند
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error communicating with API at endpoint '{endpoint}': {e}")
        return None

def find_id_with_email(conn, email):
    """از کانکشن موجود برای یافتن اطلاعات کاربر استفاده می‌کند"""
    sql = "SELECT settings, id, port FROM inbounds WHERE `settings` LIKE ? LIMIT 1"
    cursor = conn.cursor()
    cursor.execute(sql, (f'%{email}%',))
    main_data = cursor.fetchone()
    
    if not main_data:
        return None
        
    settings_json, inbound_id, port = main_data
    clients = json.loads(settings_json)

    for client in clients['clients']:
        if client.get('email') == str(email):
            return {'id': client.get('id'), "inbound_id": inbound_id, "port": port}
    return None

def report_usage():
    print("Starting usage reporting...")
    my_ip = get_my_ip()
    conn = None
    try:
        conn = sqlite3.connect(DB_URL)
        cursor = conn.cursor()
        
        sql = "SELECT email, up, down FROM client_traffics WHERE `enable` = 1"
        cursor.execute(sql)
        all_traffics = cursor.fetchall()

        usages_payload = []
        for email, up, down in all_traffics:
            if up == 0 and down == 0:
                continue # از ارسال داده‌های صفر خودداری می‌کنیم

            inbound_data = find_id_with_email(conn, email)
            if inbound_data:
                usages_payload.append({
                    "email": email,
                    "user_id": inbound_data.get('id', 'N/A'),
                    "up": up,
                    "down": down,
                    "ip": my_ip,
                    "port": inbound_data.get('port', 0)
                })

        if not usages_payload:
            print("No new usage data to report.")
            return

        print(f"Reporting usage for {len(usages_payload)} users...")
        response = send_api_request('report_usage', data=usages_payload, method='POST')

        if response and response.get('status') == 'success':
            print("Usage data successfully sent to the central server.")
            print(response.get('message'))
        else:
            print("Failed to send usage data.")
            if response:
                print(f"API Response: {response.get('message')}")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()

def restart_xui_in_thread():
    print("Restarting x-ui service...")
    # بهتر است به جای ریستارت کامل، فقط کانفیگ را ریلود کنید اگر امکانش هست
    os.system("x-ui restart") # دستور ریستارت در پنل x-ui معمولا این است
    time.sleep(2) # کمی صبر برای بالا آمدن سرویس
    print("x-ui restarted.")

if __name__ == "__main__":
    report_usage()
    # ریستارت x-ui بعد از گزارش مصرف شاید ضروری نباشد، اما طبق کد قبلی شما حفظ شده
    restart_xui_in_thread()
