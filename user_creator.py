import json
import sqlite3
import requests
import os
import time
import jdatetime
import string
import random
import ipaddress
import config

# --- تنظیمات ---
# آدرس کامل فایل api.php در سرور ایران
API_URL = config.server_address
# این کلید باید دقیقا مشابه کلید در فایل api.php باشد
API_KEY = config.api_token


DB_URL = "/etc/x-ui/x-ui.db"
# DB_URL = "x-ui.db"

# --- توابع کمکی (بسیاری از آن‌ها از کد قبلی شما هستند) ---
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

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error communicating with API at endpoint '{endpoint}': {e}")
        return None

def randomStringDigits(stringLength=16):
    lettersAndDigits = string.ascii_letters + string.digits
    return ''.join(random.choice(lettersAndDigits) for i in range(stringLength))

def create_user_local(conn, inbound_port, uuid, total_gb, title, expire_days):
    """تابع اصلی برای ساخت کاربر در دیتابیس محلی SQLite (با اصلاحات)"""
    
    # --- تغییرات کلیدی اینجا هستند ---
    # 1. از float() برای پذیرش اعداد اعشاری در حجم ترافیک استفاده می‌کنیم.
    # 2. از (total_gb or 0) استفاده می‌کنیم تا اگر مقدار None یا خالی بود، به 0 تبدیل شود.
    safe_total_gb = float(total_gb or 0)
    total_bytes = safe_total_gb * 1024 * 1024 * 1024
    
    # همین کار را برای روزهای انقضا هم انجام می‌دهیم تا کد قوی‌تر شود.
    safe_expire_days = int(expire_days or 0)
    expire_timestamp = ((safe_expire_days * 86400) + int(time.time())) * 1000 if safe_expire_days > 0 else 0
    # --- پایان تغییرات ---

    cursor = conn.cursor()

    # چک کردن تکراری بودن کاربر
    cursor.execute("SELECT id FROM client_traffics WHERE email = ?", (title,))
    if cursor.fetchone():
        return {"status": "error", "message": "title already exists"}

    # پیدا کردن اینباند
    cursor.execute("SELECT settings, id FROM inbounds WHERE port = ? LIMIT 1", (int(inbound_port),))
    inbound_data = cursor.fetchone()
    if not inbound_data:
        return {"status": "error", "message": f"Inbound with port {inbound_port} not found"}
    
    settings_json, inbound_id = inbound_data
    settings = json.loads(settings_json)
    
    # چک کردن تکراری بودن uuid
    for client in settings.get('clients', []):
        if client.get('id') == str(uuid):
            return {"status": "error", "message": "uuid already exists"}

    # ساختن کلاینت جدید
    if not settings.get('clients'):
        return {"status": "error", "message": "No client template found in inbound"}

    new_client = settings['clients'][0].copy()
    new_client.update({
        'id': str(uuid),
        'email': str(title),
        'totalGB': int(total_bytes), # پنل x-ui این مقدار را به صورت عدد صحیح می‌خواهد
        'expiryTime': int(expire_timestamp),
        'enable': True,
        'subId': randomStringDigits()
    })
    
    settings['clients'].append(new_client)
    
    try:
        # آپدیت جدول inbounds
        cursor.execute("UPDATE inbounds SET settings = ? WHERE id = ?", (json.dumps(settings, indent=4), inbound_id))
        
        # افزودن به جدول client_traffics
        sql_traffic = """
            INSERT INTO client_traffics (inbound_id, enable, email, up, down, total, expiry_time) 
            VALUES (?, 1, ?, 0, 0, ?, ?)
        """
        cursor.execute(sql_traffic, (inbound_id, title, int(total_bytes), int(expire_timestamp)))
        
        conn.commit()
        return {"status": "success", "message": "User created locally"}
    except sqlite3.Error as e:
        conn.rollback()
        return {"status": "error", "message": f"SQLite error: {e}"}


def insert_new_users():
    print("Checking for new users to create...")
    
    # 1. گرفتن لیست کاربران جدید از سرور مرکزی
    response = send_api_request('get_new_users', method='GET')
    
    if not response or response.get('status') != 'success':
        print("Failed to get new users from the central server or no new users.")
        if response:
            print(f"API Response: {response.get('message')}")
        return

    new_users = response.get('data', [])
    if not new_users:
        print("No new users assigned to this server.")
        return

    print(f"Found {len(new_users)} new user(s) to create.")
    conn = None
    try:
        conn = sqlite3.connect(DB_URL)
        created_count = 0
        for user in new_users:
            token = user.get('token')
            item_id = user.get('item_id')
            user_token_unique = f"{token}_{item_id}"
            
            print(f"Processing user: {user_token_unique}")
            
            # 2. ایجاد کاربر در دیتابیس محلی
            result = create_user_local(
                conn=conn,
                inbound_port=user.get('config_port'),
                uuid=user.get('uuid'),
                total_gb=user.get('usage_max'),
                title=user_token_unique,
                expire_days=user.get('DAY')
            )
            
            if result.get('status') == 'success':
                print(f"User {user_token_unique} created locally. Confirming with central server...")
                
                # 3. تایید ساخت کاربر به سرور مرکزی
                confirm_payload = {
                    "user_token": user_token_unique,
                    "config_id": user.get('config_tag_id') # یا هر فیلد دیگری که به عنوان config_id استفاده می‌کنید
                }
                confirm_response = send_api_request('confirm_user_creation', data=confirm_payload, method='POST')
                
                if confirm_response and confirm_response.get('status') == 'success':
                    print(f"Confirmation for {user_token_unique} was successful.")
                    created_count += 1
                else:
                    print(f"Failed to confirm creation for {user_token_unique}.")
                    if confirm_response: print(f"API Response: {confirm_response.get('message')}")
            
            elif result.get('message') in ["title already exists", "uuid already exists"]:
                 print(f"User {user_token_unique} seems to exist already. Confirming with server just in case.")
                 confirm_payload = { "user_token": user_token_unique, "config_id": user.get('config_tag_id') }
                 send_api_request('confirm_user_creation', data=confirm_payload, method='POST')

            else:
                print(f"Failed to create user {user_token_unique} locally. Reason: {result.get('message')}")

        if created_count > 0:
            print(f"\nTotal of {created_count} users created. Restarting x-ui to apply changes.")
            restart_xui_in_thread()
        else:
            print("\nNo new users were successfully created in this run.")
            
    except sqlite3.Error as e:
        print(f"A general SQLite error occurred: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during user creation process: {e}")
    finally:
        if conn:
            conn.close()

def restart_xui_in_thread():
    print("Restarting x-ui service...")
    os.system("x-ui restart")
    time.sleep(2)
    print("x-ui restarted.")


if __name__ == "__main__":
    insert_new_users()
