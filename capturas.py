"""Genera las capturas de pantalla de la interfaz (requiere playwright con Chromium)."""
import logging
import os
import tempfile
import threading

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from sge import create_app

logging.getLogger("werkzeug").setLevel(logging.ERROR)
PUERTO = 5078
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capturas")
os.makedirs(SALIDA, exist_ok=True)

app = create_app(os.path.join(tempfile.mkdtemp(), "demo.db"))
servidor = make_server("127.0.0.1", PUERTO, app, threaded=True)
threading.Thread(target=servidor.serve_forever, daemon=True).start()

with sync_playwright() as p:
    nav = p.chromium.launch()
    pag = nav.new_page(viewport={"width": 1120, "height": 700}, device_scale_factor=1.5)
    pag.goto(f"http://127.0.0.1:{PUERTO}/")
    pag.wait_for_selector("#cursos tr")

    def boton(codigo):
        return pag.locator(f'#cursos tr:has(td b:text-is("{codigo}")) button.matricular')

    # Ana Torres: dos matrículas correctas y un cruce de horario
    pag.select_option("#estudiante", label="E001 · Ana Torres")
    pag.wait_for_selector("#cursos tr")
    boton("IS201").click(); pag.wait_for_selector("#aviso.ok")
    boton("IS203").click(); pag.wait_for_selector("#mias tr:nth-child(2)")
    boton("IS105").click(); pag.wait_for_selector("#aviso.error")
    pag.wait_for_timeout(300)
    pag.screenshot(path=os.path.join(SALIDA, "captura_1_ana.png"), full_page=True)

    # Ana Torres: prerrequisito pendiente
    boton("IS202").click(); pag.wait_for_selector("#aviso.error")
    pag.wait_for_timeout(300)
    pag.screenshot(path=os.path.join(SALIDA, "captura_2_prerrequisito.png"), full_page=True)

    # Elena Vega: saldo pendiente
    pag.select_option("#estudiante", label="E005 · Elena Vega (saldo pendiente)")
    pag.wait_for_selector("#cursos tr")
    boton("IS204").click(); pag.wait_for_selector("#aviso.error")
    pag.wait_for_timeout(300)
    pag.screenshot(path=os.path.join(SALIDA, "captura_3_saldo.png"), full_page=True)
    nav.close()
servidor.shutdown()
print("capturas listas en", SALIDA)
