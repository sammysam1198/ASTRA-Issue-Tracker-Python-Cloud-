import os
import csv
import requests
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, filedialog
from datetime import datetime
from XLEngine import XLSetupSession
from XLConsole import XLScriptConsoleWindow



# Pillow is optional – used for the logo
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    ImageTk = None
    PIL_AVAILABLE = False



APP_VERSION = "6.1.0"

# Dark Mode
DARK_BG_1 = "#0d1117"  # main background
DARK_BG_2 = "#151b23"  # panels / frames
DARK_BG_3 = "#1e242a"  # inputs / boxes

TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#c9d1d9"  # optional, GitHub-style soft white


# ----------------------------
# THEME
# ----------------------------

DEBUG_HTTP = True
def _dbg(msg: str):
    if DEBUG_HTTP:
        print(msg, flush=True)



#Constants/colors

JH_PURPLE = "#3C1361"
JH_WHITE_TEXT = "white"
JH_PANEL_BG = "#360060"
JH_PANEL_BORDER = "#48176d"


# ----------------------------
# API CONFIG
# ----------------------------

API_BASE = "https://api-server-jh.onrender.com"

stores_cache = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_WHITE_PATH = os.path.join(BASE_DIR, "jh_logo_white.png")
GRADIENT_PATH = os.path.join(BASE_DIR, "Gradient.png")


# --- Admin / auth config ---

# Remember last-logged-in username for quick login autofill
LAST_USER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jh_last_user.txt")

def _dbg_response(resp, label="HTTP"):
    _dbg(f"\n--- {label} ---")
    _dbg(f"URL: {resp.request.method} {resp.request.url}")
    _dbg(f"Status: {resp.status_code}")
    try:
        _dbg(f"JSON: {resp.json()}")
    except Exception:
        text = (resp.text or "").strip()
        _dbg(f"TEXT: {text[:2000]}")  # cap so it doesn't explode your terminal
    _dbg("------------\n")

def api_admin_verify(email: str, password: str, pin: str):
    """
    POST /admin/verify
    Body: { "email", "password", "pin" }
    Returns (ok: bool, message: str)
    """
    payload = {"email": email, "password": password, "pin": pin}
    try:
        resp = requests.post(f"{API_BASE}/admin/verify", json=payload, timeout=10)
    except requests.RequestException as e:
        return False, f"Error contacting server: {e}"

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200 and data.get("ok"):
        return True, data.get("message", "Admin verified.")
    else:
        msg = data.get("error") or resp.text
        return False, msg


def api_admin_list_users(admin_email: str, admin_password: str, admin_pin: str):
    """
    POST /admin/users
    Body: { "admin_email", "admin_password", "admin_pin" }
    Expects: { "users": [ { "email", "username", "role", ... }, ... ] }
    """
    payload = {
        "admin_email": admin_email,
        "admin_password": admin_password,
        "admin_pin": admin_pin,
    }
    try:
        resp = requests.post(f"{API_BASE}/admin/users", json=payload, timeout=30)
    except requests.RequestException as e:
        return False, [], f"Error contacting server: {e}"

    try:
        data = resp.json()
    except ValueError:
        return False, [], "Server returned invalid JSON for /admin/users."

    if resp.status_code != 200:
        msg = data.get("error") or resp.text
        return False, [], msg

    return True, data.get("users", []), None


def api_get_all_issues():
    """
    Call GET /issues/all on the API server.

    Returns (ok: bool, rows: list[dict], error: str | None)
    """
    try:
        resp = requests.get(f"{API_BASE}/issues/all", timeout=60)
    except requests.RequestException as e:
        return False, [], f"Error contacting server: {e}"

    if resp.status_code != 200:
        try:
            data = resp.json()
            msg = data.get("error") or resp.text
        except Exception:
            msg = resp.text
        return False, [], f"Server returned {resp.status_code}: {msg}"

    try:
        rows = resp.json()
    except ValueError:
        return False, [], "Server returned invalid JSON."
    if not isinstance(rows, list):
        return False, [], "Server returned unexpected data format."
    return True, rows, None


def api_admin_import_devices(api_base_url: str, rows: list[dict], dry_run: bool, timeout: int = 60):
    """
    Calls your Render API endpoint:
      POST /admin/import_devices
    Body:
      { "dry_run": true/false, "rows": [...] }

    Returns: (ok: bool, data: dict|None, err: str|None)
    """
    try:
        url = api_base_url.rstrip("/") + "/admin/import_devices"
        payload = {"dry_run": bool(dry_run), "rows": rows}
        r = requests.post(url, json=payload, timeout=timeout)
        try:
            data = r.json()
        except Exception:
            return False, None, f"Non-JSON response ({r.status_code}): {r.text[:300]}"

        if r.status_code != 200 or not data.get("ok", False):
            return False, data, data.get("error", f"HTTP {r.status_code}")

        return True, data, None
    except Exception as e:
        return False, None, str(e)


def api_get_devices_by_store(store_number: int):
    """
    Call GET /devices/by-store

    Returns (ok: bool, rows: list[dict], error: str|None)
    """
    try:
        resp = requests.get(
            f"{API_BASE}/devices/by-store",
            params={"store_number": str(store_number)},
            timeout=30,
        )
    except requests.RequestException as e:
        return False, [], f"Error contacting server: {e}"

    if resp.status_code != 200:
        try:
            data = resp.json()
            msg = data.get("error") or resp.text
        except Exception:
            msg = resp.text
        return False, [], f"Server error: {msg}"

    try:
        data = resp.json()
    except ValueError:
        return False, [], "Server returned invalid JSON for /devices/by-store"

    devices = data.get("devices", [])
    if not isinstance(devices, list):
        return False, [], "Devices response was not a list."

    return True, devices, None



def api_admin_change_password(
    admin_email: str,
    admin_password: str,
    admin_pin: str,
    target_email: str,
    new_password: str,
):
    """
    POST /admin/change-user-password
    Body: { admin_email, admin_password, admin_pin, target_email, new_password }
    """
    payload = {
        "admin_email": admin_email,
        "admin_password": admin_password,
        "admin_pin": admin_pin,
        "target_email": target_email,
        "new_password": new_password,
    }
    try:
        resp = requests.post(
            f"{API_BASE}/admin/change-user-password", json=payload, timeout=30
        )
    except requests.RequestException as e:
        return False, f"Error contacting server: {e}"

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200:
        return True, data.get("message", "User password changed.")
    else:
        msg = data.get("error") or resp.text
        return False, msg


def import_tech_info_csv(self):
    """
    GUI flow:
      1) pick CSV
      2) send rows as DRY RUN
      3) show summary
      4) ask confirm
      5) send rows as REAL import
    """
    # 1) pick file
    path = filedialog.askopenfilename(
        title="Select Tech Info CSV",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
    )
    if not path:
        return

    # 2) read CSV into rows
    try:
        rows = []
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
        if not rows:
            messagebox.showwarning("Import Tech Info (CSV)", "CSV file had no rows.")
            return
    except Exception as e:
        messagebox.showerror("Import Tech Info (CSV)", f"Failed to read CSV:\n{e}")
        return

    # You likely already have API base URL stored somewhere:
    api_base = getattr(self.controller, "api_base_url", None) or getattr(self.controller, "API_BASE_URL", None)
    if not api_base:
        messagebox.showerror("Import Tech Info (CSV)", "Missing API base URL in controller.")
        return

    # 3) DRY RUN
    ok, data, err = api_admin_import_devices(api_base, rows, dry_run=True, timeout=90)
    if not ok:
        msg = err or "Unknown error"
        messagebox.showerror("Tech Info Import (Dry Run)", msg)
        return

    summary = (data.get("summary") or {})
    inserts = summary.get("insert", 0)
    updates = summary.get("update", 0)
    skips   = summary.get("skip", 0)
    errors  = summary.get("error", 0)
    processed = data.get("processed", len(rows))

    report = (
        "Tech Info Import (Dry Run)\n"
        "--------------------------\n"
        f"Rows: {processed}\n"
        f"Inserts: {inserts}\n"
        f"Updates: {updates}\n"
        f"Skips: {skips}\n"
        f"Errors: {errors}\n"
    )

    # show a few error details
    if errors:
        report += "\nFirst errors (up to 10):\n"
        for item in (data.get("errors") or [])[:10]:
            report += f"- Row {item.get('row_index')}: {item.get('error')}\n"

    # Put it in whatever textbox you use for output (adjust to your app)
    try:
        self.controller.append_output(report)  # if you have a helper
    except Exception:
        # fallback: if you have a text widget reference, use that
        if hasattr(self, "text") and self.text:
            self.text.insert("end", report + "\n")
            self.text.see("end")

    # 4) confirm
    if not messagebox.askyesno(
        "Confirm Import",
        "Dry run complete.\n\nApply these changes to the database?"
    ):
        return

    # 5) REAL IMPORT
    ok2, data2, err2 = api_admin_import_devices(api_base, rows, dry_run=False, timeout=120)
    if not ok2:
        messagebox.showerror("Tech Info Import", err2 or "Unknown error")
        return

    processed2 = data2.get("processed", len(rows))
    summary2 = (data2.get("summary") or {})
    applied = summary2.get("applied", 0)
    errors2 = summary2.get("error", 0)

    messagebox.showinfo(
        "Tech Info Import",
        f"Import complete.\n\nRows: {processed2}\nApplied: {applied}\nErrors: {errors2}"
    )


def api_admin_change_pin(
    admin_email: str,
    admin_password: str,
    admin_pin: str,
    target_email: str,
    new_pin: str,
):
    """
    POST /admin/change-user-pin
    """
    payload = {
        "admin_email": admin_email,
        "admin_password": admin_password,
        "admin_pin": admin_pin,
        "target_email": target_email,
        "new_pin": new_pin,
    }
    try:
        resp = requests.post(
            f"{API_BASE}/admin/change-user-pin", json=payload, timeout=30
        )
    except requests.RequestException as e:
        return False, f"Error contacting server: {e}"

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200:
        return True, data.get("message", "User PIN changed.")
    else:
        msg = data.get("error") or resp.text
        return False, msg


def api_admin_delete_user(
    admin_email: str,
    admin_password: str,
    admin_pin: str,
    target_email: str,
):
    """
    POST /admin/delete-user
    """
    payload = {
        "admin_email": admin_email,
        "admin_password": admin_password,
        "admin_pin": admin_pin,
        "target_email": target_email,
    }
    try:
        resp = requests.post(
            f"{API_BASE}/admin/delete-user", json=payload, timeout=30
        )
    except requests.RequestException as e:
        return False, f"Error contacting server: {e}"

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200:
        return True, data.get("message", "User deleted.")
    else:
        msg = data.get("error") or resp.text
        return False, msg


def api_admin_restart_api(
    admin_email: str,
    admin_password: str,
    admin_pin: str,
):
    """
    POST /admin/restart-api
    """
    payload = {
        "admin_email": admin_email,
        "admin_password": admin_password,
        "admin_pin": admin_pin,
    }
    try:
        resp = requests.post(
            f"{API_BASE}/admin/restart-api", json=payload, timeout=30
        )
    except requests.RequestException as e:
        return False, f"Error contacting server: {e}"

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200:
        return True, data.get("message", "API restart requested.")
    else:
        msg = data.get("error") or resp.text
        return False, msg


def load_last_username() -> str | None:
    try:
        with open(LAST_USER_FILE, "r", encoding="utf-8") as f:
            username = f.read().strip()
            return username or None
    except FileNotFoundError:
        return None
    except OSError:
        return None


def save_last_username(username: str) -> None:
    username = (username or "").strip()
    if not username:
        return
    try:
        with open(LAST_USER_FILE, "w", encoding="utf-8") as f:
            f.write(username)
    except OSError:
        # If we can't write, just silently ignore
        pass

# ----------------------------
# API HELPER FUNCTIONS
# ----------------------------

def api_quick_login(username: str, password: str):
    """
    Try quick login with username + password.
    Returns:
      (success: bool, require_full: bool, message: str, email: str|None, is_admin: bool)
    """
    payload = {"username": username, "password": password}

    try:
        resp = requests.post(f"{API_BASE}/auth/quick-login", json=payload, timeout=10)
    except requests.RequestException as e:
        return False, False, f"Error contacting server: {e}", None, False

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200:
        return (
            True,
            False,
            data.get("message", "Quick login successful."),
            data.get("email"),
            bool(data.get("is_admin", False)),
        )

    require_full = bool(data.get("require_full", False))
    msg = data.get("error") or f"Login failed: {resp.status_code}"
    return False, require_full, msg, None, False


def api_full_login(email: str, username: str, password: str, pin: str):
    """
    Do full login with email + username + password + PIN.
    Returns (success: bool, message: str)
    """
    payload = {
        "email": email,
        "username": username,
        "password": password,
        "pin": pin,
    }

    try:
        resp = requests.post(f"{API_BASE}/auth/login", json=payload, timeout=10)
    except requests.RequestException as e:
        return False, f"Error contacting server: {e}"

    if resp.status_code == 200:
        return True, "Login successful."
    else:
        try:
            data = resp.json()
            msg = data.get("error") or resp.text
        except ValueError:
            msg = resp.text
        return False, f"Login failed: {msg}"


def api_change_password(email: str, username: str, current_password: str, new_password: str, pin: str):
    """
    Call POST /auth/change-password.
    Returns (success: bool, message: str)
    """
    payload = {
        "email": email,
        "username": username,
        "current_password": current_password,
        "new_password": new_password,
        "pin": pin,
    }

    try:
        resp = requests.post(f"{API_BASE}/auth/change-password", json=payload, timeout=15)
    except requests.RequestException as e:
        return False, f"Error contacting server: {e}"

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200:
        return True, data.get("message", "Password changed successfully.")
    else:
        msg = data.get("error") or resp.text
        return False, msg


def api_change_pin(email: str, username: str, password: str, current_pin: str, new_pin: str):
    """
    Call POST /auth/change-pin.
    Returns (success: bool, message: str)
    """
    payload = {
        "email": email,
        "username": username,
        "password": password,
        "current_pin": current_pin,
        "new_pin": new_pin,
    }

    try:
        resp = requests.post(f"{API_BASE}/auth/change-pin", json=payload, timeout=15)
    except requests.RequestException as e:
        return False, f"Error contacting server: {e}"

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code == 200:
        return True, data.get("message", "PIN changed successfully.")
    else:
        msg = data.get("error") or resp.text
        return False, msg


def api_load_stores():
    """
    Load store metadata from the API (from Stores.json on the server).
    Uses a simple in-memory cache.
    Returns (stores: dict | None, error: str | None)
    """
    global stores_cache
    if stores_cache is not None:
        return stores_cache, None

    try:
        resp = requests.get(f"{API_BASE}/stores", timeout=30)
        resp.raise_for_status()
        stores_cache = resp.json()
        return stores_cache, None
    except requests.RequestException as e:
        return None, f"Error loading store list from server: {e}"


def api_add_issue(store_name: str, issue: dict):
    """
    Call POST /issues with the given store_name and legacy-style issue dict.
    Returns (success: bool, message: str)
    """
    payload = {"store_name": store_name, "issue": issue}

    resp = None
    try:
        resp = requests.post(f"{API_BASE}/issues", json=payload, timeout=60)
        resp.raise_for_status()
        return True, "Issue added and synced to the server."

    except requests.HTTPError:
        # resp should exist if request reached the server, but make it safe.
        if resp is not None:
            try:
                data = resp.json()
                msg = data.get("error") or resp.text
            except Exception:
                msg = (resp.text or "").strip()
        else:
            msg = "HTTP error occurred, but no response was returned."
        return False, f"Server error: {msg}"

    except requests.RequestException as e:
        return False, f"Error sending issue to server: {e}"


def api_search_issues(store_number: int | None = None, name: str | None = None):
    """
    Call GET /issues/search on the API server.

    - If store_number is provided, search by that store.
    - If name is provided, search issue_name with a partial, case-insensitive match.

    Returns (ok: bool, rows: list[dict], error: str | None)
    """
    params: dict[str, str] = {}
    if store_number is not None:
        params["store_number"] = str(store_number)
    if name:
        params["name"] = name

    if not params:
        return False, [], "No search parameters provided."

    try:
        resp = requests.get(f"{API_BASE}/issues/search", params=params, timeout=30)
    except requests.RequestException as e:
        return False, [], f"Error contacting server: {e}"

    if resp.status_code != 200:
        try:
            data = resp.json()
            msg = data.get("error") or resp.text
        except ValueError:
            msg = resp.text
        return False, [], f"Search failed: {msg}"

    try:
        rows = resp.json()
    except ValueError:
        return False, [], "Server returned invalid JSON for /issues/search"

    if not isinstance(rows, list):
        return False, [], "Search response was not a list."

    return True, rows, None


def api_update_issue(issue_id: int, updated_issue: dict):
    """
    Call POST /issues/update to update an existing issue in the DB.

    Expected by the API:
    {
      "issue_id": 123,
      "updated_issue": { ...same keys as add_issue 'issue' payload... }
    }

    Returns (success: bool, message: str)
    """
    payload = {
        "issue_id": issue_id,
        "updated_issue": updated_issue,
    }

    try:
        resp = requests.post(f"{API_BASE}/issues/update", json=payload, timeout=30)
    except requests.RequestException as e:
        return False, f"Error contacting server: {e}"

    if resp.status_code == 200:
        return True, "Issue updated successfully."
    else:
        try:
            data = resp.json()
            msg = data.get("error") or resp.text
        except ValueError:
            msg = resp.text
        return False, f"Update failed: {msg}"

def api_get_stores():
    """
    Fetch store metadata from /stores.
    Returns (ok: bool, stores: dict, error: str | None)
    """
    global stores_cache

    if stores_cache is not None:
        return True, stores_cache, None

    try:
        resp = requests.get(f"{API_BASE}/stores", timeout=30)
    except requests.RequestException as e:
        return False, {}, f"Error contacting server: {e}"

    if resp.status_code != 200:
        try:
            data = resp.json()
            msg = data.get("error") or resp.text
        except ValueError:
            msg = resp.text
        return False, {}, f"Failed to load stores: {msg}"

    try:
        stores = resp.json()
    except ValueError:
        return False, {}, "Server returned invalid JSON for /stores"

    if not isinstance(stores, dict):
        return False, {}, "Stores response was not a JSON object."

    stores_cache = stores
    return True, stores, None


def api_get_issues_by_store(store_number: int | None = None, store_name: str | None = None,):
    """
    Call GET /issues/by-store on the API server.

    Exactly one of store_number or store_name should be provided.

    Returns (ok: bool, rows: list[dict], error: str | None)
    """
    params: dict[str, str] = {}
    if store_number is not None:
        params["store_number"] = str(store_number)
    if store_name:
        params["store_name"] = store_name

    if not params:
        return False, [], "store_number or store_name is required."

    try:
        resp = requests.get(f"{API_BASE}/issues/by-store", params=params, timeout=30)
    except requests.RequestException as e:
        return False, [], f"Error contacting server: {e}"

    if resp.status_code != 200:
        try:
            data = resp.json()
            msg = data.get("error") or resp.text
        except ValueError:
            msg = resp.text
        return False, [], f"Failed to load issues: {msg}"

    try:
        rows = resp.json()
    except ValueError:
        return False, [], "Server returned invalid JSON for /issues/by-store"

    if not isinstance(rows, list):
        return False, [], "Issues response was not a list."

    return True, rows, None

# ----------------------------
# BASE PURPLE FRAME
# ----------------------------

class GradientFrame(tk.Frame):
    """
    Base class for all screens with a gradient background.
    Widgets should be placed on self.inner_frame (scrollable content).
    """
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, bg="black", *args, **kwargs)

        # Background image label
        self._bg_original = None
        self._bg_photo = None

        if PIL_AVAILABLE:
            self._bg_original = Image.open(GRADIENT_PATH)
            self._bg_photo = ImageTk.PhotoImage(self._bg_original)
            self._bg_label = tk.Label(self, image=self._bg_photo, bd=0)
        else:
            self._bg_label = tk.Label(self, bg="black", bd=0)

        # LAYER 0: gradient background
        self._bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        # LAYER 2: panel (smaller box)
        self.panel = tk.Frame(
            self._bg_label,
            bg=JH_PANEL_BG,
            bd=0,
            highlightthickness=1,              # set 0 for no border
            highlightbackground=JH_PANEL_BORDER
        )
        self.panel.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.86, relheight=0.88)

        # padded content area inside the panel (your “20px around everything”)
        self.content = tk.Frame(self.panel, bg=JH_PANEL_BG, bd=0, highlightthickness=0)
        self.content.pack(fill="both", expand=True, padx=20, pady=20)

        # Resize handler
        self.bind("<Configure>", self._on_resize)

        # -------------------------
        # SCROLLABLE AREA SETUP
        # -------------------------
        scroll_container = tk.Frame(self.content, bg=JH_PANEL_BG, bd=0, highlightthickness=0)
        scroll_container.pack(fill="both", expand=True)

        container_bg = JH_PANEL_BG

        self.canvas = tk.Canvas(
            scroll_container,
            bg=container_bg,
            highlightthickness=0,
            bd=0
        )
        vscroll = tk.Scrollbar(scroll_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vscroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        self.inner_frame = tk.Frame(self.canvas, bg=container_bg, bd=0, highlightthickness=0)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")

        def _on_inner_config(_event=None):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.inner_frame.bind("<Configure>", _on_inner_config)

        def _on_canvas_config(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)

        self.canvas.bind("<Configure>", _on_canvas_config)

        def _on_mousewheel(event):
            if event.delta:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(_event=None):
            self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(_event=None):
            self.canvas.unbind_all("<MouseWheel>")

        self.canvas.bind("<Enter>", _bind_mousewheel)
        self.canvas.bind("<Leave>", _unbind_mousewheel)

    @staticmethod
    def label(parent, text, **kwargs):
        kw = {
            "text": text,
            "fg": JH_WHITE_TEXT,
            "bg": parent.cget("bg"),
            "bd": 0,
            "highlightthickness": 0
        }
        kw.update(kwargs)
        return tk.Label(parent, **kw)

    @staticmethod
    def subframe(parent, **kwargs):
        bg = parent.cget("bg")
        kw = {"bg": bg, "bd": 0, "highlightthickness": 0}
        kw.update(kwargs)
        return tk.Frame(parent, **kw)

    def _on_resize(self, event):
        if not PIL_AVAILABLE or self._bg_original is None:
            return

        # Tell the type checker: if we got here, PIL objects exist
        assert Image is not None and ImageTk is not None

        w, h = event.width, event.height
        if w < 2 or h < 2:
            return

        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = getattr(Image, "LANCZOS", 1)

        img = self._bg_original.resize((w, h), resample)
        self._bg_photo = ImageTk.PhotoImage(img)
        self._bg_label.configure(image=self._bg_photo)


# ----------------------------
# LOGIN FRAME
# ----------------------------

class LoginFrame(GradientFrame):
    """Gradient-themed login screen."""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        title = GradientFrame.label(
            self.inner_frame,
            "JH Reports – Login",
            font=("Segoe UI", 22, "bold")
        )
        title.pack(pady=25)

        form_frame = GradientFrame.subframe(self.inner_frame)
        form_frame.pack(pady=10)

        #  Use the form_frame background instead of hardcoding purple
        lbl = {"fg": JH_WHITE_TEXT, "bg": form_frame.cget("bg"), "font": ("Segoe UI", 11)}
        entry_width = 30

        tk.Label(form_frame, text="Username:", **lbl).grid(row=0, column=0, sticky="e", pady=5, padx=5)
        self.entry_username = tk.Entry(form_frame, width=entry_width)
        self.entry_username.grid(row=0, column=1, pady=5, padx=5)

        # Autofill last logged-in username, if available
        last_user = load_last_username()
        if last_user:
            self.entry_username.insert(0, last_user)

        tk.Label(form_frame, text="Password:", **lbl).grid(row=1, column=0, sticky="e", pady=5, padx=5)
        self.entry_password = tk.Entry(form_frame, show="*", width=entry_width)
        self.entry_password.grid(row=1, column=1, pady=5, padx=5)

        tk.Label(form_frame, text="Email (if needed):", **lbl).grid(row=2, column=0, sticky="e", pady=5, padx=5)
        self.entry_email = tk.Entry(form_frame, width=entry_width)
        self.entry_email.grid(row=2, column=1, pady=5, padx=5)

        tk.Label(form_frame, text="PIN (if needed):", **lbl).grid(row=3, column=0, sticky="e", pady=5, padx=5)
        self.entry_pin = tk.Entry(form_frame, show="*", width=entry_width)
        self.entry_pin.grid(row=3, column=1, pady=5, padx=5)

        self.status_label = GradientFrame.label(self.inner_frame, "", font=("Segoe UI", 10))
        self.status_label.pack(pady=5)

        # BUG FIX: parent this to self.content (not self)
        btn_frame = GradientFrame.subframe(self.inner_frame)
        btn_frame.pack(pady=10)

        self.login_button = tk.Button(btn_frame, text="Log In", width=12, command=self.handle_login)
        self.login_button.grid(row=0, column=0, padx=10)

        quit_button = tk.Button(btn_frame, text="Quit", width=12, command=self.controller.destroy)
        quit_button.grid(row=0, column=1, padx=10)

        forgot_btn = tk.Button(
            btn_frame,
            text="Forgot Password",
            width=26,
            command=self.show_forgot_password,
        )
        forgot_btn.grid(row=1, column=0, columnspan=2, pady=(10, 0))

        # Note: you already have a global Enter handler in JHApp.bind_all("<Return>", ...)
        # Keeping this local bind is fine, but it may fire in addition to the global one.
        self.bind("<Return>", self._enter_login)


    def handle_login(self):
        username = self.entry_username.get().strip()
        password = self.entry_password.get()

        if not username or not password:
            messagebox.showerror("Login Error", "Username and password are required.")
            return

        self.status_label.config(text="Attempting quick login...")
        self.login_button.config(state="disabled")
        self.update_idletasks()

        success, require_full, msg, email, is_admin = api_quick_login(username, password)

        if success:
            self.controller.set_user(username=username, email=email, is_admin=is_admin)
            save_last_username(username)
            messagebox.showinfo("Login", "Quick login successful.")
            self.controller.show_frame("MainMenuFrame")
            self.login_button.config(state="normal")
            self.status_label.config(text="")
            return

        # If API says full login is needed
        if require_full:
            self.status_label.config(text="Quick login requires full login...")

            email = self.entry_email.get().strip()
            pin = self.entry_pin.get().strip()

            if not email or not pin:
                messagebox.showwarning(
                    "Full Login Required",
                    "Quick login failed. Please enter your email and PIN, then click Log In again."
                )
                self.login_button.config(state="normal")
                return

            success_full, msg_full = api_full_login(email, username, password, pin)
            if success_full:
                self.controller.set_user(username=username, email=email)
                save_last_username(username)
                messagebox.showinfo("Login", "Full login successful.")
                self.controller.show_frame("MainMenuFrame")
                self.status_label.config(text="")
            else:
                messagebox.showerror("Login Failed", msg_full)
                self.status_label.config(text=msg_full)

            self.login_button.config(state="normal")
            return

        # Quick login failed for another reason
        messagebox.showerror("Login Failed", msg)
        self.status_label.config(text=msg)
        self.login_button.config(state="normal")


    def show_forgot_password(self):
        message = (
            "Call or Email Project Dev Sammi Fishbein for immediate authentication services.\n\n"
            "Email: sammi.fishbein@jtax.com\n"
            "Phone: 1-(978)-729-7544"
        )
        messagebox.showinfo("Forgot Password", message)

    def _enter_login(self, event):
        self.handle_login()

# ----------------------------
# MAIN MENU FRAME
# ----------------------------

class MainMenuFrame(GradientFrame):
    """
    Buttons on LEFT
    White JH logo on RIGHT
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Load logo
        self.logo_image = None
        self.logo_label = tk.Label(self.inner_frame, bg=self.inner_frame.cget("bg"))
        self.load_logo()

        # LEFT CONTENT FRAME
        content_frame = GradientFrame.subframe(self.inner_frame, padx=20, pady=20)
        content_frame.pack(side="left", fill="y")

        title = GradientFrame.label(
            content_frame,
            "JH Reports – Main Menu",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(anchor="w", pady=(10, 5))

        self.user_label = GradientFrame.label(
            content_frame,
            "Logged in as:",
            font=("Segoe UI", 10),
        )
        self.user_label.pack(anchor="w", pady=(0, 20))

        btn_frame = GradientFrame.subframe(content_frame)
        btn_frame.pack(anchor="w")

        buttons = [
            ("Issue Tracking", lambda: self.controller.show_frame("IssueTrackingFrame")),
            ("Scheduling", lambda: self.controller.show_frame("SchedulingFrame")),
            ("Utilities", lambda: self.controller.show_frame("UtilitiesFrame")),
        ]

        for label, cmd in buttons:
            tk.Button(btn_frame, text=label, width=25, command=cmd).pack(anchor="w", pady=4)

        tk.Button(content_frame, text="Log Out", width=20, pady=1, command=self.handle_logout).pack(
            anchor="w", pady=(20, 0)
        )

        self.logo_label.pack(side="right", padx=40)

        self.bind("<<ShowFrame>>", self.on_show_frame)

    def load_logo(self):
        bg = self.content.cget("bg")

        if not PIL_AVAILABLE:
            self.logo_label.configure(text="JH", fg=JH_WHITE_TEXT, bg=bg)
            return

        try:
            img = Image.open(LOGO_WHITE_PATH)
            img.thumbnail((240, 240))
            self.logo_image = ImageTk.PhotoImage(img)
            self.logo_label.configure(image=self.logo_image, bg=bg)
        except Exception:
            self.logo_label.configure(text="JH", fg=JH_WHITE_TEXT, bg=bg)

    def on_show_frame(self, event=None):
        username = self.controller.current_username or "Unknown"
        email = self.controller.current_email
        if email:
            self.user_label.config(text=f"Logged in as: {username} ({email})")
        else:
            self.user_label.config(text=f"Logged in as: {username}")

    def handle_logout(self):
        self.controller.set_user(None, None)
        self.controller.show_frame("LoginFrame")

    def not_implemented_yet(self):
        messagebox.showinfo("Coming soon", "Feature not finished yet.")

# ----------------------------------------

class IssueTrackingFrame(GradientFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        title = GradientFrame.label(
            self.inner_frame,
            "Issue Tracking",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=25)

        btn_frame = GradientFrame.subframe(self.inner_frame, padx=20, pady=15)
        btn_frame.pack(pady=10)

        buttons = [
            ("Report Issue", lambda: self.controller.show_frame("ReportIssueFrame")),
            ("Edit Issue", lambda: self.controller.show_frame("EditIssueFrame")),
            ("Update Status", self.not_implemented_yet),
            ("View Issues (One Store)", lambda: self.controller.show_frame("ViewOneStoreFrame")),
            ("View All Issues", lambda: self.controller.show_frame("ViewAllIssuesFrame")),
            ("Search Issues", self.not_implemented_yet),
            ("Remove Issue", self.not_implemented_yet),
            ("Print All Issues", self.not_implemented_yet),
        ]

        for label, cmd in buttons:
            tk.Button(btn_frame, text=label, width=25, command=cmd).pack(pady=4)

        tk.Button(
            btn_frame,
            text="Back to Main Menu",
            width=25,
            command=lambda: self.controller.show_frame("MainMenuFrame"),
        ).pack(pady=(12, 4))

    def not_implemented_yet(self):
        messagebox.showinfo("Coming soon", "Feature not finished yet.")

class SchedulingFrame(GradientFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        title = GradientFrame.label(
            self.inner_frame,
            "Scheduling",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=25)

        btn_frame = GradientFrame.subframe(self.inner_frame, padx=20, pady=15)
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text="Visual Availability",
            width=30,
            command=lambda: self.controller.show_frame("VisualAvlFrame"),
        ).pack(pady=4)

        tk.Button(
            btn_frame,
            text="Employee List",
            width=30,
            command=lambda: self.controller.show_frame("EmployeeFrame"),
        ).pack(pady=4)

        tk.Button(
            btn_frame,
            text="Data Management",
            width=30,
            command=lambda: self.controller.show_frame("DataMgmtFrame"),
        ).pack(pady=4)

        tk.Button(
            btn_frame,
            text="Back to Main Menu",
            width=30,
            command=lambda: self.controller.show_frame("MainMenuFrame"),
        ).pack(pady=(12, 4))

class UtilitiesFrame(GradientFrame):
    """
    Utilities submenu:
    - Store Search
    - Tech Info By Store
    - Change Password
    - Change PIN
    - Admin Tools
    - Back to Main Menu
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        title = GradientFrame.label(
            self.inner_frame,
            "Utilities",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=25)

        btn_frame = GradientFrame.subframe(self.inner_frame, padx=20, pady=15)
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text="Store Lookup",
            width=25,
            command=lambda: self.controller.show_frame("StoreSearchFrame"),
        ).pack(pady=4)

        tk.Button(
            btn_frame,
            text="Tech Info By Store",
            width=25,
            command=lambda: self.controller.show_frame("TechInfoByStoreFrame"),
        ).pack(pady=4)

        tk.Button(
            btn_frame,
            text="Change Password",
            width=25,
            command=lambda: self.controller.show_frame("ChangePasswordFrame"),
        ).pack(pady=4)

        tk.Button(
            btn_frame,
            text="Change PIN",
            width=25,
            command=lambda: self.controller.show_frame("ChangePINFrame"),
        ).pack(pady=4)

        self.admin_button = tk.Button(
            btn_frame,
            text="Admin Tools",
            width=25,
            command=self.open_admin_tools,
        )
        self._admin_btn_packed = False

        tk.Button(
            btn_frame,
            text="Back to Main Menu",
            width=25,
            command=lambda: self.controller.show_frame("MainMenuFrame"),
        ).pack(pady=(12, 4))

        self.bind("<<ShowFrame>>", self.on_show_frame)

    def on_show_frame(self, event=None):
        if not self._admin_btn_packed:
            self.admin_button.pack(pady=4)
            self._admin_btn_packed = True

    def open_admin_tools(self):
        if not self.controller.current_email:
            messagebox.showerror("Error", "No email associated with this session.")
            return

        # If already verified, just open
        if self.controller.admin_session.get("verified"):
            self.controller.show_frame("AdminToolsFrame")
            return

        # Prompt based on server-provided is_admin
        if self.controller.current_is_admin:
            creds = self._require_admin_credentials()
        else:
            creds = self._require_admin_credentials_borrow()

        if not creds:
            return  # don't open on failure

        # Cache creds
        email, password, pin = creds
        scope = "full" if self.controller.current_is_admin else "users_read"
        self.controller.admin_session = {
            "verified": True,
            "scope": scope,
            "admin_email": email,
            "password": password,
            "pin": pin,
        }

        self.controller.show_frame("AdminToolsFrame")

    def _require_admin_credentials(self):
        """Prompt for password/pin for current user (trusted admin)."""
        email = self.controller.current_email
        password = simpledialog.askstring(
            "Admin Verification",
            f"Enter password for {email}:",
            show="*",
            parent=self,
        )
        if password is None:
            return None

        pin = simpledialog.askstring(
            "Admin Verification",
            "Enter your admin PIN:",
            show="*",
            parent=self,
        )
        if pin is None:
            return None

        ok, msg = api_admin_verify(email, password, pin)
        if not ok:
            messagebox.showerror("Verification Failed", msg)
            return None

        return email, password, pin

    def _require_admin_credentials_borrow(self):
        """Prompt for admin username/password/pin/email (borrow for non-admins)."""
        admin_username = simpledialog.askstring(
            "Admin Verification",
            "Enter admin username:",
            parent=self,
        )
        if admin_username is None:
            return None

        password = simpledialog.askstring(
            "Admin Verification",
            f"Enter password for {admin_username}:",
            show="*",
            parent=self,
        )
        if password is None:
            return None

        pin = simpledialog.askstring(
            "Admin Verification",
            "Enter admin PIN:",
            show="*",
            parent=self,
        )
        if pin is None:
            return None

        email = simpledialog.askstring(
            "Admin Verification",
            "Enter admin email:",
            parent=self,
        )
        if email is None:
            return None

        ok, msg = api_admin_verify(email, password, pin)
        if not ok:
            messagebox.showerror("Verification Failed", msg)
            return None

        return email, password, pin

# -----UTILITIES-FRAME-------------------------

class TechInfoByStoreFrame(GradientFrame):
    """
    Utilities -> Tech Info By Store

    Workflow:
    1) User enters a store number
    2) When a valid store is found, enable buttons:
       - Computer info
       - Printer/Scanner info
       - Phone info
       - Internet info
       - Other info
       - All info
    3) Output prints into right-side text area with your standard preface.

    Notes:
    - This frame is resilient: it supports multiple possible data shapes for inventory.
    - If inventory keys are missing (common right now), it prints a clean "No info recorded" message.
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.current_devices = []

        self.current_store_name = None
        self.current_store_details = None

        title = GradientFrame.label(
            self.inner_frame,
            "Tech Info By Store",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=20)

        self.status_label = GradientFrame.label(
            self.inner_frame,
            "",
            font=("Segoe UI", 10),
        )
        self.status_label.pack(pady=(0, 10))

        # --- Top input row ---
        top = GradientFrame.subframe(self.inner_frame)
        top.pack(padx=20, pady=10, fill="x")

        GradientFrame.label(
            top,
            "Enter store NUMBER:",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=5, pady=(0, 5))

        self.entry_store_num = tk.Entry(top, width=18)
        self.entry_store_num.grid(row=1, column=0, sticky="w", padx=5, pady=5)

        tk.Button(
            top,
            text="Load",
            width=12,
            command=self.handle_load_store,
        ).grid(row=1, column=1, sticky="w", padx=8, pady=5)

        # --- Main horizontal split: left buttons / right text ---
        main = GradientFrame.subframe(self.inner_frame)
        main.pack(padx=20, pady=10, fill="both", expand=True)

        self.left = GradientFrame.subframe(main)
        self.left.pack(side="left", fill="y", padx=(0, 20))

        self.right = GradientFrame.subframe(main)
        self.right.pack(side="right", fill="both", expand=True)

        # Buttons (disabled until store is loaded)
        self.btn_computers = tk.Button(self.left, text="Computer info", width=22, state="disabled",
                                       command=lambda: self.render_section("computers"))
        self.btn_printers = tk.Button(self.left, text="Printer/Scanner info", width=22, state="disabled",
                                      command=lambda: self.render_section("printers"))
        self.btn_phones = tk.Button(self.left, text="Phone info", width=22, state="disabled",
                                    command=lambda: self.render_section("phones"))
        self.btn_internet = tk.Button(self.left, text="Internet info", width=22, state="disabled",
                                      command=lambda: self.render_section("internet"))
        self.btn_other = tk.Button(self.left, text="Other info", width=22, state="disabled",
                                   command=lambda: self.render_section("other"))
        self.btn_all = tk.Button(self.left, text="All info", width=22, state="disabled",
                                 command=lambda: self.render_section("all"))

        for b in (self.btn_computers, self.btn_printers, self.btn_phones,
                  self.btn_internet, self.btn_other, self.btn_all):
            b.pack(anchor="w", pady=4)

        # Right text output
        panel_bg = self.right.cget("bg")
        self.text = scrolledtext.ScrolledText(
            self.right,
            width=80,
            height=22,
            wrap="word",
            bg=panel_bg,
            fg=JH_WHITE_TEXT,
        )
        self.text.pack(fill="both", expand=True)

        # Bottom nav
        bottom = GradientFrame.subframe(self.inner_frame)
        bottom.pack(pady=10)

        tk.Button(
            bottom,
            text="Back to Utilities",
            width=18,
            command=lambda: self.controller.show_frame("UtilitiesFrame"),
        ).pack()

        self.bind("<<ShowFrame>>", self.on_show_frame)

    def on_show_frame(self, event=None):
        self.status_label.config(text="")
        self.entry_store_num.delete(0, "end")
        self.current_store_name = None
        self.current_store_details = None
        self._set_buttons_enabled(False)
        self._clear_text()

    def _set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for b in (self.btn_computers, self.btn_printers, self.btn_phones,
                  self.btn_internet, self.btn_other, self.btn_all):
            b.config(state=state)

    def _clear_text(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def _set_text(self, content: str):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", content)
        self.text.configure(state="disabled")

    def handle_load_store(self):
        raw = self.entry_store_num.get().strip()
        if not raw:
            messagebox.showwarning("Input Required", "Please enter a store number.")
            return
        if not raw.isdigit():
            messagebox.showwarning("Invalid Input", "Store number must be numeric.")
            return

        stores, error = api_load_stores()
        if stores is None:
            self.status_label.config(text=error or "Failed to load stores.")
            messagebox.showerror("Error", error or "Failed to load stores from server.")
            return

        # Reset state each load attempt
        self.current_store_name = None
        self.current_store_details = None
        self.current_devices = []

        # Find by store number
        for name, details in stores.items():
            if str(details.get("Store Number")) == raw:
                self.current_store_name = name
                self.current_store_details = details
                self.status_label.config(text=f"Loaded store #{raw} – {name}")
                self._set_buttons_enabled(True)

                # ✅ Load devices for this store BEFORE rendering
                ok, devices, err = api_get_devices_by_store(int(raw))
                if not ok:
                    self._set_text(self._preface() + f"Error loading devices: {err}\n")
                    return

                self.current_devices = devices or []

                # Auto-render "All info"
                self.render_section("all")
                return

        # Not found
        self._set_buttons_enabled(False)
        self._set_text(f"No store found with number {raw}.\n")
        self.status_label.config(text=f"No store found with number {raw}.")

    # ----------------------------
    # Formatting + extraction helpers
    # ----------------------------

    def _preface(self) -> str:
        d = self.current_store_details or {}
        s_num = d.get("Store Number", "N/A")
        s_name = self.current_store_name or "Unknown Store"
        s_type = d.get("Type", "Unknown")
        header = f"{s_num} - {s_name}\n{s_type}\n" + ("=" * 23) + "\n\n"
        return header

    def _get_inventory_root(self) -> dict:
        """
        Where to look for inventory data.

        Supported patterns (any of these):
        - details["Tech Inventory"]  (dict)
        - details["Inventory"]       (dict)
        - details["Devices"]         (dict)
        - details["Tech"]            (dict)

        If none exist, returns empty dict.
        """
        d = self.current_store_details or {}
        for key in ("Tech Inventory", "Inventory", "Devices", "Tech"):
            val = d.get(key)
            if isinstance(val, dict):
                return val
        return {}

    def _get_device_list(self, section_key: str) -> list[dict]:
        """
        section_key: computers / phones / printers / internet / other
        devices come from store_devices table via /devices/by-store
        """
        devices = self.current_devices or []

        # Normalize your naming
        key = section_key.lower()

        def is_match(d):
            dt = (d.get("device_type") or "").strip().lower()

            # Map your categories to whatever you used in CSV:
            # (you can tweak these 5 lines once we see actual device_type values)
            if key == "computers":
                return dt in ("computer", "pc", "tp", "terminal") or dt.startswith("tp")
            if key == "phones":
                return (d.get("device_number") or "").strip().upper().startswith("P")
            if key == "printers":
                return dt in ("printer", "scanner", "printer/scanner", "mfp")
            if key == "internet":
                return dt in ("internet", "network", "cradlepoint", "router", "modem")
            if key == "other":
                return True  # catch-all
            return False

        # For "other", we’ll return only ones NOT caught by earlier categories
        if key == "other":
            cats = {"computers", "phones", "printers", "internet"}
            used = set()
            for c in cats:
                for d in self._get_device_list(c):
                    used.add(d.get("device_uid"))
            return [d for d in devices if d.get("device_uid") not in used]

        return [d for d in devices if is_match(d)]


    def _extract_flat_tp_or_p(self, section_key: str) -> list[dict]:
        """
        For computers: TP1, TP2, ...
        For phones: P1, P2, ...

        We try to read either:
        - details["TP1"] as dict, details["TP2"] as dict ...
        OR flat keys like:
        - "TP1 Device Number", "TP1 Manufacturer", "TP1 Model"
        - "P1 Device Number",  "P1 Manufacturer",  "P1 Model"

        If store metadata only has a computer count (details["Computers"]),
        we use that as our iteration range.
        """
        d = self.current_store_details or {}

        if section_key == "computers":
            prefix = "TP"
            # If you have "Computers" count, use it; else assume up to 6
            try:
                n = int(d.get("Computers", 0))
            except Exception:
                n = 0
            max_i = n if n > 0 else 6
        else:
            prefix = "P"
            max_i = 6  # phones count isn't currently stored; safe default

        out = []
        for i in range(1, max_i + 1):
            key = f"{prefix}{i}"

            # 1) nested dict form: details["TP1"] = {"device_number":..., ...}
            nested = d.get(key)
            if isinstance(nested, dict):
                out.append(nested)
                continue

            # 2) flat key form: "TP1 Manufacturer", etc.
            devnum = d.get(f"{key} Device Number") or d.get(f"{key} device_number") or d.get(f"{key} device")
            manu = d.get(f"{key} Manufacturer") or d.get(f"{key} manufacturer")
            model = d.get(f"{key} Model") or d.get(f"{key} model")

            if devnum or manu or model:
                out.append({
                    "device_number": devnum,
                    "manufacturer": manu,
                    "model": model,
                    "slot": key,
                })

        return out

    def _pretty_device(self, dev: dict, include_devnum=True) -> str:
        """
        Standard device printing:
        [device_number]
        [manufacturer]
        [model]
        """
        devnum = dev.get("device_number") or dev.get("Device Number") or dev.get("device") or dev.get("Device")
        manu = dev.get("manufacturer") or dev.get("Manufacturer")
        model = dev.get("model") or dev.get("Model")

        lines = []
        if include_devnum:
            lines.append(str(devnum or dev.get("slot") or "N/A"))
        lines.append(str(manu or "Unknown"))
        lines.append(str(model or "Unknown"))
        return "\n".join(lines) + "\n======\n"

    # ----------------------------
    # Renderers
    # ----------------------------

    def render_section(self, which: str):
        if not self.current_store_details or not self.current_store_name:
            messagebox.showwarning("No Store Loaded", "Please load a store first.")
            return

        parts = [self._preface()]

        if which in ("computers", "all"):
            parts.append(self._render_computers())

        if which in ("phones", "all"):
            parts.append(self._render_phones())

        if which in ("printers", "all"):
            parts.append(self._render_printers())

        if which in ("internet", "all"):
            parts.append(self._render_internet())

        if which in ("other", "all"):
            parts.append(self._render_other())

        self._set_text("".join(parts).rstrip() + "\n")

    def _render_computers(self) -> str:
        devices = self._get_device_list("computers")
        out = ["Computer info:\n\n"]

        if not devices:
            out.append("No computer info recorded for this store.\n\n")
            return "".join(out)

        # If you have explicit slot ordering, keep it (TP1..TPn)
        def sort_key(dev):
            slot = dev.get("slot") or dev.get("device_number") or ""
            slot = str(slot).upper()
            # pull TP number if present
            if slot.startswith("TP"):
                try:
                    return int(slot.replace("TP", "").strip())
                except Exception:
                    return 999
            return 999

        for dev in sorted(devices, key=sort_key):
            out.append(self._pretty_device(dev, include_devnum=True))

        return "".join(out)

    def _render_phones(self) -> str:
        devices = self._get_device_list("phones")
        out = ["Phones:\n\n"]

        if not devices:
            out.append("No phone info recorded for this store.\n\n")
            return "".join(out)

        def sort_key(dev):
            slot = dev.get("slot") or dev.get("device_number") or ""
            slot = str(slot).upper()
            if slot.startswith("P"):
                try:
                    return int(slot.replace("P", "").strip())
                except Exception:
                    return 999
            return 999

        for dev in sorted(devices, key=sort_key):
            out.append(self._pretty_device(dev, include_devnum=True))

        return "".join(out)

    def _render_printers(self) -> str:
        devices = self._get_device_list("printers")
        out = ["Printer Info:\n\n"]

        if not devices:
            # Also try a single dict form: inventory_root["printer"]
            inv = self._get_inventory_root()
            single = inv.get("printer") or inv.get("Printer")
            if isinstance(single, dict):
                devices = [single]

        if not devices:
            out.append("No printer/scanner info recorded for this store.\n\n")
            return "".join(out)

        for dev in devices:
            # Printer format: manufacturer + model (no device_number)
            manu = dev.get("manufacturer") or dev.get("Manufacturer") or "Unknown"
            model = dev.get("model") or dev.get("Model") or "Unknown"
            out.append(f"{manu}\n{model}\n\n")

        return "".join(out)

    def _render_internet(self) -> str:
        devices = self._get_device_list("internet")
        out = ["Internet info:\n\n"]

        if not devices:
            out.append("No internet/network info recorded for this store.\n\n")
            return "".join(out)

        for dev in devices:
            # Internet format:
            # [device_type]
            # [manufacturer]
            # [model]
            dtype = dev.get("device_type") or dev.get("Device Type") or dev.get("type") or "Unknown device"
            manu = dev.get("manufacturer") or dev.get("Manufacturer") or "Unknown"
            model = dev.get("model") or dev.get("Model") or "Unknown"
            out.append(f"{dtype}\n{manu}\n{model}\n\n")

        return "".join(out)

    def _render_other(self) -> str:
        devices = self._get_device_list("other")
        out = ["Other info:\n\n"]

        if not devices:
            out.append("No additional tech info recorded for this store.\n\n")
            return "".join(out)

        for dev in devices:
            # Flexible: print whatever we have cleanly
            label = dev.get("label") or dev.get("device_type") or dev.get("Device Type") or dev.get("type") or "Other device"
            manu = dev.get("manufacturer") or dev.get("Manufacturer") or "Unknown"
            model = dev.get("model") or dev.get("Model") or "Unknown"
            out.append(f"{label}\n{manu}\n{model}\n\n")

        return "".join(out)

class AdminToolsFrame(GradientFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # =========== TOP TITLE =============
        title = GradientFrame.label(
            self.inner_frame, "Admin Tools", font=("Segoe UI", 20, "bold")
        )
        title.pack(pady=20)

        # =========== MAIN HORIZONTAL SPLIT FRAME =============
        main_frame = GradientFrame.subframe(self.inner_frame, padx=20, pady=10)
        main_frame.pack(fill="both", expand=True)

        # LEFT COLUMN (buttons)
        left_frame = GradientFrame.subframe(main_frame)
        left_frame.pack(side="left", fill="y", padx=(0, 20))

        # RIGHT COLUMN (text area + export buttons)
        right_frame = GradientFrame.subframe(main_frame)
        right_frame.pack(side="right", fill="both", expand=True)

        # ------------- LEFT BUTTON STACK -------------
        self.btn_list_users = tk.Button(left_frame, text="List Users", width=25, command=self.admin_list_users)
        self.btn_list_users.pack(pady=4)

        self.btn_list_stores = tk.Button(left_frame, text="List All Store Info", width=25, command=self.admin_list_stores)
        self.btn_list_stores.pack(pady=4)

        self.btn_list_issues = tk.Button(left_frame, text="List All Issues", width=25, command=self.admin_list_issues)
        self.btn_list_issues.pack(pady=4)

        # ---- Account Management section (Create New User moved here, TOP) ----
        GradientFrame.label(left_frame, "Account Management", font=("Segoe UI", 12, "bold")).pack(pady=(12, 4))

        self.btn_create_user = tk.Button(left_frame, text="Create New User", width=25, command=self.open_create_user_window)
        self.btn_create_user.pack(pady=4)

        self.btn_admin_change_pw = tk.Button(left_frame, text="Admin Change Password", width=25, command=self.admin_change_password)
        self.btn_admin_change_pw.pack(pady=4)

        self.btn_admin_change_pin = tk.Button(left_frame, text="Admin Change PIN", width=25, command=self.admin_change_pin)
        self.btn_admin_change_pin.pack(pady=4)

        self.btn_admin_delete_user = tk.Button(left_frame, text="Admin Delete User", width=25, command=self.admin_delete_user)
        self.btn_admin_delete_user.pack(pady=4)

        # ---- System section ----
        GradientFrame.label(left_frame, "System", font=("Segoe UI", 12, "bold")).pack(pady=(12, 4))

        self.btn_admin_restart_api = tk.Button(left_frame, text="Admin Restart API", width=25, command=self.admin_restart_api)
        self.btn_admin_restart_api.pack(pady=4)

        self.btn_switch_admin = tk.Button(left_frame, text="Use Different Admin Credentials", width=25, command=self.clear_admin_session)
        self.btn_switch_admin.pack(pady=4)

        # ✅ New button goes here (between switch admin and back)
        self.btn_import_tech = tk.Button(left_frame, text="Import Tech Info (CSV)", width=25, command=self.import_tech_info_csv)
        self.btn_import_tech.pack(pady=4)

        tk.Button(left_frame, text="Back to Utilities", width=25, command=lambda: self.controller.show_frame("UtilitiesFrame")).pack(pady=(20, 4))

        # ------------- RIGHT SIDE (TITLE + TEXT) -------------
        self.report_title_label = GradientFrame.label(right_frame, "", font=("Segoe UI", 12, "bold"))
        self.report_title_label.pack(pady=(0, 6))

        panel_bg = right_frame.cget("bg")
        self.report_text = scrolledtext.ScrolledText(
            right_frame,
            width=80,
            height=25,
            wrap="word",
            bg=panel_bg,
            fg=JH_WHITE_TEXT
        )
        self.report_text.pack(fill="both", expand=True)

        # ------------- BOTTOM OF RIGHT SIDE -------------
        bottom_buttons = GradientFrame.subframe(right_frame)
        bottom_buttons.pack(pady=6)

        tk.Button(bottom_buttons, text="Print to Text File", width=18, command=self.export_report_to_file).grid(row=0, column=0, padx=5)
        tk.Button(bottom_buttons, text="Clear Report", width=18, command=self.clear_report).grid(row=0, column=1, padx=5)

        self.current_report_content = ""
        self.current_report_prefix = "admin_report"
        self.bind("<<ShowFrame>>", self.on_show_frame)

    # =============================
    # SHOW / PERMISSIONS
    # =============================
    def on_show_frame(self, event=None):
        if not self.controller.current_email:
            messagebox.showerror("Error", "No email associated with this session.")
            self.controller.show_frame("UtilitiesFrame")
            return

        s = self.controller.admin_session or {}
        if s.get("verified"):
            self.clear_report()
            self.apply_permissions()
            return

        # Prompt based on server-provided is_admin
        if self.controller.current_is_admin:
            creds = self._require_admin_credentials()  # current user prompt
        else:
            creds = self._require_admin_credentials_borrow()  # borrow prompt

        if not creds:
            self.controller.show_frame("UtilitiesFrame")
            return

        # Set scope
        email, password, pin = creds
        scope = "full" if self.controller.current_is_admin else "users_read"

        # Cache
        self.controller.admin_session = {
            "verified": True,
            "scope": scope,
            "admin_email": email,
            "password": password,
            "pin": pin,
        }

        self.clear_report()
        self.apply_permissions()

    def clear_report(self):
        self.report_title_label.config(text="")
        self.current_report_content = ""
        self.report_text.config(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.config(state="disabled")

    def export_report_to_file(self):
        if not self.current_report_content.strip():
            messagebox.showinfo("No Report", "There is no report to print to a file.")
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suggested = f"{self.current_report_prefix}_{ts}.txt"
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=suggested,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.current_report_content)
            messagebox.showinfo("Saved", f"Report saved to:\n{path}")
        except OSError as e:
            messagebox.showerror("Error", f"Could not save report:\n{e}")

    def _show_report(self, title: str, content: str, prefix: str):
        self.report_title_label.config(text=title)
        self.current_report_content = content
        self.current_report_prefix = prefix
        self.report_text.config(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("end", content)
        self.report_text.config(state="disabled")

    def clear_admin_session(self):
        if not self.controller.admin_session:
            self.controller.admin_session = {"verified": False, "scope": "none"}
        else:
            self.controller.admin_session["verified"] = False
            self.controller.admin_session["scope"] = "none"
        self.apply_permissions()
        messagebox.showinfo("Admin Session", "Cleared. Enter new credentials on next action.")

    def apply_permissions(self):
        s = self.controller.admin_session or {}
        scope = s.get("scope", "none")

        self.btn_list_users.config(state="normal")
        self.btn_switch_admin.config(state="normal" if s.get("verified") else "disabled")

        state_full = "normal" if scope == "full" else "disabled"
        for b in (
            self.btn_create_user,
            self.btn_list_stores,
            self.btn_list_issues,
            self.btn_admin_change_pw,
            self.btn_admin_change_pin,
            self.btn_admin_delete_user,
            self.btn_admin_restart_api,
            self.btn_import_tech,  # ✅ require full admin
        ):
            b.config(state=state_full)

    def ensure_full_admin(self):
        s = self.controller.admin_session or {}
        if s.get("verified") and s.get("scope") == "full":
            return True
        messagebox.showerror("Access Denied", "Full admin access required for this action.")
        return False

    # =============================
    # ADMIN AUTH PROMPTS
    # =============================
    def _require_admin_credentials(self):
        """Prompt for password/pin for current user (trusted admin)"""
        email = self.controller.current_email
        password = simpledialog.askstring("Admin Verification", f"Enter password for {email}:", show="*", parent=self)
        if password is None:
            return None

        pin = simpledialog.askstring("Admin Verification", "Enter your admin PIN:", show="*", parent=self)
        if pin is None:
            return None

        ok, msg = api_admin_verify(email, password, pin)
        if not ok:
            messagebox.showerror("Verification Failed", msg)
            return None

        return email, password, pin

    def _require_admin_credentials_borrow(self):
        """Prompt for admin username/password/pin/email (borrow for non-admins)"""
        admin_username = simpledialog.askstring("Admin Verification", "Enter admin username:", parent=self)
        if admin_username is None:
            return None

        password = simpledialog.askstring("Admin Verification", f"Enter password for {admin_username}:", show="*", parent=self)
        if password is None:
            return None

        pin = simpledialog.askstring("Admin Verification", "Enter admin PIN:", show="*", parent=self)
        if pin is None:
            return None

        email = simpledialog.askstring("Admin Verification", "Enter admin email:", parent=self)
        if email is None:
            return None

        ok, msg = api_admin_verify(email, password, pin)
        if not ok:
            messagebox.showerror("Verification Failed", msg)
            return None

        return email, password, pin

    # =============================
    # CSV IMPORT (BUILT-IN)
    # =============================
    def _api_admin_import_devices(self, rows: list, dry_run: bool, timeout: int = 120):
        """
        Calls Render API endpoint:
          POST /admin/import_devices
        Body:
          { "dry_run": true/false, "rows": [...] }
        Returns: (ok: bool, data: dict|None, err: str|None)
        """
        try:
            url = f"{API_BASE}/admin/import_devices"
            payload = {"dry_run": bool(dry_run), "rows": rows}
            resp = requests.post(url, json=payload, timeout=timeout)
            try:
                data = resp.json()
            except Exception:
                return False, None, f"Non-JSON response ({resp.status_code}): {resp.text[:300]}"

            if resp.status_code != 200 or not data.get("ok", False):
                return False, data, data.get("error", f"HTTP {resp.status_code}")

            return True, data, None
        except Exception as e:
            return False, None, str(e)

    def import_tech_info_csv(self):
        if not self.ensure_full_admin():
            return

        path = filedialog.askopenfilename(
            title="Select Tech Info CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return

        # Read CSV rows
        try:
            rows = []
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    rows.append(r)

            if not rows:
                messagebox.showwarning("Import Tech Info (CSV)", "CSV file had no rows.")
                return
        except Exception as e:
            messagebox.showerror("Import Tech Info (CSV)", f"Failed to read CSV:\n{e}")
            return

        # DRY RUN
        ok, data, err = self._api_admin_import_devices(rows, dry_run=True, timeout=180)
        if not ok:
            messagebox.showerror("Tech Import (Dry Run)", err or "Unknown error")
            return

        summary = data.get("summary") or {}
        processed = data.get("processed", len(rows))
        inserts = summary.get("insert", 0)
        updates = summary.get("update", 0)
        skips = summary.get("skip", 0)
        errors = summary.get("error", 0)

        report_lines = [
            "Tech Info Import (DRY RUN)",
            "--------------------------",
            f"File: {os.path.basename(path)}",
            f"Rows: {processed}",
            "",
            f"Inserts: {inserts}",
            f"Updates: {updates}",
            f"Skips:   {skips}",
            f"Errors:  {errors}",
            "",
        ]

        if errors:
            report_lines.append("First errors (up to 10):")
            for item in (data.get("errors") or [])[:10]:
                report_lines.append(f"- Row {item.get('row_index')}: {item.get('error')}")

        report = "\n".join(report_lines) + "\n"
        self._show_report("Tech Import (Dry Run)", report, "tech_import_dryrun")

        if not messagebox.askyesno(
            "Confirm Import",
            "Dry run complete.\n\nApply these changes to the database?"
        ):
            return

        # REAL APPLY
        ok2, data2, err2 = self._api_admin_import_devices(rows, dry_run=False, timeout=300)
        if not ok2:
            messagebox.showerror("Tech Import", err2 or "Unknown error")
            return

        summary2 = data2.get("summary") or {}
        processed2 = data2.get("processed", len(rows))
        applied2 = summary2.get("applied", 0)
        errors2 = summary2.get("error", 0)

        report2_lines = [
            "Tech Info Import (APPLIED)",
            "--------------------------",
            f"File: {os.path.basename(path)}",
            f"Rows: {processed2}",
            "",
            f"Applied: {applied2}",
            f"Errors:  {errors2}",
            "",
        ]

        if errors2:
            report2_lines.append("First errors (up to 20):")
            for item in (data2.get("errors") or [])[:20]:
                report2_lines.append(f"- Row {item.get('row_index')}: {item.get('error')}")

        report2 = "\n".join(report2_lines) + "\n"
        self._show_report("Tech Import (Applied)", report2, "tech_import_applied")

        if errors2:
            messagebox.showwarning("Tech Import", f"Import finished with errors: {errors2}\nSee report panel.")
        else:
            messagebox.showinfo("Tech Import", "Import complete (no errors).")

    # =============================
    # ADMIN ACTIONS (EXISTING)
    # =============================
    def admin_list_users(self):
        s = self.controller.admin_session or {}
        if not s.get("verified"):
            self.on_show_frame()
            return

        ok, users, error = api_admin_list_users(s["admin_email"], s["password"], s["pin"])
        if not ok:
            messagebox.showerror("Error", error or "Failed to load users.")
            return
        if not users:
            self._show_report("Users", "No users found.\n", "users")
            return
        lines = []
        for u in users:
            lines.append(f"Email: {u.get('email', 'N/A')}")
            lines.append(f"Username: {u.get('username', 'N/A')}")
            lines.append(f"Role: {u.get('role', 'user')}")
            lines.append("----------------------------")
        content = "\n".join(lines) + "\n"
        self._show_report("Users", content, "users")

    def open_create_user_window(self):
        """Open a small admin dialog to create a new user via /auth/register."""
        win = tk.Toplevel(self)
        win.title("Create User")
        win.geometry("400x260")

        tk.Label(win, text="Email:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        email_entry = tk.Entry(win, width=35)
        email_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(win, text="Username:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        username_entry = tk.Entry(win, width=35)
        username_entry.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(win, text="Password:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        password_entry = tk.Entry(win, width=35, show="*")
        password_entry.grid(row=2, column=1, padx=5, pady=5)

        tk.Label(win, text="Confirm Password:").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        confirm_entry = tk.Entry(win, width=35, show="*")
        confirm_entry.grid(row=3, column=1, padx=5, pady=5)

        tk.Label(win, text="PIN (4–6 digits):").grid(row=4, column=0, sticky="e", padx=5, pady=5)
        pin_entry = tk.Entry(win, width=10)
        pin_entry.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        def submit():
            email = email_entry.get().strip()
            username = username_entry.get().strip()
            password = password_entry.get()
            confirm = confirm_entry.get()
            pin = pin_entry.get().strip()

            if not email or not username or not password or not confirm or not pin:
                messagebox.showerror("Error", "All fields are required.")
                return

            if password != confirm:
                messagebox.showerror("Error", "Passwords do not match.")
                return

            if not pin.isdigit() or not (4 <= len(pin) <= 6):
                messagebox.showerror("Error", "PIN must be 4–6 digits.")
                return

            payload = {"email": email, "username": username, "password": password, "pin": pin}

            try:
                resp = requests.post(f"{API_BASE}/auth/register", json=payload, timeout=10)
            except requests.RequestException as e:
                messagebox.showerror("Network Error", f"Error talking to server:\n{e}")
                return

            if resp.status_code in (200, 201):
                messagebox.showinfo("Success", "User created successfully.")
                win.destroy()
            else:
                messagebox.showerror("Error", f"Failed to create user.\nStatus: {resp.status_code}\n\n{resp.text}")

        btn_frame = tk.Frame(win)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=15)

        tk.Button(btn_frame, text="Create User", command=submit).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", command=win.destroy).pack(side="left", padx=5)

    def admin_list_stores(self):
        if not self.ensure_full_admin():
            return

        s = self.controller.admin_session or {}
        if not s.get("verified"):
            self.on_show_frame()
            return

        stores, error = api_load_stores()
        if stores is None:
            messagebox.showerror("Error", error or "Failed to load stores.")
            return

        lines = []
        for name in sorted(stores.keys()):
            details = stores[name]
            lines.append(f"Store Name: {name}")
            lines.append(f"Store Number: {details.get('Store Number', 'N/A')}")
            lines.append(f"Address: {details.get('Address', 'Unknown')}")
            lines.append(
                f"City: {details.get('City', 'Unknown')}  "
                f"State: {details.get('State', 'Unknown')}  "
                f"ZIP: {details.get('ZIP', 'Unknown')}"
            )
            lines.append(f"Phone: {details.get('Phone', 'Unknown')}")
            lines.append(f"Type: {details.get('Type', 'Unknown')}")
            lines.append(f"Kiosk Type: {details.get('Kiosk Type', 'Unknown')}")
            lines.append(f"Computers: {details.get('Computers', 'Unknown')}")
            lines.append("----------------------------")
        content = "\n".join(lines) + "\n"
        self._show_report("All Store Info", content, "stores")

    def admin_list_issues(self):
        if not self.ensure_full_admin():
            return

        s = self.controller.admin_session or {}
        if not s.get("verified"):
            self.on_show_frame()
            return

        ok, rows, err = api_get_all_issues()
        if not ok:
            messagebox.showerror("Error", err or "Failed to load issues.")
            return

        if not rows:
            self._show_report("All Issues", "No issues found.\n", "issues")
            return

        from collections import defaultdict
        by_store = defaultdict(list)
        for row in rows:
            key = (row.get("store_name"), row.get("store_number"))
            by_store[key].append(row)

        lines = []
        total_issues = 0

        for (sName, sNum), issue_rows in sorted(
            by_store.items(),
            key=lambda k: (k[0][1] or 0, (k[0][0] or "").lower())
        ):
            if not issue_rows:
                continue

            lines.append(f"{sNum or '????'} - {sName or 'Unknown Store'}")
            lines.append("=" * 40)

            for r in issue_rows:
                total_issues += 1
                lines.append(f"Issue ID: {r.get('id', 'N/A')}")
                lines.append(f"Date: {r.get('created_at', 'N/A')}")
                lines.append(f"Category: {r.get('category', 'N/A')}")
                lines.append(f"Severity: {r.get('severity', 'N/A')}")
                lines.append(f"Status: {r.get('status', 'N/A')}")
                lines.append(f"Title: {r.get('title', 'N/A')}")
                lines.append(f"Details: {r.get('details', '')}")
                lines.append("-" * 40)

            lines.append("")

        header = f"Total Issues: {total_issues}\n\n"
        content = header + "\n".join(lines) + "\n"
        self._show_report("All Issues", content, "issues")

    def admin_change_password(self):
        if not self.ensure_full_admin():
            return
        s = self.controller.admin_session

        target_email = simpledialog.askstring(
            "Admin Change Password",
            "Enter the user's email to change password:",
            parent=self,
        )
        if not target_email:
            return

        new_pw = simpledialog.askstring(
            "Admin Change Password",
            f"Enter NEW password for {target_email}:",
            show="*",
            parent=self,
        )
        if not new_pw:
            return

        ok, msg = api_admin_change_password(
            s["admin_email"], s["password"], s["pin"],
            target_email, new_pw
        )
        if ok:
            messagebox.showinfo("Success", msg)
        else:
            messagebox.showerror("Error", msg)

    def admin_change_pin(self):
        if not self.ensure_full_admin():
            return
        s = self.controller.admin_session

        target_email = simpledialog.askstring(
            "Admin Change PIN",
            "Enter the user's email to change PIN:",
            parent=self,
        )
        if not target_email:
            return

        new_pin = simpledialog.askstring(
            "Admin Change PIN",
            f"Enter NEW PIN for {target_email}:",
            show="*",
            parent=self,
        )
        if not new_pin:
            return

        ok, msg = api_admin_change_pin(
            s["admin_email"], s["password"], s["pin"],
            target_email, new_pin
        )
        if ok:
            messagebox.showinfo("Success", msg)
        else:
            messagebox.showerror("Error", msg)

    def admin_delete_user(self):
        if not self.ensure_full_admin():
            return
        s = self.controller.admin_session

        target_email = simpledialog.askstring(
            "Admin Delete User",
            "Enter the user's email to DELETE:",
            parent=self,
        )
        if not target_email:
            return

        if not messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete user:\n{target_email}?",
        ):
            return

        ok, msg = api_admin_delete_user(
            s["admin_email"], s["password"], s["pin"],
            target_email
        )
        if ok:
            messagebox.showinfo("Success", msg)
        else:
            messagebox.showerror("Error", msg)

    def admin_restart_api(self):
        if not self.ensure_full_admin():
            return
        s = self.controller.admin_session

        if not messagebox.askyesno(
            "Restart API",
            "Are you sure you want to restart the API server?",
        ):
            return

        ok, msg = api_admin_restart_api(s["admin_email"], s["password"], s["pin"])
        if ok:
            messagebox.showinfo("Restart Requested", msg)
        else:
            messagebox.showerror("Error", msg)

class StoreSearchFrame(GradientFrame):
    """
    GUI version of storeLookup():
    - Enter store NAME or store NUMBER
    - Shows exact match, or partial matches, or "not found"
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        title = GradientFrame.label(
            self.inner_frame,
            "Store Search",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=20)

        self.status_label = GradientFrame.label(
            self.inner_frame,
            "",
            font=("Segoe UI", 10),
        )
        self.status_label.pack(pady=(0, 10))

        # Search bar
        search_frame = GradientFrame.subframe(self.inner_frame)
        search_frame.pack(pady=10, padx=20, fill="x")

        GradientFrame.label(
            search_frame,
            "Enter store NAME or NUMBER:",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=5, pady=(0, 5))

        self.entry_query = tk.Entry(search_frame, width=40)
        self.entry_query.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        tk.Button(
            search_frame,
            text="Search",
            width=12,
            command=self.handle_search,
        ).grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # Results text (put it in content, match bg)
        results_frame = GradientFrame.subframe(self.inner_frame)
        results_frame.pack(padx=20, pady=10, fill="both", expand=True)

        panel_bg = results_frame.cget("bg")
        self.text = scrolledtext.ScrolledText(
            results_frame,
            width=80,
            height=18,
            wrap="word",
            bg=panel_bg,
            fg=JH_WHITE_TEXT,
        )
        self.text.pack(fill="both", expand=True)

        # Back button
        bottom_frame = GradientFrame.subframe(self.inner_frame)
        bottom_frame.pack(pady=10)

        tk.Button(
            bottom_frame,
            text="Back to Utilities",
            width=18,
            command=lambda: self.controller.show_frame("UtilitiesFrame"),
        ).pack()

        self.bind("<<ShowFrame>>", self.on_show_frame)



    def on_show_frame(self, event=None):
        self.status_label.config(text="")
        self.entry_query.delete(0, "end")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def handle_search(self):
        query = self.entry_query.get().strip()
        if not query:
            messagebox.showwarning(
                "Input Required",
                "Please enter a store name or number.",
            )
            return

        stores, error = api_load_stores()
        if stores is None:
            self.status_label.config(text=error or "Failed to load stores.")
            messagebox.showerror(
                "Error",
                error or "Failed to load stores from server.",
            )
            return

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")

        # Try as number first
        if query.isdigit():
            for name, details in stores.items():
                if str(details.get("Store Number")) == query:
                    self.render_store_info(name, details)
                    self.status_label.config(
                        text=f"Found store #{query} – {name}"
                    )
                    self.text.configure(state="disabled")
                    return

            self.status_label.config(text=f"No store found with number {query}.")
            self.text.insert("end", f"No store found with number {query}.\n")
            self.text.configure(state="disabled")
            return

        # Otherwise treat as name (exact match, then partial)
        lowered = query.lower()

        # Exact match
        for name, details in stores.items():
            if name.lower() == lowered:
                self.render_store_info(name, details)
                self.status_label.config(text=f"Found store '{name}'.")
                self.text.configure(state="disabled")
                return

        # Partial matches
        matches = [
            (name, details)
            for name, details in stores.items()
            if lowered in name.lower()
        ]

        if not matches:
            self.status_label.config(text="No matching stores found.")
            self.text.insert("end", "No matching stores found.\n")
            self.text.configure(state="disabled")
            return

        if len(matches) == 1:
            name, details = matches[0]
            self.render_store_info(name, details)
            self.status_label.config(text=f"Found store '{name}'.")
        else:
            self.status_label.config(
                text=f"{len(matches)} stores matched your search."
            )
            self.text.insert(
                "end",
                "Multiple stores matched your search:\n\n",
            )
            for name, details in matches:
                num = details.get("Store Number", "N/A")
                state = details.get("State", "Unknown")
                type_ = details.get("Type", "Unknown")
                self.text.insert(
                    "end",
                    f"- {name} (Store {num}, {state}, {type_})\n",
                )

        self.text.configure(state="disabled")

    def render_store_info(self, name: str, details: dict):
        self.text.insert("end", "Store Information\n")
        self.text.insert("end", "----------------------------\n")
        self.text.insert("end", f"Store Name: {name}\n")
        self.text.insert("end", f"Store Number: {details.get('Store Number', 'N/A')}\n")
        self.text.insert("end", f"Address: {details.get('Address', 'Unknown')}\n")
        self.text.insert("end", f"City: {details.get('City', 'Unknown')}\n")
        self.text.insert("end", f"State: {details.get('State', 'Unknown')}\n")
        self.text.insert("end", f"ZIP: {details.get('ZIP', 'Unknown')}\n")
        self.text.insert("end", f"Phone: {details.get('Phone', 'Unknown')}\n")
        self.text.insert("end", f"Type: {details.get('Type', 'Unknown')}\n")
        self.text.insert("end", f"Kiosk Type: {details.get('Kiosk Type', 'Unknown')}\n")
        self.text.insert("end", f"Number of Computers: {details.get('Computers', 'Unknown')}\n")
        known_issues = len(details.get("Known Issues", []))
        self.text.insert("end", f"Known Issues: {known_issues} total\n")
        self.text.insert("end", "----------------------------\n")

class ChangePasswordFrame(GradientFrame):
    """
    Change password using /auth/change-password.
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        title = GradientFrame.label(
            self.inner_frame,
            "Change Password",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=20)

        form_frame = GradientFrame.subframe(self.inner_frame)
        form_frame.pack(pady=10)


        lbl = {"fg": JH_WHITE_TEXT, "bg": form_frame.cget("bg"), "font": ("Segoe UI", 10)}
        width = 30

        tk.Label(form_frame, text="Username:", **lbl).grid(
            row=0, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_username = tk.Entry(form_frame, width=width)
        self.entry_username.grid(row=0, column=1, padx=5, pady=4)

        tk.Label(form_frame, text="Email:", **lbl).grid(
            row=1, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_email = tk.Entry(form_frame, width=width)
        self.entry_email.grid(row=1, column=1, padx=5, pady=4)

        tk.Label(form_frame, text="Current Password:", **lbl).grid(
            row=2, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_current_pw = tk.Entry(form_frame, show="*", width=width)
        self.entry_current_pw.grid(row=2, column=1, padx=5, pady=4)

        tk.Label(form_frame, text="New Password:", **lbl).grid(
            row=3, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_new_pw = tk.Entry(form_frame, show="*", width=width)
        self.entry_new_pw.grid(row=3, column=1, padx=5, pady=4)

        tk.Label(form_frame, text="PIN:", **lbl).grid(
            row=4, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_pin = tk.Entry(form_frame, show="*", width=width)
        self.entry_pin.grid(row=4, column=1, padx=5, pady=4)

        self.status_label = GradientFrame.label(self.inner_frame, "", font=("Segoe UI", 10))
        self.status_label.pack(pady=(5, 0))

        btn_frame = GradientFrame.subframe(self.inner_frame)
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text="Submit",
            width=14,
            command=self.handle_submit,
        ).grid(row=0, column=0, padx=8)

        tk.Button(
            btn_frame,
            text="Back to Utilities",
            width=14,
            command=lambda: self.controller.show_frame("UtilitiesFrame"),
        ).grid(row=0, column=1, padx=8)

        # Optional: make Enter submit on this screen (plays nice even if you have a global bind)
        self.bind("<Return>", lambda e: self.handle_submit())

        self.bind("<<ShowFrame>>", self.on_show_frame)

    def on_show_frame(self, event=None):
        # Pre-fill username/email from logged in user if available
        self.entry_username.delete(0, "end")
        self.entry_email.delete(0, "end")

        if self.controller.current_username:
            self.entry_username.insert(0, self.controller.current_username)
        if self.controller.current_email:
            self.entry_email.insert(0, self.controller.current_email)

        self.entry_current_pw.delete(0, "end")
        self.entry_new_pw.delete(0, "end")
        self.entry_pin.delete(0, "end")
        self.status_label.config(text="")

        # Nice UX: cursor starts in current password
        self.entry_current_pw.focus_set()

    def handle_submit(self):
        username = self.entry_username.get().strip()
        email = self.entry_email.get().strip()
        current_pw = self.entry_current_pw.get()
        new_pw = self.entry_new_pw.get()
        pin = self.entry_pin.get()

        if not all([username, email, current_pw, new_pw, pin]):
            messagebox.showerror("Validation Error", "All fields are required.")
            return

        if current_pw == new_pw:
            messagebox.showerror("Validation Error", "New password must be different from the current password.")
            return

        self.status_label.config(text="Submitting password change...")
        self.update_idletasks()

        success, msg = api_change_password(email, username, current_pw, new_pw, pin)
        self.status_label.config(text=msg)

        if success:
            messagebox.showinfo("Password Changed", msg)
            # Clear sensitive fields after success
            self.entry_current_pw.delete(0, "end")
            self.entry_new_pw.delete(0, "end")
            self.entry_pin.delete(0, "end")
            self.entry_current_pw.focus_set()
        else:
            messagebox.showerror("Error", msg)

class ChangePINFrame(GradientFrame):
    """
    Change PIN using /auth/change-pin.
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        title = GradientFrame.label(
            self.inner_frame,
            "Change PIN",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=20)

        form_frame = GradientFrame.subframe(self.inner_frame)
        form_frame.pack(pady=10)

        # ✅ Match whatever bg the form_frame is using (prevents purple fill mismatch)
        lbl = {"fg": JH_WHITE_TEXT, "bg": form_frame.cget("bg"), "font": ("Segoe UI", 10)}
        width = 30

        tk.Label(form_frame, text="Username:", **lbl).grid(
            row=0, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_username = tk.Entry(form_frame, width=width)
        self.entry_username.grid(row=0, column=1, padx=5, pady=4)

        tk.Label(form_frame, text="Email:", **lbl).grid(
            row=1, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_email = tk.Entry(form_frame, width=width)
        self.entry_email.grid(row=1, column=1, padx=5, pady=4)

        tk.Label(form_frame, text="Account Password:", **lbl).grid(
            row=2, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_password = tk.Entry(form_frame, show="*", width=width)
        self.entry_password.grid(row=2, column=1, padx=5, pady=4)

        tk.Label(form_frame, text="Current PIN:", **lbl).grid(
            row=3, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_current_pin = tk.Entry(form_frame, show="*", width=width)
        self.entry_current_pin.grid(row=3, column=1, padx=5, pady=4)

        tk.Label(form_frame, text="New PIN:", **lbl).grid(
            row=4, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_new_pin = tk.Entry(form_frame, show="*", width=width)
        self.entry_new_pin.grid(row=4, column=1, padx=5, pady=4)

        self.status_label = GradientFrame.label(self.inner_frame, "", font=("Segoe UI", 10))
        self.status_label.pack(pady=(5, 0))

        btn_frame = GradientFrame.subframe(self.inner_frame)
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text="Submit",
            width=14,
            command=self.handle_submit,
        ).grid(row=0, column=0, padx=8)

        tk.Button(
            btn_frame,
            text="Back to Utilities",
            width=14,
            command=lambda: self.controller.show_frame("UtilitiesFrame"),
        ).grid(row=0, column=1, padx=8)

        # Optional: Enter submits on this screen
        self.bind("<Return>", lambda e: self.handle_submit())

        self.bind("<<ShowFrame>>", self.on_show_frame)

    def on_show_frame(self, event=None):
        # Pre-fill username/email from logged in user if available
        self.entry_username.delete(0, "end")
        self.entry_email.delete(0, "end")

        if self.controller.current_username:
            self.entry_username.insert(0, self.controller.current_username)
        if self.controller.current_email:
            self.entry_email.insert(0, self.controller.current_email)

        # Clear sensitive fields every time you enter
        self.entry_password.delete(0, "end")
        self.entry_current_pin.delete(0, "end")
        self.entry_new_pin.delete(0, "end")
        self.status_label.config(text="")

        # Nice UX: start typing password immediately
        self.entry_password.focus_set()

    def handle_submit(self):
        username = self.entry_username.get().strip()
        email = self.entry_email.get().strip()
        password = self.entry_password.get()
        current_pin = self.entry_current_pin.get().strip()
        new_pin = self.entry_new_pin.get().strip()

        if not all([username, email, password, current_pin, new_pin]):
            messagebox.showerror("Validation Error", "All fields are required.")
            return

        if current_pin == new_pin:
            messagebox.showerror("Validation Error", "New PIN must be different from the current PIN.")
            return

        # Optional strictness (keeps it user-friendly but avoids obvious mistakes)
        if not current_pin.isdigit() or not new_pin.isdigit():
            messagebox.showerror("Validation Error", "PIN must be numeric.")
            return

        self.status_label.config(text="Submitting PIN change...")
        self.update_idletasks()

        success, msg = api_change_pin(email, username, password, current_pin, new_pin)
        self.status_label.config(text=msg)

        if success:
            messagebox.showinfo("PIN Changed", msg)
            # Clear sensitive fields after success
            self.entry_password.delete(0, "end")
            self.entry_current_pin.delete(0, "end")
            self.entry_new_pin.delete(0, "end")
            self.entry_password.focus_set()
        else:
            messagebox.showerror("Error", msg)

# -----ISSUE-TRACKER------------------------------

class ReportIssueFrame(GradientFrame):



    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.stores = None  # will be loaded from API

        title = GradientFrame.label(
            self.inner_frame, "Report New Issue", font=("Segoe UI", 20, "bold")
        )
        title.pack(pady=20)

        self.status_label = GradientFrame.label(self.inner_frame, "", font=("Segoe UI", 10))
        self.status_label.pack(pady=(0, 10))

        form = GradientFrame.subframe(self.inner_frame)
        form.pack(pady=5, padx=20, fill="x")

        # ✅ IMPORTANT: match the form bg (don’t hardcode purple)
        label_style = {"fg": JH_WHITE_TEXT, "bg": form.cget("bg"), "font": ("Segoe UI", 10)}
        entry_width = 30

        # Row 0: Store number
        tk.Label(form, text="Store number:", **label_style).grid(
            row=0, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_store_num = tk.Entry(form, width=entry_width)
        self.entry_store_num.grid(row=0, column=1, sticky="w", padx=5, pady=4)

        # Row 1: Device type
        tk.Label(form, text="Device type:", **label_style).grid(
            row=1, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_device = tk.Entry(form, width=entry_width)
        self.entry_device.grid(row=1, column=1, sticky="w", padx=5, pady=4)

        # Row 2: Computer number
        tk.Label(form, text="Computer number (if computer):", **label_style).grid(
            row=2, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_comp_num = tk.Entry(form, width=entry_width)
        self.entry_comp_num.grid(row=2, column=1, sticky="w", padx=5, pady=4)

        # Row 3: Category
        tk.Label(form, text="Issue category:", **label_style).grid(
            row=3, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_category = tk.Entry(form, width=entry_width)
        self.entry_category.insert(0, "Hardware/Software/Network/etc.")
        self.entry_category.grid(row=3, column=1, sticky="w", padx=5, pady=4)

        # Row 4: Priority (1/2/3 like CLI)
        tk.Label(form, text="Priority:", **label_style).grid(
            row=4, column=0, sticky="e", padx=5, pady=4
        )
        self.priority_var = tk.StringVar(value="1 - Critical")
        priority_options = ["1 - Critical", "2 - Functional", "3 - Cosmetic"]
        self.priority_menu = tk.OptionMenu(form, self.priority_var, *priority_options)
        self.priority_menu.grid(row=4, column=1, sticky="w", padx=5, pady=4)

        # Row 5: Replicable?
        tk.Label(form, text="Replicable on other systems?:", **label_style).grid(
            row=5, column=0, sticky="e", padx=5, pady=4
        )
        self.replicable_var = tk.StringVar(value="No")
        self.replicable_menu = tk.OptionMenu(form, self.replicable_var, "Yes", "No")
        self.replicable_menu.grid(row=5, column=1, sticky="w", padx=5, pady=4)

        # Row 6: Global issue fields
        tk.Label(form, text="Global issue (more than one device)?:", **label_style).grid(
            row=6, column=0, sticky="e", padx=5, pady=4
        )
        self.global_issue_var = tk.StringVar(value="No")
        self.global_issue_menu = tk.OptionMenu(form, self.global_issue_var, "Yes", "No")
        self.global_issue_menu.grid(row=6, column=1, sticky="w", padx=5, pady=4)

        tk.Label(form, text="If global, how many devices?:", **label_style).grid(
            row=7, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_global_num = tk.Entry(form, width=entry_width)
        self.entry_global_num.grid(row=7, column=1, sticky="w", padx=5, pady=4)

        # Row 8: Issue name
        tk.Label(form, text="Issue name:", **label_style).grid(
            row=8, column=0, sticky="e", padx=5, pady=4
        )
        self.entry_issue_name = tk.Entry(form, width=entry_width + 10)
        self.entry_issue_name.grid(row=8, column=1, sticky="w", padx=5, pady=4)

        # Row 9: Description (multi-line)
        GradientFrame.label(
            self.inner_frame, "Description:", font=("Segoe UI", 10)
        ).pack(anchor="w", padx=20)

        # IMPORTANT: parent should be self.content, not self (keeps theme consistent)
        panel_bg = self.inner_frame.cget("bg")
        self.text_description = scrolledtext.ScrolledText(
            self.inner_frame,
            width=70,
            height=6,
            wrap="word",
            bg=panel_bg,
            fg=JH_WHITE_TEXT,
            insertbackground=JH_WHITE_TEXT,  # caret color so you can see it
        )
        self.text_description.pack(padx=20, pady=5, fill="x")

        # Buttons
        btn_frame = GradientFrame.subframe(self.inner_frame)
        btn_frame.pack(pady=20)

        submit_btn = tk.Button(
            btn_frame, text="Submit Issue", command=self.handle_submit, width=20
        )
        submit_btn.grid(row=0, column=0, padx=10)

        back_btn = tk.Button(
            btn_frame,
            text="Back to Main Menu",
            command=lambda: self.controller.show_frame("MainMenuFrame"),
            width=20,
        )
        back_btn.grid(row=0, column=1, padx=10)

        self.bind("<<ShowFrame>>", self.on_show_frame)

    def on_show_frame(self, event=None):
        """
        When this frame is shown, ensure stores are loaded (for validation)
        and clear status text.
        """
        self.status_label.config(text="")
        # Optionally load stores here so first submit isn't slow
        if self.stores is None:
            stores, error = api_load_stores()
            if stores is None:
                self.status_label.config(text=error or "Could not load stores list.")
            else:
                self.stores = stores

    def resolve_store_name(self, store_number: str):
        """
        Find store_name in the loaded stores dict from a store number.
        Returns store_name or None.
        """
        if not self.stores:
            return None

        for name, details in self.stores.items():
            if str(details.get("Store Number", "")).strip() == str(store_number).strip():
                return name
        return None

    def handle_submit(self):
        sNum = self.entry_store_num.get().strip()
        devName = self.entry_device.get().strip()
        compNum = self.entry_comp_num.get().strip()
        category = self.entry_category.get().strip()
        priority_choice = self.priority_var.get().strip()
        replicable_choice = self.replicable_var.get().strip()
        global_issue_choice = self.global_issue_var.get().strip()
        global_num_raw = self.entry_global_num.get().strip()
        issue_name = self.entry_issue_name.get().strip()
        desc = self.text_description.get("1.0", "end").strip()

        # Validation
        if not sNum.isdigit():
            messagebox.showerror("Validation Error", "Store number must be a number.")
            return

        if not devName:
            messagebox.showerror("Validation Error", "Device type is required.")
            return

        if not category or category == "Hardware/Software/Network/etc.":
            messagebox.showerror("Validation Error", "Please enter an issue category.")
            return

        if not issue_name:
            messagebox.showerror("Validation Error", "Please enter an issue name.")
            return

        if not desc:
            messagebox.showerror("Validation Error", "Please enter a description.")
            return

        # Load stores if not already loaded
        if self.stores is None:
            stores, error = api_load_stores()
            if stores is None:
                messagebox.showerror("Error", error or "Could not load stores list.")
                return
            self.stores = stores

        # Resolve store_name from store number
        store_name = self.resolve_store_name(sNum)
        if not store_name:
            messagebox.showerror("Validation Error", "Store number not found in store list.")
            return

        # Priority: keep "1"/"2"/"3" like CLI
        priority = priority_choice.split(" ")[0]

        # Replicable? (Yes/No)
        repro = "Yes" if replicable_choice == "Yes" else "No"

        # Global issue + number
        gIssue = global_issue_choice == "Yes"
        gNum = None
        if gIssue:
            if global_num_raw:
                if not global_num_raw.isdigit():
                    messagebox.showerror(
                        "Validation Error", "Global device count must be a whole number."
                    )
                    return
                gNum = int(global_num_raw)

        # Computer number logic
        if "computer" in devName.lower() and not compNum:
            if not messagebox.askyesno(
                "No Computer Number",
                "Device type includes 'computer' but computer number is blank.\n\n"
                "Submit anyway with 'N/A'?",
            ):
                return
            compNum = "N/A"
        elif not compNum:
            compNum = "N/A"

        # Build issue dict in legacy format expected by backend
        new_issue = {
            "Name": issue_name,
            "Issue Name": issue_name,
            "Priority": priority,
            "Store Number": sNum,
            "Computer Number": compNum,
            "Device": devName,
            "Category": category,
            "Description": desc,
            "Narrative": "",
            "Replicable?": repro,
            "Global Issue": gIssue,
            "Global Number": gNum,
            "Status": "Unresolved",
            "Resolution": "",
        }

        self.status_label.config(text="Submitting issue...")
        self.update_idletasks()

        success, msg = api_add_issue(store_name, new_issue)

        if success:
            messagebox.showinfo(
                "Issue Submitted", f"Issue '{issue_name}' added to {store_name}."
            )
            self.clear_fields()
            self.status_label.config(text="Issue submitted successfully.")
        else:
            messagebox.showerror("Error", msg)
            self.status_label.config(text=msg)

    def clear_fields(self):
        self.entry_store_num.delete(0, "end")
        self.entry_device.delete(0, "end")
        self.entry_comp_num.delete(0, "end")
        self.entry_category.delete(0, "end")
        self.entry_category.insert(0, "Hardware/Software/Network/etc.")
        self.priority_var.set("1 - Critical")
        self.replicable_var.set("No")
        self.global_issue_var.set("No")
        self.entry_global_num.delete(0, "end")
        self.entry_issue_name.delete(0, "end")
        self.text_description.delete("1.0", "end")

class EditIssueFrame(GradientFrame):
    """
    Edit Issue screen.

    Flow:
    - User enters either store number (digits) OR search text
    - Click "Search"
    - Select an issue from dropdown
    - Load -> edit -> Save
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.matches = []      # list of row dicts from the DB
        self.match_map = {}    # display_text -> row dict
        self.current_issue_id = None


        # -------------------------
        # UI CONTENT
        # -------------------------
        title = GradientFrame.label(
            self.inner_frame,
            "Edit Existing Issue",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=20)

        self.status_label = GradientFrame.label(self.inner_frame, "", font=("Segoe UI", 10))
        self.status_label.pack(pady=(0, 10))

        # Search area
        search_frame = GradientFrame.subframe(self.inner_frame)
        search_frame.pack(pady=10, padx=20, fill="x")

        GradientFrame.label(
            search_frame,
            "Enter a store number OR search for issue by name:",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 5))

        self.search_entry = tk.Entry(search_frame, width=40)
        self.search_entry.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        tk.Button(search_frame, text="Search", width=12, command=self.handle_search).grid(
            row=1, column=1, padx=5, pady=5, sticky="w"
        )

        # Results selector (only shown when results exist)
        self.selector_frame = GradientFrame.subframe(self.inner_frame)
        self.issue_var = tk.StringVar(value="")
        self.issue_menu = None

        # Form frame (only shown after loading an issue)
        self.form_frame = GradientFrame.subframe(self.inner_frame)
        self.build_form(self.form_frame)  # created but not packed yet

        bottom_frame = GradientFrame.subframe(self.inner_frame)
        bottom_frame.pack(pady=15)
        tk.Button(
            bottom_frame,
            text="Back to Main Menu",
            width=18,
            command=lambda: self.controller.show_frame("MainMenuFrame")
        ).pack()

        self.bind("<<ShowFrame>>", self.on_show_frame)

    # ---------- UI building ----------

    def build_form(self, parent):
        form = GradientFrame.subframe(parent)
        form.pack(pady=5, padx=20, fill="x")

        form_bg = form.cget("bg")
        label_style = {"fg": JH_WHITE_TEXT, "bg": form_bg, "font": ("Segoe UI", 10)}
        entry_width = 30

        tk.Label(form, text="Store number:", **label_style).grid(row=0, column=0, sticky="e", padx=5, pady=3)
        self.entry_store_num = tk.Entry(form, width=entry_width)
        self.entry_store_num.grid(row=0, column=1, sticky="w", padx=5, pady=3)

        tk.Label(form, text="Device type:", **label_style).grid(row=1, column=0, sticky="e", padx=5, pady=3)
        self.entry_device = tk.Entry(form, width=entry_width)
        self.entry_device.grid(row=1, column=1, sticky="w", padx=5, pady=3)

        tk.Label(form, text="Computer number:", **label_style).grid(row=2, column=0, sticky="e", padx=5, pady=3)
        self.entry_comp_num = tk.Entry(form, width=entry_width)
        self.entry_comp_num.grid(row=2, column=1, sticky="w", padx=5, pady=3)

        tk.Label(form, text="Category:", **label_style).grid(row=3, column=0, sticky="e", padx=5, pady=3)
        self.entry_category = tk.Entry(form, width=entry_width)
        self.entry_category.grid(row=3, column=1, sticky="w", padx=5, pady=3)

        tk.Label(form, text="Priority:", **label_style).grid(row=4, column=0, sticky="e", padx=5, pady=3)
        self.priority_var = tk.StringVar(value="1 - Critical")
        priority_options = ["1 - Critical", "2 - Functional", "3 - Cosmetic"]
        self.priority_menu = tk.OptionMenu(form, self.priority_var, *priority_options)
        self.priority_menu.grid(row=4, column=1, sticky="w", padx=5, pady=3)

        tk.Label(form, text="Replicable on other systems?", **label_style).grid(row=5, column=0, sticky="e", padx=5, pady=3)
        self.replicable_var = tk.StringVar(value="No")
        self.replicable_menu = tk.OptionMenu(form, self.replicable_var, "No", "Yes")
        self.replicable_menu.grid(row=5, column=1, sticky="w", padx=5, pady=3)

        tk.Label(form, text="Global issue?", **label_style).grid(row=6, column=0, sticky="e", padx=5, pady=3)
        self.global_issue_var = tk.StringVar(value="No")
        self.global_issue_menu = tk.OptionMenu(form, self.global_issue_var, "No", "Yes")
        self.global_issue_menu.grid(row=6, column=1, sticky="w", padx=5, pady=3)

        tk.Label(form, text="Global device count:", **label_style).grid(row=7, column=0, sticky="e", padx=5, pady=3)
        self.entry_global_num = tk.Entry(form, width=entry_width)
        self.entry_global_num.grid(row=7, column=1, sticky="w", padx=5, pady=3)

        tk.Label(form, text="Issue name:", **label_style).grid(row=8, column=0, sticky="e", padx=5, pady=3)
        self.entry_issue_name = tk.Entry(form, width=entry_width)
        self.entry_issue_name.grid(row=8, column=1, sticky="w", padx=5, pady=3)

        tk.Label(form, text="Status:", **label_style).grid(row=9, column=0, sticky="e", padx=5, pady=3)
        self.status_var = tk.StringVar(value="Unresolved")
        status_options = ["Unresolved", "In Progress", "Resolved", "Closed"]
        self.status_menu = tk.OptionMenu(form, self.status_var, *status_options)
        self.status_menu.grid(row=9, column=1, sticky="w", padx=5, pady=3)

        # Text areas (match ReportIssueFrame pattern)
        GradientFrame.label(parent, "Description:", font=("Segoe UI", 10)).pack(anchor="w", padx=25)
        panel_bg = parent.cget("bg")
        self.text_description = scrolledtext.ScrolledText(
            parent,
            width=70,
            height=4,
            wrap="word",
            bg=panel_bg,
            fg=JH_WHITE_TEXT,
            insertbackground=JH_WHITE_TEXT
        )
        self.text_description.pack(padx=25, pady=3, fill="x")

        GradientFrame.label(parent, "Narrative:", font=("Segoe UI", 10)).pack(anchor="w", padx=25)
        self.text_narrative = scrolledtext.ScrolledText(
            parent,
            width=70,
            height=4,
            wrap="word",
            bg=panel_bg,
            fg=JH_WHITE_TEXT,
            insertbackground=JH_WHITE_TEXT
        )
        self.text_narrative.pack(padx=25, pady=3, fill="x")

        GradientFrame.label(parent, "Resolution (if any):", font=("Segoe UI", 10)).pack(anchor="w", padx=25)
        self.text_resolution = scrolledtext.ScrolledText(
            parent,
            width=70,
            height=3,
            wrap="word",
            bg=panel_bg,
            fg=JH_WHITE_TEXT,
            insertbackground=JH_WHITE_TEXT
        )
        self.text_resolution.pack(padx=25, pady=3, fill="x")

        btn_frame = GradientFrame.subframe(parent)
        btn_frame.pack(pady=15)

        tk.Button(btn_frame, text="Save Changes", width=18, command=self.handle_save).grid(row=0, column=0, padx=10)
        tk.Button(btn_frame, text="Cancel Changes", width=18, command=self.clear_form).grid(row=0, column=1, padx=10)

    # ---------- Frame lifecycle ----------

    def on_show_frame(self, event=None):
        self.status_label.config(text="")
        self.search_entry.delete(0, "end")
        self.matches = []
        self.match_map = {}
        self.current_issue_id = None

        self.selector_frame.pack_forget()
        self.form_frame.pack_forget()

        try:
            self.canvas.yview_moveto(0.0)
        except Exception:
            pass

    # ---------- Search logic ----------

    def handle_search(self):
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning("Input Required", "Please enter a store number or search text.")
            return

        self.status_label.config(text="Searching the database...")
        self.update_idletasks()

        self.match_map.clear()

        if query.isdigit():
            ok, rows, error = api_search_issues(store_number=int(query), name=None)
        else:
            ok, rows, error = api_search_issues(store_number=None, name=query)

        if not ok:
            self.selector_frame.pack_forget()
            self.form_frame.pack_forget()
            self.status_label.config(text=error or "Search failed.")
            messagebox.showerror("Search Error", error or "Search failed.")
            return

        if not rows:
            self.selector_frame.pack_forget()
            self.form_frame.pack_forget()
            self.status_label.config(text="No matching issues found.")
            return

        for row in rows:
            store_num = row.get("store_number", "Unknown")
            name = row.get("issue_name") or row.get("issue") or "Unnamed Issue"
            display = f"Store {store_num} – {name}"
            self.match_map[display] = row

        self.build_selector_ui()
        self.status_label.config(text=f"Found {len(rows)} matching issue(s).")

    def build_selector_ui(self):
        for child in self.selector_frame.winfo_children():
            child.destroy()

        GradientFrame.label(
            self.selector_frame,
            "Select an issue to edit:",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=25, pady=(5, 2))

        options = sorted(self.match_map.keys())
        self.issue_var.set(options[0])

        self.issue_menu = tk.OptionMenu(self.selector_frame, self.issue_var, *options)
        self.issue_menu.pack(anchor="w", padx=25, pady=3)

        tk.Button(
            self.selector_frame,
            text="Load Issue",
            width=15,
            command=self.load_selected_issue
        ).pack(anchor="w", padx=25, pady=5)

        self.selector_frame.pack(pady=10, fill="x")

    # ---------- Load + show issue ----------

    def load_selected_issue(self):
        key = self.issue_var.get()
        if key not in self.match_map:
            messagebox.showerror("Error", "Please select an issue.")
            return

        row = self.match_map[key]
        self.current_issue_id = row.get("id")

        self.entry_store_num.delete(0, "end")
        self.entry_store_num.insert(0, str(row.get("store_number") or ""))

        self.entry_device.delete(0, "end")
        self.entry_device.insert(0, row.get("device_type") or "")

        self.entry_comp_num.delete(0, "end")
        self.entry_comp_num.insert(0, row.get("computer_number") or "")

        self.entry_category.delete(0, "end")
        self.entry_category.insert(0, row.get("category") or "")

        pr = str(row.get("priority") or "1")
        if pr == "1":
            self.priority_var.set("1 - Critical")
        elif pr == "2":
            self.priority_var.set("2 - Functional")
        elif pr == "3":
            self.priority_var.set("3 - Cosmetic")
        else:
            self.priority_var.set("1 - Critical")

        repro = (row.get("replicable") or "").strip().lower()
        self.replicable_var.set("Yes" if repro in ("yes", "y", "true", "1") else "No")

        self.global_issue_var.set("Yes" if row.get("global_issue") else "No")

        self.entry_global_num.delete(0, "end")
        g_num = row.get("global_num")
        if g_num is not None:
            self.entry_global_num.insert(0, str(g_num))

        self.entry_issue_name.delete(0, "end")
        self.entry_issue_name.insert(0, row.get("issue_name") or "")

        self.status_var.set(row.get("status") or "Unresolved")

        self.text_description.delete("1.0", "end")
        self.text_description.insert("1.0", row.get("description") or "")

        self.text_narrative.delete("1.0", "end")
        self.text_narrative.insert("1.0", row.get("narrative") or "")

        self.text_resolution.delete("1.0", "end")
        self.text_resolution.insert("1.0", row.get("resolution") or "")

        self.form_frame.pack(pady=10, fill="both", expand=True)
        self.canvas.after(10, lambda: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    # ---------- Saving ----------

    def handle_save(self):
        if self.current_issue_id is None:
            messagebox.showerror("Error", "No issue is currently loaded.")
            return

        sNum = self.entry_store_num.get().strip()
        devName = self.entry_device.get().strip()
        compNum = self.entry_comp_num.get().strip()
        category = self.entry_category.get().strip()
        priority_choice = self.priority_var.get()
        replicable_choice = self.replicable_var.get()
        global_issue_choice = self.global_issue_var.get()
        global_num_raw = self.entry_global_num.get().strip()
        issue_name = self.entry_issue_name.get().strip()
        status_choice = self.status_var.get()
        desc = self.text_description.get("1.0", "end").strip()
        narrative = self.text_narrative.get("1.0", "end").strip()
        resolution_text = self.text_resolution.get("1.0", "end").strip()

        if not sNum.isdigit():
            messagebox.showerror("Validation Error", "Store number must be a number.")
            return
        if not issue_name:
            messagebox.showerror("Validation Error", "Issue name is required.")
            return
        if not devName:
            messagebox.showerror("Validation Error", "Device type is required.")
            return
        if not category:
            messagebox.showerror("Validation Error", "Category is required.")
            return

        priority = priority_choice.split(" ")[0] if priority_choice else "1"
        repro = "Yes" if replicable_choice == "Yes" else "No"

        gIssue = (global_issue_choice == "Yes")
        gNum = None
        if gIssue and global_num_raw:
            if not global_num_raw.isdigit():
                messagebox.showerror("Validation Error", "Global device count must be a whole number.")
                return
            gNum = int(global_num_raw)

        if "computer" in devName.lower() and not compNum:
            if not messagebox.askyesno(
                "No Computer Number",
                "Device type includes 'computer' but computer number is blank.\n\nSave anyway with 'N/A'?"
            ):
                return
            compNum = "N/A"
        elif not compNum:
            compNum = "N/A"

        updated_issue = {
            "Name": issue_name,
            "Issue Name": issue_name,
            "Priority": priority,
            "Store Number": sNum,
            "Computer Number": compNum,
            "Device": devName,
            "Category": category,
            "Description": desc,
            "Narrative": narrative,
            "Replicable?": repro,
            "Global Issue": gIssue,
            "Global Number": gNum,
            "Status": status_choice,
            "Resolution": resolution_text,
        }

        self.status_label.config(text="Saving changes...")
        self.update_idletasks()

        success, msg = api_update_issue(self.current_issue_id, updated_issue)

        if success:
            messagebox.showinfo("Saved", "Issue updated successfully.")
            self.status_label.config(text="Issue updated successfully.")
        else:
            messagebox.showerror("Error", msg or "Failed to update issue.")
            self.status_label.config(text=msg or "Failed to update issue.")

    def clear_form(self):
        self.current_issue_id = None

        self.entry_store_num.delete(0, "end")
        self.entry_device.delete(0, "end")
        self.entry_comp_num.delete(0, "end")
        self.entry_category.delete(0, "end")
        self.priority_var.set("1 - Critical")
        self.replicable_var.set("No")
        self.global_issue_var.set("No")
        self.entry_global_num.delete(0, "end")
        self.entry_issue_name.delete(0, "end")
        self.status_var.set("Unresolved")
        self.text_description.delete("1.0", "end")
        self.text_narrative.delete("1.0", "end")
        self.text_resolution.delete("1.0", "end")

        self.form_frame.pack_forget()
        self.status_label.config(text="Changes cancelled. Load an issue to edit again.")

class ViewOneStoreFrame(GradientFrame):
    """
    View issues for a single store by store number or store name.
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        title = GradientFrame.label(
            self.inner_frame,
            "View Issues – One Store",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=20)

        self.status_label = GradientFrame.label(
            self.inner_frame,
            "",
            font=("Segoe UI", 10),
        )
        self.status_label.pack(pady=(0, 10))

        # --- Search area ---
        search_frame = GradientFrame.subframe(self.inner_frame)
        search_frame.pack(pady=10, padx=20, fill="x")

        GradientFrame.label(
            search_frame,
            "Enter a store number OR exact store name:",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 5))

        self.search_entry = tk.Entry(search_frame, width=40)
        self.search_entry.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        tk.Button(
            search_frame,
            text="Load Issues",
            width=15,
            command=self.handle_search,
        ).grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # --- Results area ---
        results_frame = GradientFrame.subframe(self.inner_frame)
        results_frame.pack(padx=20, pady=10, fill="both", expand=True)

        panel_bg = results_frame.cget("bg")

        self.text = scrolledtext.ScrolledText(
            results_frame,
            width=80,
            height=20,
            wrap="word",
            bg=panel_bg,                 # ✅ match container bg (same pattern as AdminToolsFrame)
            fg=JH_WHITE_TEXT,
            insertbackground=JH_WHITE_TEXT
        )
        self.text.pack(fill="both", expand=True)

        # Header lines (issue number + name) will be yellow & bold
        self.text.tag_configure(
            "issue_header",
            foreground="yellow",
            font=("Segoe UI", 10, "bold"),
        )

        # Start read-only until we print results
        self.text.configure(state="disabled")

        # Back button
        bottom_frame = GradientFrame.subframe(self.inner_frame)
        bottom_frame.pack(pady=10)
        tk.Button(
            bottom_frame,
            text="Back to Main Menu",
            width=18,
            command=lambda: self.controller.show_frame("MainMenuFrame"),
        ).pack()

        self.bind("<<ShowFrame>>", self.on_show_frame)

    def on_show_frame(self, event=None):
        self.status_label.config(text="")
        self.search_entry.delete(0, "end")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def handle_search(self):
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning(
                "Input Required",
                "Please enter a store number or store name.",
            )
            return

        # Decide if this is a store number or name
        store_number = None
        store_name = None
        if query.isdigit():
            store_number = int(query)
        else:
            store_name = query

        ok, rows, error = api_get_issues_by_store(
            store_number=store_number,
            store_name=store_name,
        )

        if not ok:
            self.status_label.config(text=error or "Failed to load issues.")
            messagebox.showerror(
                "Error",
                error or "Failed to load issues for that store.",
            )
            return

        if not rows:
            self.status_label.config(text="No issues found for that store.")
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.insert("end", "No issues found for that store.\n")
            self.text.configure(state="disabled")
            return

        self.render_issues(rows)

    def render_issues(self, rows: list[dict]):
        first = rows[0]
        store_name = first.get("store_name") or "Unknown Store"
        store_number = first.get("store_number") or "Unknown"

        header = f"Viewing Issues for {store_name} (Store {store_number})\n\n"

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", header)

        for idx, row in enumerate(rows, start=1):
            issue_name = row.get("issue_name") or "Unnamed Issue"
            status = row.get("status") or "Unresolved"

            # Header line: number + issue name + [status] in yellow
            header_line = f"{idx}. {issue_name} [{status}]\n"
            self.text.insert("end", header_line, ("issue_header",))

            device = row.get("device_type") or ""
            if device:
                self.text.insert("end", f"Device: {device}\n")

            category = row.get("category") or ""
            if category:
                self.text.insert("end", f"Category: {category}\n")

            comp = row.get("computer_number")
            if comp and str(comp).strip().upper() != "N/A":
                self.text.insert("end", f"Computer: {comp}\n")

            priority_raw = row.get("priority")
            pretty_priority = "Unknown"
            if priority_raw is not None:
                val = str(priority_raw).strip()
                if val == "1":
                    pretty_priority = "Critical"
                elif val == "2":
                    pretty_priority = "Functional"
                elif val == "3":
                    pretty_priority = "Cosmetic"
                else:
                    pretty_priority = val
            self.text.insert("end", f"Priority: {pretty_priority}\n")

            desc = row.get("description") or ""
            if desc:
                self.text.insert("end", f"Description: {desc}\n")

            narrative = row.get("narrative") or ""
            if narrative:
                self.text.insert("end", f"Narrative: {narrative}\n")

            resolution = row.get("resolution") or ""
            if resolution:
                self.text.insert("end", f"Resolution: {resolution}\n")

            self.text.insert("end", "\n" + "-" * 60 + "\n\n")

        self.text.configure(state="disabled")
        self.status_label.config(text=f"Loaded {len(rows)} issue(s).")

class ViewAllIssuesFrame(GradientFrame):
    """
    View all issues for all stores, grouped by store.

    NOTE:
    - Uses api_load_stores() to get store metadata.
    - Uses api_get_issues_by_store() to get issues per store.
    - Calls update_idletasks() inside the loop so the UI doesn't appear frozen.
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        title = GradientFrame.label(
            self.inner_frame,
            "View All Issues",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=20)

        self.status_label = GradientFrame.label(
            self.inner_frame,
            "",
            font=("Segoe UI", 10),
        )
        self.status_label.pack(pady=(0, 10))

        # Button to refresh/load all
        top_btn_frame = GradientFrame.subframe(self.inner_frame)
        top_btn_frame.pack(pady=5)

        tk.Button(
            top_btn_frame,
            text="Load / Refresh All Issues",
            width=22,
            command=self.handle_refresh,
        ).pack()

        # Text area (parented to self.content + uses panel bg)
        panel_bg = self.content.cget("bg")
        self.text = scrolledtext.ScrolledText(
            self.content,
            width=80,
            height=22,
            wrap="word",
            bg=panel_bg,
            fg=JH_WHITE_TEXT,
        )
        self.text.pack(padx=20, pady=10, fill="both", expand=True)

        # Tag for issue header lines
        self.text.tag_configure(
            "issue_header",
            foreground="yellow",
            font=("Segoe UI", 10, "bold"),
        )

        # Tag for store headers (bold white)
        self.text.tag_configure(
            "store_header",
            font=("Segoe UI", 11, "bold"),
        )

        # Back button
        bottom_frame = GradientFrame.subframe(self.inner_frame)
        bottom_frame.pack(pady=10)

        tk.Button(
            bottom_frame,
            text="Back to Main Menu",
            width=18,
            command=lambda: self.controller.show_frame("MainMenuFrame"),
        ).pack()

        self.bind("<<ShowFrame>>", self.on_show_frame)

        # Start disabled until we load
        self.text.configure(state="disabled")

    def on_show_frame(self, event=None):
        # Just clear the text / status when entering.
        # User explicitly clicks "Load / Refresh All Issues" to start the heavy work.
        self.status_label.config(text="")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def handle_refresh(self):
        # Step 1: load stores
        self.status_label.config(text="Loading stores from server...")
        self.update_idletasks()

        stores, error = api_load_stores()
        if stores is None:
            self.status_label.config(text=error or "Failed to load stores.")
            messagebox.showerror(
                "Error",
                error or "Failed to load stores metadata.",
            )
            return

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "Loading issues for all stores...\n\n")
        self.update_idletasks()

        total_issues = 0
        store_count = 0

        # Step 2: loop through stores and fetch issues for each
        for sName in sorted(stores.keys()):
            details = stores[sName]
            sNum = details.get("Store Number")

            # Skip stores without a usable store number
            if sNum is None:
                continue

            store_count += 1
            self.status_label.config(text=f"Loading issues for {sName} (Store {sNum})...")
            self.update_idletasks()

            ok2, rows, err2 = api_get_issues_by_store(
                store_number=sNum,
                store_name=None,
            )
            if not ok2:
                # If one store fails, log it and keep going
                self.text.insert(
                    "end",
                    f"{sName} (Store {sNum}) – error loading issues: {err2}\n\n",
                )
                self.update_idletasks()
                continue

            if not rows:
                # No issues for this store – skip printing anything
                continue

            total_issues += len(rows)

            # Store header
            header = f"{sName} (Store {sNum})"
            self.text.insert("end", header + "\n", ("store_header",))
            self.text.insert("end", "-" * len(header) + "\n")

            # Issues under this store
            for idx, row in enumerate(rows, start=1):
                issue_name = row.get("issue_name") or "Unnamed Issue"
                status = row.get("status") or "Unresolved"

                header_line = f"{idx}. {issue_name} [{status}]\n"
                self.text.insert("end", header_line, ("issue_header",))

                device = row.get("device_type") or ""
                if device:
                    self.text.insert("end", f"Device: {device}\n")

                category = row.get("category") or ""
                if category:
                    self.text.insert("end", f"Category: {category}\n")

                comp = row.get("computer_number")
                if comp and str(comp).strip().upper() != "N/A":
                    self.text.insert("end", f"Computer: {comp}\n")

                # Priority conversion
                priority_raw = row.get("priority")
                pretty_priority = "Unknown"
                if priority_raw is not None:
                    val = str(priority_raw).strip()
                    if val == "1":
                        pretty_priority = "Critical"
                    elif val == "2":
                        pretty_priority = "Functional"
                    elif val == "3":
                        pretty_priority = "Cosmetic"
                    else:
                        pretty_priority = val
                self.text.insert("end", f"Priority: {pretty_priority}\n")

                # Global issue info
                g_issue = row.get("global_issue")
                if g_issue is not None:
                    self.text.insert("end", f"Global issue: {'Yes' if g_issue else 'No'}\n")

                g_num = row.get("global_num")
                if g_num is not None:
                    self.text.insert("end", f"Devices affected: {g_num}\n")

                # Description
                desc = row.get("description") or ""
                if desc:
                    self.text.insert("end", f"Description:\n{desc}\n")

                # Narrative
                narrative = row.get("narrative") or ""
                if narrative:
                    self.text.insert("end", f"Narrative:\n{narrative}\n")

                # Resolution
                resolution = row.get("resolution") or ""
                if resolution:
                    self.text.insert("end", f"Resolution:\n{resolution}\n")

                # Separator
                self.text.insert("end", "\n----    ----    ----    ----    \n\n")

            self.text.insert("end", "\n")

        self.text.configure(state="disabled")
        self.status_label.config(text=f"Done. Loaded {total_issues} issue(s) across {store_count} store(s).")

# -----SCHEDULING-FRAME----------------------------

class VisualAvlFrame(GradientFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        GradientFrame.label(
            self.inner_frame,
            "Visual Availability",
            font=("Segoe UI", 20, "bold")
        ).pack(pady=20)

        controls = GradientFrame.subframe(self.inner_frame, padx=15, pady=10)
        controls.pack(fill="x")

        tk.Label(controls, text="Store Number:").pack(side="left", padx=(0, 6))
        self.store_entry = tk.Entry(controls, width=10)
        self.store_entry.pack(side="left")

        tk.Button(
            controls,
            text="Load",
            command=self.load_schedule
        ).pack(side="left", padx=10)

        self.output = tk.Text(self.inner_frame, height=14, width=60)
        self.output.pack(padx=20, pady=10, fill="both", expand=True)

        tk.Button(
            self.inner_frame,
            text="Back to Scheduling",
            width=22,
            command=lambda: self.controller.show_frame("SchedulingFrame")
        ).pack(pady=15)

    def load_schedule(self):
        store_txt = self.store_entry.get().strip()
        if not store_txt.isdigit():
            messagebox.showerror("Invalid store", "Enter a numeric store number.")
            return

        store_number = int(store_txt)

        try:
            url = f"{API_BASE}/schedule/store/{store_number}"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load schedule:\n{e}")
            return

        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

        self.output.delete("1.0", "end")
        self.output.insert("end", f"Store {store_number} — Availability (read-only)\n\n")

        days = data.get("days") or []
        if not days:
            self.output.insert("end", "(No schedule rows returned.)\n")
            self.output.insert("end", "Tip: the API normally auto-initializes 7 days on first GET.\n")
            return

        for d in days:
            day_idx = d.get("day")
            status = (d.get("status") or "").upper()
            start = d.get("start")
            end = d.get("end")

            name = day_names[day_idx] if isinstance(day_idx, int) and 0 <= day_idx <= 6 else str(day_idx)

            if status in ("STANDARD", "CUSTOM"):
                # If something weird happens and start/end are None, show it clearly
                if start and end:
                    line = f"{name}: {start} - {end} ({status})"
                else:
                    line = f"{name}: (missing time) ({status})"
            elif status == "OFF":
                line = f"{name}: OFF"
            elif status == "BLOCK":
                line = f"{name}: BLOCK"
            else:
                line = f"{name}: {status or '(unknown)'}"

            self.output.insert("end", line + "\n")

class EmployeeFrame(GradientFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        GradientFrame.label(
            self.inner_frame, "Employee List",
            font=("Segoe UI", 20, "bold")
        ).pack(pady=20)

        controls = GradientFrame.subframe(self.inner_frame, padx=15, pady=10)
        controls.pack(fill="x")

        GradientFrame.label(controls, "Store Number:").pack(side="left", padx=(0, 6))

        self.store_entry = tk.Entry(controls, width=10)
        self.store_entry.pack(side="left")

        tk.Button(controls, text="Load", command=self.load_employees).pack(side="left", padx=10)

        self.output = tk.Text(self.inner_frame, height=16, width=70)
        self.output.pack(padx=20, pady=10, fill="both", expand=True)

        tk.Button(
            self.inner_frame,
            text="Back to Scheduling",
            width=22,
            command=lambda: self.controller.show_frame("SchedulingFrame")
        ).pack(pady=12)

    def load_employees(self):
        store_txt = self.store_entry.get().strip()
        if not store_txt.isdigit():
            messagebox.showerror("Invalid store", "Enter a numeric store number.")
            return

        store_number = int(store_txt)

        try:
            url = f"{API_BASE}/schedule/employees/{store_number}"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load employees:\n{e}")
            return

        self.output.delete("1.0", "end")
        self.output.insert("end", f"Store {store_number} Employees\n\n")

        employees = data.get("employees") or []
        if not employees:
            self.output.insert("end", "(No employees found)\n")
            return

        for emp in employees:
            name = emp.get("full_name") or "Unnamed"
            role = emp.get("role_title") or ""
            active = bool(emp.get("is_active"))
            archived_until = emp.get("archived_until")

            status = "ACTIVE" if active else "INACTIVE"
            if archived_until:
                status += f" (archived until {archived_until[:10]})"

            line = f"- {name}"
            if role:
                line += f" — {role}"
            line += f" — {status}"
            self.output.insert("end", line + "\n")

class DataMgmtFrame(GradientFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.xl_session = XLSetupSession(workbook_filename="AVL_DB_2D.xlsx")

        GradientFrame.label(
            self.inner_frame,
            "Scheduling Data Management",
            font=("Segoe UI", 20, "bold")
        ).pack(pady=25)

        # --- action buttons ---
        btn_frame = GradientFrame.subframe(self.inner_frame, padx=20, pady=15)
        btn_frame.pack(pady=(10, 8))

        tk.Button(
            btn_frame,
            text="Add Data (XLScript)",
            width=28,
            command=self.open_XLConsole
        ).pack(pady=4)

        tk.Button(
            btn_frame,
            text="Edit Employees",
            width=28,
            command=self.open_employee_tools_readonly
        ).pack(pady=4)

        tk.Button(
            btn_frame,
            text="Adjust Store Hours",
            width=28,
            command=self.open_hours_readonly
        ).pack(pady=4)

        tk.Button(
            btn_frame,
            text="Download Data",
            width=28,
            command=self.download_readonly
        ).pack(pady=4)

        # --- log panel so user always sees feedback ---
        GradientFrame.label(
            self.inner_frame,
            "Log",
            font=("Segoe UI", 12, "bold")
        ).pack(pady=(10, 4))

        self.log = tk.Text(self.inner_frame, height=10, width=75)
        self.log.pack(padx=20, pady=(0, 10), fill="both", expand=True)

        tk.Button(
            self.inner_frame,
            text="Back to Scheduling",
            width=28,
            command=lambda: self.controller.show_frame("SchedulingFrame")
        ).pack(pady=(0, 12))

        self._log_line("Ready. These tools are read-only placeholders for now.")

    def _log_line(self, msg: str):
        self.log.insert("end", msg.rstrip() + "\n")
        self.log.see("end")

    def open_XLConsole(self):
        XLScriptConsoleWindow(self, session=self.xl_session, api_mode=False)

    # -----------------------
    # Read-only placeholder actions (Phase 1)
    # -----------------------

    def open_employee_tools_readonly(self):
        self._log_line("[Employees] Tools opened (read-only). Next phase: add/edit/archive employees.")
        self._simple_popup(
            title="Employee Tools (Read-Only Placeholder)",
            body=(
                "Next step (Phase 2):\n"
                "- Import schedule_employees\n"
                "- Add employee create/archive endpoints\n"
                "- Wire UI forms\n\n"
                "For now: use Employee List (Read-Only) to view employees."
            )
        )

    def open_hours_readonly(self):
        self._log_line("[Store Hours] Opened (read-only). Next phase: edit STANDARD/CUSTOM/OFF/BLOCK.")
        self._simple_popup(
            title="Adjust Store Hours (Read-Only Placeholder)",
            body=(
                "Right now:\n"
                "- Visual Availability reads resolved hours via GET /schedule/store/<store_number>\n\n"
                "Next step (Phase 2/3):\n"
                "- Add endpoints to set store day status/times\n"
                "- Add safeguards for status transitions\n"
            )
        )

    def download_readonly(self):
        self._log_line("[Download] Placeholder clicked. Next phase: export CSV/JSON.")
        self._simple_popup(
            title="Download Data (Read-Only Placeholder)",
            body=(
                "Next step (later):\n"
                "- Export employees\n"
                "- Export store schedules\n"
                "- Export availability overlays\n\n"
                "For now: this is a placeholder."
            )
        )

    def _simple_popup(self, title: str, body: str):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("560x320")

        container = tk.Frame(win, padx=12, pady=12)
        container.pack(fill="both", expand=True)

        tk.Label(container, text=title, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        text = tk.Text(container, wrap="word")
        text.pack(fill="both", expand=True, pady=(8, 10))
        text.insert("1.0", body)
        text.config(state="disabled")

        tk.Button(container, text="Close", width=14, command=win.destroy).pack(anchor="e")

# ----------------------------
# ROOT APP
# ----------------------------

class JHApp(tk.Tk):
    """
    Root Tkinter app using a 'frame stack' pattern:
    - LoginFrame
    - MainMenuFrame
    - ReportIssueFrame
    """

    def __init__(self):
        super().__init__()

        self.title("JH Reports – GUI")
        self.geometry("700x550")
        self.resizable(True, True)

        # Logged-in user info
        self.current_username = None
        self.current_email = None
        self.is_admin = False

        # Root window base
        self.configure(bg="black")

        # ONE container only
        container = tk.Frame(self, bg="black")
        container.pack(fill="both", expand=True)

        # ---- Gradient background (1x, global) ----
        if PIL_AVAILABLE:
            # Type-checker reassurance (since Image/ImageTk may be None when PIL isn't installed)
            assert Image is not None and ImageTk is not None

            # Load original once
            self._bg_original = Image.open(GRADIENT_PATH)

            # Pillow compatibility: LANCZOS moved in newer versions
            try:
                resample = Image.Resampling.LANCZOS
            except Exception:
                resample = getattr(Image, "LANCZOS", 1)

            bg_img = self._bg_original.resize((700, 550), resample)
            self.bg_photo = ImageTk.PhotoImage(bg_img)
            self.bg_label = tk.Label(container, image=self.bg_photo, bd=0)
        else:
            self._bg_original = None
            self.bg_label = tk.Label(container, bg=JH_PURPLE, bd=0)


        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        # This is the "frame stack" parent now
        self.bg_label.grid_rowconfigure(0, weight=1)
        self.bg_label.grid_columnconfigure(0, weight=1)


        # ---- Resize handler (MUST be inside __init__) ----
        def _resize_bg(event):
            if not PIL_AVAILABLE or self._bg_original is None:
                return

            # Type-checker reassurance
            assert Image is not None and ImageTk is not None

            w, h = event.width, event.height
            if w < 2 or h < 2:
                return

            # Pillow compatibility: LANCZOS moved in newer versions
            try:
                resample = Image.Resampling.LANCZOS
            except Exception:
                resample = getattr(Image, "LANCZOS", 1)

            img = self._bg_original.resize((w, h), resample)
            self.bg_photo = ImageTk.PhotoImage(img)
            self.bg_label.configure(image=self.bg_photo)

        container.bind("<Configure>", _resize_bg)

        self.frames = {}

        for F in (
                LoginFrame,
                MainMenuFrame,

                IssueTrackingFrame,
                ReportIssueFrame,
                EditIssueFrame,
                ViewOneStoreFrame,
                ViewAllIssuesFrame,
                StoreSearchFrame,

                SchedulingFrame,
                DataMgmtFrame,
                VisualAvlFrame,
                EmployeeFrame,

                UtilitiesFrame,
                TechInfoByStoreFrame,

                AdminToolsFrame,
                ChangePasswordFrame,
                ChangePINFrame,
        ):
            frame = F(parent=self.bg_label, controller=self)
            self.frames[F.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.current_frame_name = None
        self.show_frame("LoginFrame")

        # Global Enter-key handler for QOL
        self.bind_all("<Return>", self.on_enter_key)



    def show_frame(self, name: str):
        """Raise a frame by its class name and fire <<ShowFrame>>."""
        frame = self.frames.get(name)
        if frame:
            # remember which frame is active
            self.current_frame_name = name
            frame.event_generate("<<ShowFrame>>")
            frame.tkraise()

    def on_enter_key(self, event=None):
        """
        Global handler for the Enter key.

        - On LoginFrame: trigger login
        - On ReportIssueFrame: submit new issue
        - On EditIssueFrame:
            * if no issue loaded yet -> search
            * if issue is loaded -> save changes
        - Ignore Enter if focus is inside a multi-line Text/ScrolledText widget
        """
        # Don't hijack Enter when typing in multi-line text boxes
        if isinstance(getattr(event, "widget", None), tk.Text):
            return

        frame = self.frames.get(getattr(self, "current_frame_name", None))
        if frame is None:
            return

        # Login screen
        if isinstance(frame, LoginFrame):
            frame.handle_login()
            return

        # New issue screen
        if isinstance(frame, ReportIssueFrame):
            frame.handle_submit()
            return

        # Edit issue screen
        if isinstance(frame, EditIssueFrame):
            # If no issue loaded yet, Enter should act like "Search"
            if getattr(frame, "current_issue_id", None) is None:
                frame.handle_search()
            else:
                frame.handle_save()
            return

    def set_user(self, username: str | None, email: str | None = None, is_admin: bool = False):
        self.current_username = username
        self.current_email = email
        self.current_is_admin = is_admin  # NEW
        self.is_admin = False  # keep your existing reset
        self.admin_session = {
            "verified": False,
            "scope": "none",
            "admin_username": None,
            "admin_email": None,
            "password": None,
            "pin": None,
        }


if __name__ == "__main__":
    app = JHApp()
    app.mainloop()
