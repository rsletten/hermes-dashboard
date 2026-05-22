#!/usr/bin/env python3
"""
Hermes AI Dashboard — Raspberry Pi 5 4.3" DSI display (800x480)
Shows system stats + Hermes Agent AI usage statistics.

Run: python3 dashboard.py
Press Q or ESC to quit.
"""

import os, sys, json, subprocess, time, glob, math
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta

import pygame
import psutil

# ── Constants ──────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 800, 480
REFRESH_INTERVAL = 30  # seconds between data updates
ANIMATION_FPS = 60

BG_COLOR = (10, 10, 18)          # near-black
PANEL_BG = (18, 18, 30)          # slightly lighter panel bg
ACCENT = (0, 180, 255)           # cyan accent
ACCENT_DIM = (40, 100, 140)
GREEN = (0, 220, 120)
YELLOW = (240, 200, 40)
RED = (230, 60, 60)
WHITE = (220, 220, 230)
GRAY = (120, 120, 130)
DARK_GRAY = (60, 60, 70)

FONT_SMALL = None
FONT_MEDIUM = None
FONT_LARGE = None
FONT_TINY = None

HERMES_HOME = Path.home() / ".hermes"
SESSIONS_DIR = HERMES_HOME / "sessions"
HERMES_LOGS = HERMES_HOME / "logs"

# ── Data Store ─────────────────────────────────────────────────────────────

class DashboardData:
    """Holds all dashboard data, refreshed every interval."""
    def __init__(self):
        self.last_refresh = 0
        self.uptime = ""
        self.cpu_temp = 0.0
        self.cpu_pct = 0.0
        self.ram_pct = 0.0
        self.ram_used_gb = 0.0
        self.ram_total_gb = 0.0
        self.disk_pct = 0.0
        self.disk_used_gb = 0.0
        self.disk_total_gb = 0.0

        # Hermes stats
        self.model_name = "—"
        self.provider = "—"
        self.sessions_7d = 0
        self.total_tokens_7d = 0
        self.input_tokens_7d = 0
        self.output_tokens_7d = 0
        self.tool_calls_7d = 0
        self.active_time_str = ""
        self.platform_breakdown = []  # [(platform, sessions, tokens), ...]
        self.top_tools = []           # [(tool, calls), ...]

        # Cron / job status
        self.cron_jobs = []           # [(name, status, last_run), ...]

        # Status indicators
        self.hermes_processes = 0
        self.gateway_running = False
        self.errors_24h = 0

    def refresh(self):
        """Fetch all fresh data."""
        self._refresh_system()
        self._refresh_hermes()
        self._refresh_cron()
        self.last_refresh = time.time()

    def _refresh_system(self):
        # Uptime
        with open("/proc/uptime") as f:
            up_secs = float(f.read().split()[0])
        days = int(up_secs // 86400)
        hours = int((up_secs % 86400) // 3600)
        mins = int((up_secs % 3600) // 60)
        self.uptime = f"{days}d {hours}h {mins}m"

        # CPU temp
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                self.cpu_temp = int(f.read().strip()) / 1000.0
        except: pass
        self.cpu_pct = psutil.cpu_percent(interval=0.2)

        # RAM
        mem = psutil.virtual_memory()
        self.ram_pct = mem.percent
        self.ram_used_gb = mem.used / (1024**3)
        self.ram_total_gb = mem.total / (1024**3)

        # Disk
        disk = psutil.disk_usage("/")
        self.disk_pct = disk.percent
        self.disk_used_gb = disk.used / (1024**3)
        self.disk_total_gb = disk.total / (1024**3)

    def _parse_insights(self, text):
        """Parse the box-drawing output of `hermes insights`."""
        for line in text.split("\n"):
            stripped = line.strip()
            # Sessions count
            if stripped.startswith("Sessions:"):
                parts = stripped.split()
                if len(parts) >= 2:
                    try: self.sessions_7d = int(parts[1])
                    except: pass
            # Tool calls
            if stripped.startswith("Tool calls:"):
                parts = stripped.split()
                if len(parts) >= 3:
                    try: self.tool_calls_7d = int(parts[2])
                    except: pass
            # Tokens
            if "Input tokens:" in stripped and "Output" not in stripped:
                parts = stripped.split()
                if len(parts) >= 3:
                    try: self.input_tokens_7d = int(parts[2].replace(",", ""))
                    except: pass
            if "Output tokens:" in stripped:
                parts = stripped.split()
                if len(parts) >= 3:
                    try: self.output_tokens_7d = int(parts[2].replace(",", ""))
                    except: pass
            if "Total tokens:" in stripped:
                parts = stripped.split()
                if len(parts) >= 3:
                    try: self.total_tokens_7d = int(parts[2].replace(",", ""))
                    except: pass
            # Active time
            if "Active time:" in stripped:
                parts = stripped.split()
                if len(parts) >= 3:
                    self.active_time_str = parts[2]
            # Model line
            if stripped.startswith("deepseek") or stripped.startswith("claude") or stripped.startswith("gpt"):
                parts = stripped.split()
                if len(parts) >= 2:
                    self.model_name = parts[0]
            # Top tools section
            if stripped.startswith("tool") and "%" in stripped:
                parts = stripped.split()
                if len(parts) >= 3:
                    try:
                        tool_name = parts[0]
                        calls = int(parts[1])
                        self.top_tools.append((tool_name, calls))
                    except: pass

    def _refresh_hermes(self):
        # Reset per-refresh data
        self.top_tools = []
        self.platform_breakdown = []
        self.cron_jobs = []

        # Get status
        try:
            out = subprocess.run(
                ["hermes", "status"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "HERMES_NO_COLOR": "1"}
            )
            for line in out.stdout.split("\n"):
                s = line.strip()
                if s.startswith("Model:"):
                    self.model_name = s.split(":")[-1].strip()
                if s.startswith("Provider:"):
                    self.provider = s.split(":")[-1].strip()
        except: pass

        # Get insights (7 days)
        try:
            out = subprocess.run(
                ["hermes", "insights", "--days", "7"],
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "HERMES_NO_COLOR": "1"}
            )
            self._parse_insights(out.stdout)
        except: pass

        # Count hermes processes
        try:
            out = subprocess.run(["pgrep", "-af", "hermes"], capture_output=True, text=True, timeout=5)
            self.hermes_processes = len([l for l in out.stdout.split("\n") if l.strip()])
        except: pass

        # Check if gateway is running
        try:
            out = subprocess.run(
                ["hermes", "gateway", "status"],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "HERMES_NO_COLOR": "1"}
            )
            self.gateway_running = "running" in out.stdout.lower()
        except: pass

        # Count error *events* in last 24h (count lines starting with a timestamp only)
        try:
            log_path = HERMES_LOGS / "errors.log"
            if log_path.exists():
                threshold = time.time() - 86400
                with open(log_path) as f:
                    for line in f:
                        if len(line) < 19:
                            continue
                        # Only count lines that start with a timestamp (YYYY-MM-DD HH:MM:SS)
                        if line[4] == '-' and line[7] == '-' and line[10] == ' ' and line[13] == ':':
                            try:
                                line_time = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").timestamp()
                                if line_time > threshold:
                                    self.errors_24h += 1
                            except: pass
        except: pass

    def _refresh_cron(self):
        try:
            out = subprocess.run(
                ["hermes", "cron", "list"],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "HERMES_NO_COLOR": "1"}
            )
            # Multi-line block parser: each job starts with a hex ID line like
            # "  61cc16d5bdcd [active]"
            # followed by indented fields (Name, Schedule, Last run, etc.)
            lines = out.stdout.split("\n")
            i = 0
            while i < len(lines):
                raw = lines[i]
                stripped = raw.strip()
                # Detect job header: hex ID followed by [active] or [paused]
                if stripped and (stripped.endswith("[active]") or stripped.endswith("[paused]") or stripped.endswith("[scheduled]")):
                    is_active = "[active]" in stripped or "[scheduled]" in stripped
                    job_id = stripped.split("[")[0].strip()
                    name = job_id  # fallback
                    schedule = ""
                    status = "✓" if is_active else "⏸"
                    last_run = ""
                    last_ok = True
                    # Walk following indented lines
                    i += 1
                    while i < len(lines):
                        next_line = lines[i].rstrip()
                        if not next_line.strip():
                            i += 1
                            continue
                        # Check if this is the start of a new job (non-indented hex ID)
                        if not next_line.startswith("    ") and next_line.strip() and not next_line.startswith("─") and not next_line.startswith("┌") and not next_line.startswith("│"):
                            break
                        nxt = next_line.strip()
                        if nxt.startswith("Name:"):
                            name = nxt.split(":", 1)[-1].strip()
                        elif nxt.startswith("Schedule:"):
                            schedule = nxt.split(":", 1)[-1].strip()
                        elif nxt.startswith("Last run:"):
                            parts = nxt.split(":", 1)[-1].strip()
                            last_run = parts[:16] if len(parts) > 16 else parts
                            last_ok = "ok" in parts or "success" in parts.lower()
                        i += 1
                    # Truncate long names
                    if len(name) > 35:
                        name = name[:32] + "..."
                    self.cron_jobs.append((name, status, schedule, last_run, last_ok))
                else:
                    i += 1
        except: pass


# ── Rendering ──────────────────────────────────────────────────────────────

def draw_progress_bar(surf, x, y, w, h, pct, color):
    """Draw a rounded progress bar."""
    if pct < 0: pct = 0
    if pct > 100: pct = 100
    # Background
    pygame.draw.rect(surf, DARK_GRAY, (x, y, w, h), border_radius=3)
    if pct > 0:
        fill_w = int(w * pct / 100)
        if fill_w > 0:
            pygame.draw.rect(surf, color, (x, y, fill_w, h), border_radius=3)

def draw_bar_chart(surf, x, y, width, height, items, bar_color):
    """Draw a simple horizontal bar chart. Items: [(label, value), ...]"""
    if not items:
        return y
    max_val = max(v for _, v in items)
    if max_val == 0: max_val = 1
    bar_h = max(14, min(20, height // len(items)))
    gap = 3
    cy = y
    for label, val in items:
        bar_w = int((val / max_val) * (width - 80))
        # Label
        lbl = FONT_TINY.render(label, True, WHITE)
        surf.blit(lbl, (x, cy))
        # Bar
        pygame.draw.rect(surf, bar_color, (x + 80, cy, max(bar_w, 2), bar_h - 2), border_radius=2)
        # Value
        val_text = FONT_TINY.render(str(val), True, ACCENT)
        surf.blit(val_text, (x + 80 + max(bar_w, 2) + 4, cy))
        cy += bar_h + gap
    return cy

def format_tokens(n):
    """Format token counts human-readable."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)

def render_dashboard(surf, data):
    """Main render function. Called every frame."""
    now = time.time()
    age = now - data.last_refresh

    # ── Header bar ──────────────────────────────────────────────────
    # Title
    title = FONT_LARGE.render("HERMES AI DASHBOARD", True, ACCENT)
    surf.blit(title, (20, 12))

    # Model badge on right
    model_text = FONT_TINY.render(f"Model: {data.model_name}", True, WHITE)
    surf.blit(model_text, (WIDTH - model_text.get_width() - 15, 10))

    provider_text = FONT_TINY.render(f"Provider: {data.provider}", True, GRAY)
    surf.blit(provider_text, (WIDTH - provider_text.get_width() - 15, 26))

    # Refresh indicator
    refresh_color = GREEN if age < REFRESH_INTERVAL * 2 else YELLOW
    refresh_text = FONT_TINY.render(f"↻ {max(0, REFRESH_INTERVAL - int(age))}s", True, refresh_color)
    surf.blit(refresh_text, (WIDTH - 80, 42))

    # Divider
    pygame.draw.line(surf, ACCENT_DIM, (10, 55), (WIDTH - 10, 55), 2)

    # ── LEFT COLUMN: System Stats ──────────────────────────────────
    lx, ly = 15, 68

    # System panel
    panel_height = 160
    pygame.draw.rect(surf, PANEL_BG, (lx, ly, 255, panel_height), border_radius=6)
    pygame.draw.rect(surf, ACCENT_DIM, (lx, ly, 255, panel_height), 1, border_radius=6)

    sys_title = FONT_MEDIUM.render("SYSTEM", True, ACCENT)
    surf.blit(sys_title, (lx + 10, ly + 6))

    # CPU temp
    temp_color = GREEN if data.cpu_temp < 60 else (YELLOW if data.cpu_temp < 75 else RED)
    temp_str = f"CPU: {data.cpu_temp:.1f}°C  {data.cpu_pct:.0f}%"
    temp_text = FONT_SMALL.render(temp_str, True, WHITE)
    surf.blit(temp_text, (lx + 10, ly + 32))
    draw_progress_bar(surf, lx + 10, ly + 50, 235, 12, data.cpu_pct, temp_color)

    # RAM
    ram_str = f"RAM: {data.ram_used_gb:.1f}/{data.ram_total_gb:.1f} GB ({data.ram_pct:.0f}%)"
    ram_color = GREEN if data.ram_pct < 70 else (YELLOW if data.ram_pct < 85 else RED)
    ram_text = FONT_SMALL.render(ram_str, True, WHITE)
    surf.blit(ram_text, (lx + 10, ly + 68))
    draw_progress_bar(surf, lx + 10, ly + 86, 235, 12, data.ram_pct, ram_color)

    # Disk
    disk_str = f"Disk: {data.disk_used_gb:.1f}/{data.disk_total_gb:.0f} GB ({data.disk_pct:.0f}%)"
    disk_color = GREEN if data.disk_pct < 70 else (YELLOW if data.disk_pct < 85 else RED)
    disk_text = FONT_SMALL.render(disk_str, True, WHITE)
    surf.blit(disk_text, (lx + 10, ly + 104))
    draw_progress_bar(surf, lx + 10, ly + 122, 235, 12, data.disk_pct, disk_color)

    # Uptime
    uptime_text = FONT_SMALL.render(f"Uptime: {data.uptime}", True, GRAY)
    surf.blit(uptime_text, (lx + 10, ly + 140))

    # ── RIGHT COLUMN: Hermes AI Stats ──────────────────────────────
    rx = 285
    ry = 68

    ai_panel_h = 240
    pygame.draw.rect(surf, PANEL_BG, (rx, ry, 500, ai_panel_h), border_radius=6)
    pygame.draw.rect(surf, ACCENT_DIM, (rx, ry, 500, ai_panel_h), 1, border_radius=6)

    ai_title = FONT_MEDIUM.render("AI USAGE (Last 7 Days)", True, ACCENT)
    surf.blit(ai_title, (rx + 10, ry + 6))

    # Row of big metric cards
    card_w = 110
    card_h = 56
    card_gap = 8
    card_y = ry + 32

    metrics = [
        ("Sessions", str(data.sessions_7d), ACCENT),
        ("Tool Calls", str(data.tool_calls_7d), GREEN),
        ("Input Tokens", format_tokens(data.input_tokens_7d), YELLOW),
        ("Output Tokens", format_tokens(data.output_tokens_7d), WHITE),
    ]

    for i, (label, value, color) in enumerate(metrics):
        cx = rx + 10 + i * (card_w + card_gap)
        pygame.draw.rect(surf, (25, 25, 42), (cx, card_y, card_w, card_h), border_radius=5)
        lbl = FONT_TINY.render(label, True, GRAY)
        surf.blit(lbl, (cx + 6, card_y + 4))
        val_surf = FONT_LARGE.render(value, True, color)
        surf.blit(val_surf, (cx + 6, card_y + 24))

    # Bottom row: total tokens + active time
    total_text = FONT_SMALL.render(f"Total Tokens: {format_tokens(data.total_tokens_7d)}", True, WHITE)
    surf.blit(total_text, (rx + 10, card_y + card_h + 8))

    active_text = FONT_SMALL.render(f"Active Time: {data.active_time_str}", True, WHITE)
    surf.blit(active_text, (rx + 250, card_y + card_h + 8))

    # Gateway / process / errors — right-align errors to panel edge
    status_y = card_y + card_h + 32
    gate_color = GREEN if data.gateway_running else RED
    gate_text = FONT_SMALL.render(f"Gateway: {'●' if data.gateway_running else '○'}", True, gate_color)
    surf.blit(gate_text, (rx + 12, status_y))

    proc_text = FONT_SMALL.render(f"Processes: {data.hermes_processes}", True, WHITE)
    surf.blit(proc_text, (rx + 180, status_y))

    err_color = GREEN if data.errors_24h <= 1 else (YELLOW if data.errors_24h < 5 else RED)
    err_text = FONT_SMALL.render(f"Errors: {data.errors_24h}", True, err_color)
    surf.blit(err_text, (rx + 500 - err_text.get_width() - 12, status_y))

    # ── Top Tools Bar Chart ────────────────────────────────────────
    if data.top_tools:
        tools_y = status_y + 28
        tools_label = FONT_TINY.render("Top Tools:", True, GRAY)
        surf.blit(tools_label, (rx + 10, tools_y))
        draw_bar_chart(surf, rx + 80, tools_y - 2, 400, 70, data.top_tools[:5], ACCENT)

    # ── BOTTOM PANEL: Cron Jobs ────────────────────────────────────
    bx, by = 15, 245

    cron_panel_h = 220
    pygame.draw.rect(surf, PANEL_BG, (bx, by, 770, cron_panel_h), border_radius=6)
    pygame.draw.rect(surf, ACCENT_DIM, (bx, by, 770, cron_panel_h), 1, border_radius=6)

    cron_title = FONT_MEDIUM.render("SCHEDULED JOBS", True, ACCENT)
    surf.blit(cron_title, (bx + 10, by + 6))

    if data.cron_jobs:
        job_y = by + 32
        for name, status, schedule, last_run, last_ok in data.cron_jobs[:6]:
            status_color = GREEN if "✓" in status else GRAY
            status_dot = FONT_SMALL.render(status, True, status_color)
            surf.blit(status_dot, (bx + 15, job_y))
            name_text = FONT_SMALL.render(name, True, WHITE)
            surf.blit(name_text, (bx + 35, job_y))
            # Schedule on the right
            if schedule:
                sched_color = GRAY
                sched_text = FONT_TINY.render(schedule[:12], True, sched_color)
                sx = bx + 770 - sched_text.get_width() - 10
                surf.blit(sched_text, (sx, job_y))
            # Last run status
            if last_run:
                lr_color = GREEN if last_ok else RED
                lr_text = FONT_TINY.render(f"↻ {last_run}", True, lr_color)
                surf.blit(lr_text, (bx + 400, job_y))
            job_y += 20
    else:
        na = FONT_SMALL.render("No scheduled jobs detected", True, GRAY)
        surf.blit(na, (bx + 20, by + 32))

    # ── Last refresh timestamp ─────────────────────────────────────
    if data.last_refresh > 0:
        ts = datetime.fromtimestamp(data.last_refresh).strftime("%H:%M:%S")
        ts_text = FONT_TINY.render(f"Last updated: {ts}", True, DARK_GRAY)
        surf.blit(ts_text, (WIDTH - ts_text.get_width() - 15, HEIGHT - 18))

    # Version footer
    ver_text = FONT_TINY.render("Hermes Dashboard v1.0", True, DARK_GRAY)
    surf.blit(ver_text, (15, HEIGHT - 18))


# ── Main Loop ──────────────────────────────────────────────────────────────

def main():
    global FONT_SMALL, FONT_MEDIUM, FONT_LARGE, FONT_TINY

    pygame.init()
    pygame.mouse.set_visible(False)

    # Fullscreen on the DSI display (800x480)
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN | pygame.DOUBLEBUF)
    pygame.display.set_caption("Hermes AI Dashboard")
    clock = pygame.time.Clock()

    # Fonts — try to load a nice monospace, fall back to default
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        None,  # pygame default
    ]

    FONT_TINY = None
    FONT_SMALL = None
    FONT_MEDIUM = None
    FONT_LARGE = None

    for fp in font_paths:
        try:
            if fp:
                FONT_TINY = pygame.font.Font(fp, 12)
                FONT_SMALL = pygame.font.Font(fp, 16)
                FONT_MEDIUM = pygame.font.Font(fp, 18)
                FONT_LARGE = pygame.font.Font(fp, 28)
            else:
                FONT_TINY = pygame.font.Font(None, 14)
                FONT_SMALL = pygame.font.Font(None, 18)
                FONT_MEDIUM = pygame.font.Font(None, 22)
                FONT_LARGE = pygame.font.Font(None, 32)
            break
        except:
            continue

    if FONT_TINY is None:
        FONT_TINY = pygame.font.Font(None, 14)
        FONT_SMALL = pygame.font.Font(None, 18)
        FONT_MEDIUM = pygame.font.Font(None, 22)
        FONT_LARGE = pygame.font.Font(None, 32)

    data = DashboardData()

    # Create a surface for double buffering
    canvas = pygame.Surface((WIDTH, HEIGHT))

    running = True
    refresh_needed = True

    while running:
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False

        # Refresh data at interval
        if refresh_needed or (time.time() - data.last_refresh >= REFRESH_INTERVAL):
            data.refresh()
            refresh_needed = False

        # Render
        canvas.fill(BG_COLOR)
        render_dashboard(canvas, data)
        screen.blit(canvas, (0, 0))
        pygame.display.flip()

        clock.tick(ANIMATION_FPS)

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
