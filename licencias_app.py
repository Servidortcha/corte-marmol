"""Generador de licencias AresaNest (app de escritorio).

Uso:  .venv\\Scripts\\python.exe licencias_app.py
Para compilar: build_licencias.bat
"""

import tkinter as tk
from tkinter import messagebox, ttk

from core import licencia


class LicenciasApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AresaNest - Generador de Licencias")
        self.geometry("480x560")
        self.resizable(False, False)
        self.configure(bg="#f2f3f5")
        try:
            self.iconbitmap("static/icono.ico")
        except Exception:
            pass

        self._build_ui()
        self._refresh_status()

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"),
                        background="#f2f3f5", foreground="#3a4046")
        style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"),
                        background="#f2f3f5", foreground="#3a4046")
        style.configure("Field.TLabel", background="#f2f3f5",
                        foreground="#333333")
        style.configure("Key.TLabel", font=("Consolas", 10),
                        background="#ffffff", foreground="#1a1a1a",
                        borderwidth=1, relief="solid", padding=8)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

        pad = {"padx": 16, "pady": 4}

        ttk.Label(self, text="AresaNest", style="Title.TLabel").pack(anchor="w", **pad)
        ttk.Label(self, text="Generador de claves de licencia",
                  style="Field.TLabel").pack(anchor="w", **pad)

        ttk.Separator(self).pack(fill="x", padx=16, pady=8)

        ttk.Label(self, text="Generar licencia", style="Section.TLabel").pack(anchor="w", **pad)

        form = ttk.Frame(self)
        form.pack(fill="x", padx=16)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Cliente:", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        self.nombre = ttk.Entry(form, width=30)
        self.nombre.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(form, text="D\u00edas de vigencia:", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        self.dias = ttk.Entry(form, width=12)
        self.dias.insert(0, "3650")
        self.dias.grid(row=1, column=1, sticky="w", pady=3)

        self.btn_generar = ttk.Button(self, text="Generar clave", style="Accent.TButton",
                                      command=self._generar)
        self.btn_generar.pack(fill="x", padx=16, pady=6)

        ttk.Label(self, text="Clave generada:", style="Field.TLabel").pack(anchor="w", **pad)
        self.clave_var = tk.StringVar()
        clave_label = ttk.Label(self, textvariable=self.clave_var, style="Key.TLabel",
                                wraplength=430)
        clave_label.pack(fill="x", padx=16)
        ttk.Button(self, text="Copiar al portapapeles", command=self._copiar).pack(fill="x", padx=16, pady=6)

        ttk.Separator(self).pack(fill="x", padx=16, pady=8)

        ttk.Label(self, text="Estado de esta computadora", style="Section.TLabel").pack(anchor="w", **pad)
        self.estado_var = tk.StringVar()
        estado_label = ttk.Label(self, textvariable=self.estado_var, style="Field.TLabel",
                                 wraplength=430)
        estado_label.pack(anchor="w", padx=16, pady=4)

        form2 = ttk.Frame(self)
        form2.pack(fill="x", padx=16)
        form2.columnconfigure(1, weight=1)
        ttk.Label(form2, text="Clave para activar:", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        self.clave_activar = ttk.Entry(form2, width=30)
        self.clave_activar.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(form2, text="Activar en esta PC", command=self._activar).grid(row=1, column=1, sticky="w", pady=3)

    def _generar(self):
        name = self.nombre.get().strip()
        if not name:
            messagebox.showwarning("Falta el cliente",
                                   "Ingres\u00e1 el nombre del cliente.")
            return
        try:
            days = int(self.dias.get().strip() or "3650")
        except ValueError:
            days = 3650
        key = licencia.generate_key(name, days)
        self.clave_var.set(key)
        self.btn_generar.focus_set()

    def _copiar(self):
        key = self.clave_var.get()
        if not key:
            return
        self.clipboard_clear()
        self.clipboard_append(key)
        self.title("AresaNest - Generador de Licencias (clave copiada)")

    def _refresh_status(self):
        estado = licencia.status()
        if estado["status"] == "licensed":
            self.estado_var.set(
                f"Licencia activa para: {estado['licensed_to']} "
                f"({estado['days_left']} d\u00edas restantes).")
        elif estado["status"] == "trial":
            self.estado_var.set(
                f"Periodo de prueba: {estado['days_left']} d\u00edas restantes.")
        else:
            self.estado_var.set("Prueba vencida o sin licencia.")

    def _activar(self):
        key = self.clave_activar.get().strip()
        if not key:
            messagebox.showwarning("Falta la clave", "Ingres\u00e1 la clave.")
            return
        ok, msg = licencia.activate(key)
        if ok:
            messagebox.showinfo("Licencia activada", msg)
            self.clave_activar.delete(0, tk.END)
            self._refresh_status()
        else:
            messagebox.showerror("Clave inv\u00e1lida", msg)


if __name__ == "__main__":
    LicenciasApp().mainloop()
