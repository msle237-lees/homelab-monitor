python3 -m venv /opt/homelab-agent/venv
/opt/homelab-agent/venv/bin/pip install --upgrade pip
/opt/homelab-agent/venv/bin/pip install psutil requests python-dotenv
sudo mkdir -p /etc/homelab-agent
sudo mkdir -p /var/log
sudo cp homelab_agent.py /opt/homelab-agent/
sudo chown -R $USER:$USER /opt/homelab-agent
