# XLConsole.py
import tkinter as tk
from tkinter import messagebox



from XLEngine import XLSetupSession, XLScriptBufferedRepl


class XLScriptConsoleWindow(tk.Toplevel):
    def __init__(self, parent, session: XLSetupSession, api_mode: bool = False, api_base: str = ""):
        super().__init__(parent)
        self.session = session
        self.repl = XLScriptBufferedRepl(session)
        self.api_mode = api_mode
        self.api_base = api_base.rstrip("/")

        self.title("XLSetup — XLScript Console")
        self.geometry("820x560")

        # Header
        header = tk.Frame(self, padx=12, pady=10)
        header.pack(fill="x")

        self.banner_var = tk.StringVar()
        self._refresh_banner()
        tk.Label(header, textvariable=self.banner_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")

        tk.Label(
            header,
            text="Rule: Enter submits a line. A BLANK line executes the buffered block.\nSingle-line commands (RMV/RRMV/RVRT) execute immediately.",
            justify="left"
        ).pack(anchor="w", pady=(6, 0))

        # Body
        body = tk.Frame(self, padx=12, pady=10)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        right = tk.Frame(body)
        right.pack(side="right", fill="both", expand=True)

        # Input area
        tk.Label(left, text="Input (type lines here):", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.input_text = tk.Text(left, height=14, wrap="none")
        self.input_text.pack(fill="both", expand=True)

        btns = tk.Frame(left)
        btns.pack(fill="x", pady=(8, 0))

        tk.Button(btns, text="Send Line", width=14, command=self.send_current_line).pack(side="left")
        tk.Button(btns, text="Send All Lines", width=14, command=self.send_all_lines).pack(side="left", padx=6)
        tk.Button(btns, text="Execute Block (Blank Line)", width=22, command=self.execute_blank_line).pack(side="left")

        # Output area
        tk.Label(right, text="Console Output:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.output = tk.Text(right, height=14, wrap="word")
        self.output.pack(fill="both", expand=True)

        # Footer / quick commands
        footer = tk.Frame(self, padx=12, pady=10)
        footer.pack(fill="x")

        tk.Button(footer, text="RVRT OFF", width=12, command=lambda: self._exec_line("RVRT OFF")).pack(side="left")
        tk.Button(footer, text="Help", width=10, command=self.show_help).pack(side="left", padx=6)
        tk.Button(footer, text="Close", width=10, command=self.destroy).pack(side="right")

        # Bind Enter: insert newline (normal), BUT we’ll let you click buttons to execute.
        # If you want Enter key to "send current line", tell me and I’ll bind it safely.

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
        # sends the last line of the input box
        txt = self.input_text.get("1.0", "end-1c")
        if not txt.strip():
            self._print("(No input.)")
            return
        last_line = txt.splitlines()[-1]
        self._exec_line(last_line)

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
