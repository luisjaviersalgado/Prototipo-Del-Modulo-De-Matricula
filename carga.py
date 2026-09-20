"""Prueba de carga del prototipo con datos del tamaño del piloto (500 estudiantes).

Fase A: 500 estudiantes consultan cursos, se matriculan en 5 cursos cada uno y consultan su matrícula.
Fase B: 500 estudiantes piden a la vez un curso con solo 100 cupos.
Al final se verifica en la base de datos que ningún curso quedó por encima de su cupo.

Uso:  python carga.py [--repeticiones 3] [--hilos 50] [--salida resultados_carga.json]
"""
import argparse
import http.client
import json
import logging
import os
import platform
import random
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from werkzeug.serving import make_server

from sge import create_app, db

PUERTO = 5077
logging.getLogger("werkzeug").setLevel(logging.ERROR)


def pedir(metodo, ruta, cuerpo=None):
    t0 = time.perf_counter()
    con = http.client.HTTPConnection("127.0.0.1", PUERTO, timeout=60)
    cabeceras = {"Content-Type": "application/json"} if cuerpo is not None else {}
    con.request(metodo, ruta, body=json.dumps(cuerpo) if cuerpo is not None else None, headers=cabeceras)
    r = con.getresponse()
    r.read()
    con.close()
    return r.status, (time.perf_counter() - t0) * 1000


def percentil(valores, p):
    orden = sorted(valores)
    k = max(0, min(len(orden) - 1, int(round(p / 100 * len(orden) + 0.5)) - 1))
    return orden[k]


def resumen(latencias):
    return {"n": len(latencias), "p50": round(statistics.median(latencias), 1),
            "p95": round(percentil(latencias, 95), 1), "p99": round(percentil(latencias, 99), 1),
            "max": round(max(latencias), 1)}


def una_corrida(n_est, hilos, por_est, semilla):
    rnd = random.Random(semilla)
    carpeta = tempfile.mkdtemp()
    ruta_db = os.path.join(carpeta, "carga.db")
    db.init_db(ruta_db)
    db.seed_carga(ruta_db, n_estudiantes=n_est)
    app = create_app(ruta_db)
    servidor = make_server("127.0.0.1", PUERTO, app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()

    lat = {"listar_cursos": [], "matricular": [], "consultar_matriculas": []}
    estados = {"matricular": {}}
    lock = threading.Lock()
    con = db.connect(ruta_db)
    ids_cursos = [r["id"] for r in con.execute("SELECT id FROM cursos WHERE codigo LIKE 'C%' ORDER BY id")]
    ids_est = [r["id"] for r in con.execute("SELECT id FROM estudiantes ORDER BY id")]
    id_pico = con.execute("SELECT id FROM cursos WHERE codigo = 'PICO'").fetchone()["id"]

    def estudiante(eid):
        elegidos = rnd_local.sample(ids_cursos, por_est)
        s, ms = pedir("GET", f"/api/cursos?estudiante_id={eid}")
        with lock:
            lat["listar_cursos"].append(ms)
        for cid in elegidos:
            s, ms = pedir("POST", "/api/matriculas", {"estudiante_id": eid, "curso_id": cid})
            with lock:
                lat["matricular"].append(ms)
                estados["matricular"][s] = estados["matricular"].get(s, 0) + 1
        s, ms = pedir("GET", f"/api/estudiantes/{eid}/matriculas")
        with lock:
            lat["consultar_matriculas"].append(ms)

    rnd_local = rnd
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        list(pool.map(estudiante, ids_est))
    dur_a = time.perf_counter() - t0
    total_a = sum(len(v) for v in lat.values())

    # Fase B: pico sobre un curso con 100 cupos
    codigos_b = {}
    lat_b = []

    def pico(eid):
        s, ms = pedir("POST", "/api/matriculas", {"estudiante_id": eid, "curso_id": id_pico})
        with lock:
            lat_b.append(ms)
            codigos_b[s] = codigos_b.get(s, 0) + 1

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        list(pool.map(pico, ids_est))
    dur_b = time.perf_counter() - t0

    # Verificación de integridad directamente en la base de datos
    exceso = con.execute(
        """SELECT COUNT(*) FROM cursos c WHERE
           (SELECT COUNT(*) FROM matriculas m WHERE m.curso_id = c.id AND m.estado = 'ACTIVA') > c.cupo_maximo""").fetchone()[0]
    pico_ocupados = con.execute("SELECT COUNT(*) FROM matriculas WHERE curso_id = ? AND estado = 'ACTIVA'", (id_pico,)).fetchone()[0]
    creditos_excedidos = con.execute(
        """SELECT COUNT(*) FROM (SELECT m.estudiante_id, SUM(c.creditos) t FROM matriculas m JOIN cursos c ON c.id = m.curso_id
           WHERE m.estado = 'ACTIVA' GROUP BY m.estudiante_id HAVING t > 20)""").fetchone()[0]
    activas = con.execute("SELECT COUNT(*) FROM matriculas WHERE estado = 'ACTIVA'").fetchone()[0]
    con.close()
    servidor.shutdown()
    return {
        "fase_a": {"duracion_s": round(dur_a, 2), "solicitudes": total_a,
                   "solicitudes_por_s": round(total_a / dur_a, 1),
                   "listar_cursos": resumen(lat["listar_cursos"]),
                   "matricular": resumen(lat["matricular"]),
                   "consultar_matriculas": resumen(lat["consultar_matriculas"]),
                   "codigos_matricular": estados["matricular"]},
        "fase_b": {"duracion_s": round(dur_b, 2), "solicitudes": len(lat_b), "codigos": codigos_b,
                   "latencia": resumen(lat_b)},
        "integridad": {"cursos_sobre_cupo": exceso, "ocupados_curso_pico": pico_ocupados,
                       "estudiantes_sobre_20_creditos": creditos_excedidos, "matriculas_activas_total": activas},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estudiantes", type=int, default=500)
    ap.add_argument("--hilos", type=int, default=50)
    ap.add_argument("--por-estudiante", type=int, default=5)
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--salida", default="resultados_carga.json")
    a = ap.parse_args()
    corridas = []
    for i in range(a.repeticiones):
        print(f"Corrida {i + 1}/{a.repeticiones} ...", flush=True)
        c = una_corrida(a.estudiantes, a.hilos, a.por_estudiante, semilla=100 + i)
        corridas.append(c)
        print(json.dumps({"A": c["fase_a"]["matricular"], "B": c["fase_b"]["codigos"], "int": c["integridad"]}), flush=True)
    salida = {"entorno": {"python": platform.python_version(), "so": platform.platform(), "nucleos": os.cpu_count(),
                          "estudiantes": a.estudiantes, "hilos": a.hilos, "cursos_por_estudiante": a.por_estudiante},
              "corridas": corridas}
    with open(a.salida, "w", encoding="utf8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print("Resultados guardados en", a.salida)


if __name__ == "__main__":
    sys.exit(main())
