# XLConsole.py
import tkinter as tk
from tkinter import messagebox



from XLEngine import XLSetupSession, XLScriptBufferedRepl


BG_MAIN   = "#0d1117"
BG_PANEL  = "#151b23"
BG_INPUT  = "#1e242a"

FG_TEXT   = "#ffffff"
FG_DIM    = "#c9d1d9"


class XLScriptConsoleWindow(tk.Toplevel):
    def __init__(self, parent, session: XLSetupSession, api_mode: bool = False, api_base: str = ""):
        super().__init__(parent)
        self.session = session
        self.repl = XLScriptBufferedRepl(session)
        self.api_mode = api_mode
        self.api_base = api_base.rstrip("/")

        # ---- Dark theme (console ONLY) ----
        # Make sure these constants exist at top of XLConsole.py:
        # BG_MAIN="#0d1117", BG_PANEL="#151b23", BG_INPUT="#1e242a"
        # FG_TEXT="#ffffff", FG_DIM="#c9d1d9"
        self.configure(bg=BG_MAIN)

        self.title("XLSetup — XLScript Console")
        self.geometry("820x560")

        # Helper for consistent dark buttons
        def dark_button(parent_widget, **kwargs):
            return tk.Button(
                parent_widget,
                bg=BG_PANEL,
                fg=FG_TEXT,
                activebackground=BG_INPUT,
                activeforeground=FG_TEXT,
                relief="flat",
                highlightthickness=0,
                bd=0,
                **kwargs
            )

        # ---------------- Header ----------------
        header = tk.Frame(self, padx=12, pady=10, bg=BG_PANEL)
        header.pack(fill="x")

        self.banner_var = tk.StringVar()
        self._refresh_banner()

        tk.Label(
            header,
            textvariable=self.banner_var,
            font=("Segoe UI", 11, "bold"),
            fg=FG_TEXT,
            bg=BG_PANEL
        ).pack(anchor="w")

        tk.Label(
            header,
            text=(
                "Rule: Enter submits a line. A BLANK line executes the buffered block.\n"
                "Single-line commands (RMV/RRMV/RVRT) execute immediately."
            ),
            justify="left",
            fg=FG_DIM,
            bg=BG_PANEL
        ).pack(anchor="w", pady=(6, 0))

        # ---------------- Body ----------------
        body = tk.Frame(self, padx=12, pady=10, bg=BG_MAIN)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG_MAIN)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        right = tk.Frame(body, bg=BG_MAIN)
        right.pack(side="right", fill="both", expand=True)

        # Input area
        tk.Label(
            left,
            text="Input (type lines here):",
            font=("Segoe UI", 10, "bold"),
            fg=FG_TEXT,
            bg=BG_MAIN
        ).pack(anchor="w")

        self.input_text = tk.Text(
            left,
            height=14,
            wrap="none",
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,       # cursor
            selectbackground="#30363d",     # selection (GitHub-ish)
            relief="flat",
            bd=0
        )
        self.input_text.pack(fill="both", expand=True)

        btns = tk.Frame(left, bg=BG_MAIN)
        btns.pack(fill="x", pady=(8, 0))

        dark_button(btns, text="Send Line", width=14, command=self.send_current_line).pack(side="left")
        dark_button(btns, text="Send All Lines", width=14, command=self.send_all_lines).pack(side="left", padx=6)
        dark_button(btns, text="Execute Block (Blank Line)", width=22, command=self.execute_blank_line).pack(side="left")

        self.input_text.bind("<Return>", self._on_enter)

        # Output area
        tk.Label(
            right,
            text="Console Output:",
            font=("Segoe UI", 10, "bold"),
            fg=FG_TEXT,
            bg=BG_MAIN
        ).pack(anchor="w")

        self.output = tk.Text(
            right,
            height=14,
            wrap="word",
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            selectbackground="#30363d",
            relief="flat",
            bd=0
        )
        self.output.pack(fill="both", expand=True)

        # ---------------- Footer ----------------
        footer = tk.Frame(self, padx=12, pady=10, bg=BG_PANEL)
        footer.pack(fill="x")

        dark_button(footer, text="RVRT OFF", width=12, command=lambda: self._exec_line("RVRT OFF")).pack(side="left")
        dark_button(footer, text="Help", width=10, command=self.show_help).pack(side="left", padx=6)
        dark_button(footer, text="Close", width=10, command=self.destroy).pack(side="right")

        # Startup message
        self._print(f"Thanks for using XLSetup! You are editing file version {self.session.active_version}.\n")

    def _refresh_banner(self):
        rvrt = f"RVRT={self.session.revert_version}" if self.session.revert_active else "RVRT=OFF"
        self.banner_var.set(f"XLSetup Console — Active Version: {self.session.active_version}   |   {rvrt}")


    def _print(self, msg: str):
        self.output.insert("end", msg.rstrip() + "\n")
        self.output.see("end")

    def show_help(self):
        messagebox.showinfo(
            "XLScript Help",
            "Multi-line blocks execute when you press Enter on a blank line.\n\n"
            "Examples:\n"
            "UPDATE BY EX=11 WITH:\n"
            "  DAY=a\n"
            "  AVL=ALL o\n"
            "  SNUM!=11529\n"
            "(blank line executes)\n\n"
            "Single-line immediate:\n"
            "RRMV ROW=23\n"
            "RVRT=2C\n"
            "RVRT OFF\n"
        )

    def send_current_line(self):
        # sends the line the cursor is currently on
        try:
            index = self.input_text.index("insert")
            line_no = index.split(".")[0]
            line = self.input_text.get(f"{line_no}.0", f"{line_no}.end")
        except Exception:
            line = ""

        if not line.strip():
            self._exec_line("")  # treat empty current line as "blank line executes"
            return

        self._exec_line(line)

    def send_all_lines(self):
        txt = self.input_text.get("1.0", "end-1c")
        if not txt.strip():
            self._print("(No input.)")
            return
        for line in txt.splitlines():
            self._exec_line(line)

    def execute_blank_line(self):
        # emulate user pressing Enter on a blank line
        self._exec_line("")

    def _exec_line(self, line: str):
        result = self.repl.feed_line(line)

        if result["executed"]:
            # Update session if RVRT command in actions (local behavior)
            for a in result["actions"]:
                if a.get("type") == "RVRT":
                    self.session.set_revert(a["target"]["version"])
                    self._refresh_banner()

            # Local dry-run output now; later we can route to API
            self._print("=== EXECUTE ===")
            self._print(result["script"])
            self._print("--- PLAN ---")
            for p in result["plan"]:
                self._print(p)
            self._print("")

        else:
            # buffered line
            if line.strip():
                self._print(f"(buffered) {line.lstrip()}")

    def _on_enter(self, event):
        # Grab the current line where the cursor is
        try:
            index = self.input_text.index("insert")
            line_no = index.split(".")[0]
            line = self.input_text.get(f"{line_no}.0", f"{line_no}.end")
        except Exception:
            line = ""

        # Send it to the REPL (blank line triggers execute)
        self._exec_line(line)

        # Move cursor to next line in the input box (like a console prompt)
        self.input_text.insert("insert", "\n")
        self.input_text.see("insert")

        # Prevent Tkinter from also inserting its own newline behavior
        return "break"

