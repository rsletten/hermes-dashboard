# Hermes AI Dashboard

A fullscreen AI statistics dashboard for Raspberry Pi 5 with a 4.3" DSI display (800×480).

Built with **Pygame** — shows live Hermes Agent usage stats alongside system metrics, refreshed every 30 seconds.

## Screenshot

![Dashboard](screenshot-v3.png)

## Features

- **SYSTEM** — CPU temp & load, RAM usage, disk usage, uptime
- **AI USAGE (7 days)** — Sessions, tool calls, input/output tokens, active time, top tool bar chart
- **Gateway & Process Health** — Running status, process count, error counter (24h)
- **Scheduled Jobs** — Cron job names, schedules, last-run timestamps
- **Auto-refresh** every 30 seconds
- **Autostart** with desktop via LabWC (Raspberry Pi OS)

## Requirements

- Python 3.11+
- [pygame](https://www.pygame.org/)
- [psutil](https://github.com/giampaolo/psutil)
- [Hermes Agent](https://hermes-agent.nousresearch.com) (for AI statistics)
- Raspberry Pi OS with Wayland/LabWC (or any X11 display)

## Install

```bash
pip install pygame psutil
```

## Run

```bash
DISPLAY=:0 python3 dashboard.py
```

Press **Q** or **ESC** to quit.

## Autostart on Pi

Add to `~/.config/labwc/autostart`:

```bash
(sleep 5 && python3 /home/rsletten/hermes-dashboard/dashboard.py) &
```

## License

MIT
