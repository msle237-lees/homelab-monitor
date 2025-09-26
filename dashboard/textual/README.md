# homelab_monitor_tui

A Textual (terminal UI) frontend for your homelab-monitor data served by your FastAPI db_manager.

## Expected API (minimal)
- `GET /machines` → list of machines and current metrics. Example item:
```json
{
  "machine_id": 1,
  "machine_name": "proxmox-01",
  "cpu_cores": 16,
  "cpu_temp_c": 58.2,
  "ram_used_gb": 24.1,
  "ram_total_gb": 64.0,
  "storage_used_gb": 1200.5,
  "storage_total_gb": 4000.0,
  "network_mbps": 125.4
}
```
- `GET /machines/{id}/readings?limit=50` → latest time-series readings for the given machine.

## Install & Run
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate
pip install -r requirements.txt
export HOMELAB_API_URL="http://127.0.0.1:8000"  # point to your db_manager
export HOMELAB_REFRESH_SECONDS=5
python app.py
```

## Key bindings
- `q` quit
- `r` refresh now
- `/` focus filter
- `Enter` open selected machine details

## Notes
- The TUI auto-refreshes every `HOMELAB_REFRESH_SECONDS` seconds.
- If your API shape differs, adjust `refresh_data` and `load_logs_for_machine` accordingly.
