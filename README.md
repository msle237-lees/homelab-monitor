# homelab-monitor
A monitor system designed to keep track of my homelab setup.

Consists of two parts:

- dashboard:
  - A application serving a textual dashboard available over ssh with FastAPI + SQLite backend.
  - Contained within a docker container
- server-monitor:
  - A low usage python script meant to run as a subprocess on homelab machines.
  - Uses the requests library to post sensor and usage information back to Part 1.
