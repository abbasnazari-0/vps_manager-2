#!/bin/bash

# --- بخش جدید: دریافت آدرس API و اعتبارسنجی آن ---

# 1. دریافت آدرس API از کاربر
read -p "لطفا آدرس کامل API Endpoint پنل را وارد کنید (مثال: http://yourdomain.com/api/v1/server/): " server_address

# بررسی اینکه آیا ورودی خالی است یا نه
if [ -z "$server_address" ]; then
    echo "خطا: آدرس API وارد نشده است. اسکریپت متوقف شد."
    exit 1
fi

echo "درحال بررسی اعتبار آدرس API..."

# 2. ارسال درخواست و ذخیره پاسخ
# از -s برای حالت سکوت (بدون نمایش progress bar) و -m 5 برای 5 ثانیه таймаут استفاده می‌کنیم
response=$(curl -s -m 10 "$server_address")

# 3. پاسخ مورد انتظار را تعریف می‌کنیم
expected_response='{"status":"error","message":"Unauthorized"}'

# 4. مقایسه پاسخ دریافتی با پاسخ مورد انتظار
if [[ "$response" == "$expected_response" ]]; then
    echo "✅ آدرس API معتبر است. ادامه مراحل نصب..."
else
    echo "❌ خطا: آدرس API نامعتبر است یا به درستی پاسخ نمی‌دهد."
    echo "--------------------------------------------------------"
    echo "پاسخ مورد انتظار: $expected_response"
    echo "پاسخ دریافت شده: $response"
    echo "--------------------------------------------------------"
    echo "لطفا آدرس را بررسی کرده و اسکریپت را مجددا اجرا کنید. نصب متوقف شد."
    exit 1
fi

# --- پایان بخش اعتبارسنجی ---


# حالا که آدرس معتبر است، توکن را می‌پرسیم
read -p "لطفا توکن API پنل را وارد کنید: " api_token


echo "شروع مراحل نصب سرور منیجر..."
# install server manager
apt-get update
apt-get install python3 python3-pip unzip nginx gunicorn -y

pkill gunicorn

rm -rf servermanager/ vps_manager/ v11.zip nohup.out v10.zip v12.zip

rm -rf vps_manager && git clone https://github.com/abbasnazari-0/vps_manager.git

# ایجاد فایل کانفیگ در همین ابتدا با اطلاعاتی که گرفته‌ایم
echo "ایجاد فایل کانفیگ..."
echo -e "server_address = '$server_address'\napi_token='$api_token'" | tee vps_manager/config.py

mv vps_manager/servermanager /etc/nginx/sites-enabled/servermanager
# بررسی وجود فایل default قبل از حذف آن
if [ -L /etc/nginx/sites-enabled/default ]; then
    unlink /etc/nginx/sites-enabled/default
fi
nginx -s reload

pip3 install flask jdatetime jsonpickle psutil mysql-connector-python

# حذف سرویس قبلی اگر وجود داشته باشد تا از تداخل جلوگیری شود
if [ -f /etc/systemd/system/manager_vps.service ]; then
    sudo systemctl stop manager_vps.service
    rm /etc/systemd/system/manager_vps.service
fi

echo "[Unit]
Description=VPS MANAGER SERVICE
After=network.target
StartLimitIntervalSec=0
[Service]
Type=simple
Restart=always
RuntimeMaxSec=6h
RestartSec=1
User=root
ExecStart=gunicorn -w 3 vps_manager:app --bind 0.0.0.0:4000
WorkingDirectory=/root/

[Install]
WantedBy=multi-user.target
" > /etc/systemd/system/manager_vps.service

sudo systemctl daemon-reload
sudo systemctl enable manager_vps.service
sudo systemctl restart manager_vps.service

echo ""
echo ""
echo "=========================================="
echo "✅ نصب منیجر با موفقیت انجام شد."
echo "=========================================="
echo ""

# افزودن جاب‌ها به کرون‌تب
echo "افزودن جاب‌های گزارش‌دهی به crontab..."
(crontab -l 2>/dev/null | grep -v '/usr/bin/python3 /root/vps_manager/usage_reporter.py'; echo '*/10 * * * * /usr/bin/python3 /root/vps_manager/usage_reporter.py') | crontab -
(crontab -l 2>/dev/null | grep -v '/usr/bin/python3 /root/vps_manager/user_creator.py'; echo '*/2 * * * * /usr/bin/python3 /root/vps_manager/user_creator.py') | crontab -

echo "✅ جاب‌های کرون‌تب با موفقیت افزوده شدند."
echo "نصب کامل شد."
