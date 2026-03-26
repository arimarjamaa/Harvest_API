#!/usr/bin/env python3
"""
Harvest Clock App - Track time and submit entries to Harvest API
"""

import os
import sys
import time
import datetime
import requests
import threading

# ── Config ────────────────────────────────────────────────────────────────────
HARVEST_ACCOUNT_ID = os.environ.get("HARVEST_ACCOUNT_ID", "")
HARVEST_TOKEN      = os.environ.get("HARVEST_TOKEN", "")
HARVEST_HEADERS    = {
    "Harvest-Account-Id": HARVEST_ACCOUNT_ID,
    "Authorization": f"Bearer {HARVEST_TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "HarvestClockApp",
}

# ── ANSI helpers ───────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
CLEAR  = "\033[2J\033[H"

def fmt(text, *codes):
    return "".join(codes) + text + RESET

# ── Clock display ──────────────────────────────────────────────────────────────
BIG_DIGITS = {
    "0": ["███", "█ █", "█ █", "█ █", "███"],
    "1": [" █ ", " █ ", " █ ", " █ ", " █ "],
    "2": ["███", "  █", "███", "█  ", "███"],
    "3": ["███", "  █", "███", "  █", "███"],
    "4": ["█ █", "█ █", "███", "  █", "  █"],
    "5": ["███", "█  ", "███", "  █", "███"],
    "6": ["███", "█  ", "███", "█ █", "███"],
    "7": ["███", "  █", "  █", "  █", "  █"],
    "8": ["███", "█ █", "███", "█ █", "███"],
    "9": ["███", "█ █", "███", "  █", "███"],
    ":": [" ", "█", " ", "█", " "],
}

def render_big_clock(time_str):
    rows = [""] * 5
    for ch in time_str:
        digit = BIG_DIGITS.get(ch, [" " * 3] * 5)
        for i in range(5):
            rows[i] += digit[i] + "  "
    return "\n".join("  " + r for r in rows)

# ── Timer state ────────────────────────────────────────────────────────────────
class Timer:
    def __init__(self):
        self.running   = False
        self.start_ts  = None
        self.elapsed   = 0.0
        self.note      = ""
        self.project_id = None
        self.task_id    = None

    def start(self):
        if not self.running:
            self.start_ts = time.time()
            self.running  = True

    def stop(self):
        if self.running:
            self.elapsed += time.time() - self.start_ts
            self.running  = False

    def reset(self):
        self.stop()
        self.elapsed  = 0.0
        self.note     = ""

    def current(self):
        total = self.elapsed
        if self.running:
            total += time.time() - self.start_ts
        return total

    def formatted(self):
        total = int(self.current())
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def hours_decimal(self):
        return self.current() / 3600

# ── Harvest API calls ──────────────────────────────────────────────────────────
def fetch_projects():
    if not HARVEST_ACCOUNT_ID or not HARVEST_TOKEN:
        return []
    try:
        r = requests.get("https://api.harvestapp.com/v2/projects",
                         headers=HARVEST_HEADERS, timeout=5)
        r.raise_for_status()
        return r.json().get("projects", [])
    except Exception:
        return []

def fetch_tasks_for_project(project_id):
    if not HARVEST_ACCOUNT_ID or not HARVEST_TOKEN:
        return []
    try:
        r = requests.get(
            f"https://api.harvestapp.com/v2/projects/{project_id}/task_assignments",
            headers=HARVEST_HEADERS, timeout=5)
        r.raise_for_status()
        return [ta["task"] for ta in r.json().get("task_assignments", [])]
    except Exception:
        return []

def submit_time_entry(timer):
    if not HARVEST_ACCOUNT_ID or not HARVEST_TOKEN:
        return False, "No Harvest credentials set (HARVEST_ACCOUNT_ID / HARVEST_TOKEN)"
    if not timer.project_id or not timer.task_id:
        return False, "Project and task must be selected before submitting"
    payload = {
        "project_id": timer.project_id,
        "task_id":    timer.task_id,
        "spent_date": datetime.date.today().isoformat(),
        "hours":      round(timer.hours_decimal(), 4),
        "notes":      timer.note,
    }
    try:
        r = requests.post("https://api.harvestapp.com/v2/time_entries",
                          headers=HARVEST_HEADERS, json=payload, timeout=8)
        r.raise_for_status()
        return True, f"Submitted {timer.formatted()} to Harvest (entry id {r.json().get('id')})"
    except requests.HTTPError as e:
        return False, f"HTTP error: {e.response.status_code} {e.response.text[:120]}"
    except Exception as e:
        return False, str(e)

# ── UI ─────────────────────────────────────────────────────────────────────────
def print_ui(timer, status_msg, projects, tasks):
    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%A, %B %d %Y")

    print(CLEAR, end="")
    print()
    print(fmt(render_big_clock(time_str), CYAN, BOLD))
    print()
    print(fmt(f"  {date_str}", CYAN))
    print()

    # Timer section
    timer_color = GREEN if timer.running else YELLOW
    state_label = "● RUNNING" if timer.running else "■ STOPPED"
    print(fmt(f"  ┌─ Timer ─────────────────────────────────────┐", BOLD))
    print(fmt(f"  │  {timer.formatted()}   ", BOLD, timer_color) +
          fmt(state_label, timer_color) +
          fmt("                    │", BOLD))

    note_display = timer.note[:38] if timer.note else "(no note)"
    print(fmt(f"  │  Note: {note_display:<38}│", BOLD))

    # Project / task
    proj_name = next((p["name"] for p in projects if p["id"] == timer.project_id), "—")
    task_name = next((t["name"] for t in tasks   if t["id"] == timer.task_id),    "—")
    print(fmt(f"  │  Project: {proj_name[:35]:<35}│", BOLD))
    print(fmt(f"  │  Task:    {task_name[:35]:<35}│", BOLD))
    print(fmt(f"  └─────────────────────────────────────────────┘", BOLD))
    print()

    # Status message
    if status_msg:
        color = GREEN if not status_msg.startswith("Error") else RED
        print(fmt(f"  {status_msg}", color))
        print()

    # Controls
    controls = [
        ("[s]", "start/stop"),
        ("[r]", "reset"),
        ("[n]", "set note"),
        ("[p]", "set project"),
        ("[t]", "set task"),
        ("[u]", "submit to Harvest"),
        ("[q]", "quit"),
    ]
    ctrl_line = "   ".join(fmt(k, BOLD) + " " + v for k, v in controls)
    print("  " + ctrl_line)
    print()
    sys.stdout.flush()

def input_line(prompt):
    """Prompt on a new line and read input."""
    print(fmt(f"\n  {prompt}: ", BOLD), end="", flush=True)
    try:
        return input().strip()
    except (EOFError, KeyboardInterrupt):
        return ""

def pick_from_list(label, items, name_key="name"):
    """Display a numbered list and return chosen id or None."""
    if not items:
        print(fmt(f"\n  No {label}s available (check credentials).", RED))
        time.sleep(1.5)
        return None
    print()
    for i, item in enumerate(items[:20], 1):
        print(f"  {i:2}. {item[name_key]}")
    choice = input_line(f"Select {label} (1-{min(len(items),20)})")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(items):
            return items[idx]["id"]
    except ValueError:
        pass
    return None

# ── Main loop ──────────────────────────────────────────────────────────────────
def run():
    timer      = Timer()
    status_msg = ""
    projects   = []
    tasks      = []

    # Fetch projects in background
    def _load_projects():
        nonlocal projects
        projects = fetch_projects()
    threading.Thread(target=_load_projects, daemon=True).start()

    import tty, termios, select

    fd   = sys.stdin.fileno()
    old  = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        while True:
            print_ui(timer, status_msg, projects, tasks)
            status_msg = ""

            # Wait up to 1 s for a keypress
            rlist, _, _ = select.select([sys.stdin], [], [], 1.0)
            if not rlist:
                continue

            # Restore canonical mode to read the key
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            ch = sys.stdin.read(1)
            tty.setraw(fd)

            if ch in ("q", "Q"):
                break
            elif ch in ("s", "S"):
                if timer.running:
                    timer.stop()
                    status_msg = "Timer stopped."
                else:
                    timer.start()
                    status_msg = "Timer started."
            elif ch in ("r", "R"):
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                confirm = input_line("Reset timer? [y/N]")
                tty.setraw(fd)
                if confirm.lower() == "y":
                    timer.reset()
                    status_msg = "Timer reset."
            elif ch in ("n", "N"):
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                note = input_line("Note")
                tty.setraw(fd)
                timer.note = note
                status_msg = "Note updated."
            elif ch in ("p", "P"):
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                if not projects:
                    print(fmt("\n  Loading projects…", YELLOW), flush=True)
                    projects = fetch_projects()
                pid = pick_from_list("project", projects)
                tty.setraw(fd)
                if pid:
                    timer.project_id = pid
                    tasks = fetch_tasks_for_project(pid)
                    timer.task_id = None
                    status_msg = "Project set. Press [t] to pick a task."
            elif ch in ("t", "T"):
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                if not tasks:
                    print(fmt("\n  No tasks — pick a project first.", YELLOW), flush=True)
                    time.sleep(1.2)
                else:
                    tid = pick_from_list("task", tasks)
                    if tid:
                        timer.task_id = tid
                        status_msg = "Task set."
                tty.setraw(fd)
            elif ch in ("u", "U"):
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                if timer.hours_decimal() < 0.001:
                    status_msg = "Error: Timer has no elapsed time to submit."
                else:
                    was_running = timer.running
                    timer.stop()
                    ok, msg = submit_time_entry(timer)
                    status_msg = msg if ok else f"Error: {msg}"
                    if ok:
                        timer.reset()
                    elif was_running:
                        timer.start()
                tty.setraw(fd)

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print(CLEAR, end="")
        print("Goodbye!")

if __name__ == "__main__":
    run()
