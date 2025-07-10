#!/bin/bash

# --- Section 1: Get and Validate API Endpoint ---

# Get API URL from user
read -p "Please enter the full API Endpoint URL (e.g., http://yourdomain.com/api/v1/server/): " server_address

# Check if input is empty
if [ -z "$server_address" ]; then
    echo "Error: API address was not provided. Script aborted."
    exit 1
fi

echo "Validating API address..."

# Send a request and store the response
# -s for silent mode, -m 10 for a 10-second timeout
response=$(curl -s -m 10 "$server_address")

# Define the expected response for a valid (but unauthorized) endpoint
expected_response='{"status":"error","message":"Unauthorized"}'

# Compare the received response with the expected one
if [[ "$response" == "$expected_response" ]]; then
    echo "✅ API address is valid. Continuing with installation..."
else
    echo "❌ Error: The API address is invalid or not responding correctly."
    echo "--------------------------------------------------------"
    echo "Expected response: $expected_response"
    echo "Received response: $response"
    echo "--------------------------------------------------------"
    echo "Please check the address and run the script again. Installation aborted."
    exit 1
fi

# --- End of Validation Section ---


# Now that the address is valid, ask for the token
read -p "Please enter the API token: " api_token


echo "Starting server manager installation..."
# Install prerequisites
apt-get update
apt-get install -y python3 python3-pip unzip nginx gunicorn

# Stop any running gunicorn instance
pkill gunicorn

# Clean up old files and directories from previous installations
# Added vps_manager-2 to the list for cleaner removal
rm -rf servermanager/ vps_manager/ vps_manager-2/ v11.zip nohup.out v10.zip v12.zip

# *** FIX: Clone the repo and rename the destination folder to 'vps_manager' ***
git clone https://github.com/abbasnazari-0/vps_manager-2.git vps_manager

# Now the 'vps_manager' directory exists, and the following commands will work
echo "Creating config file..."
echo -e "server_address = '$server_address'\napi_token='$api_token'" | tee vps_manager/config.py

# Configure Nginx
mv vps_manager/servermanager /etc/nginx/sites-enabled/servermanager
# Check if the default symlink exists before unlinking
if [ -L /etc/nginx/sites-enabled/default ]; then
    unlink /etc/nginx/sites-enabled/default
fi
nginx -s reload

# Install Python dependencies
pip3 install flask jdatetime jsonpickle psutil mysql-connector-python

# Stop and remove the old service file to ensure a clean setup
if [ -f /etc/systemd/system/manager_vps.service ]; then
    sudo systemctl stop manager_vps.service
    rm /etc/systemd/system/manager_vps.service
fi

# Create the systemd service file
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

# Reload, enable, and restart the service
sudo systemctl daemon-reload
sudo systemctl enable manager_vps.service
sudo systemctl restart manager_vps.service

echo ""
echo ""
echo "=========================================="
echo "✅ Manager installed successfully."
echo "=========================================="
echo ""

# Add jobs to crontab
echo "Adding jobs to crontab..."
(crontab -l 2>/dev/null | grep -v '/usr/bin/python3 /root/vps_manager/usage_reporter.py'; echo '*/10 * * * * /usr/bin/python3 /root/vps_manager/usage_reporter.py') | crontab -
(crontab -l 2>/dev/null | grep -v '/usr/bin/python3 /root/vps_manager/user_creator.py'; echo '*/2 * * * * /usr/bin/python3 /root/vps_manager/user_creator.py') | crontab -

echo "✅ Crontab jobs added successfully."
echo "Installation complete."
