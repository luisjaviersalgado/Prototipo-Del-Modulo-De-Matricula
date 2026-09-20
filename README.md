# Prototipo del módulo de matrícula · EduTech Solutions

Prototipo funcional que valida las reglas del módulo de matrícula (hito H2) del Sistema de Gestión Educativa.
Está hecho con **Python 3.12, Flask y SQLite** para poder probarlo rápido. El diseño de producción del informe
usa Java, Spring Boot y PostgreSQL; las reglas y el modelo de datos son los mismos.

## Qué hace
- Lista cursos con cupos disponibles, horarios y prerrequisitos.
- Matricula y cancela, validando en este orden: pago al día, sin duplicados, prerrequisitos aprobados (nota ≥ 3,0),
  cupo, máximo de 20 créditos y cruce de horario.
- Guarda una bitácora de éxitos, rechazos y cancelaciones.
- Toda la validación y el guardado ocurren en una sola transacción, así que dos solicitudes simultáneas no ocupan el mismo cupo.

## Cómo ejecutarlo
```bash
python -m venv .venv
source .venv/bin/activate          # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                      # abre http://127.0.0.1:5000
```
La primera vez crea `sge.db` con datos de ejemplo (8 estudiantes y 14 cursos). Para probar los casos de la interfaz:
- **Ana Torres**: matricula Programación II y Bases de Datos I; al intentar Ética Profesional, se cruza el horario.
- **Elena Vega**: tiene saldo pendiente y no puede matricularse.
- **Bruno Díaz**: no tiene historial, así que los cursos con prerrequisitos se rechazan.

## Pruebas automáticas (26)
```bash
python -m unittest discover -s tests -v
```

## Prueba de carga (500 estudiantes)
```bash
python carga.py --repeticiones 3        # escribe resultados_carga.json
```
Los tiempos dependen de tu equipo; usa tus propios resultados en el informe.

## Capturas de pantalla (opcional)
```bash
pip install playwright && playwright install chromium
python capturas.py                      # escribe la carpeta capturas/
```

## Estructura
```
sge/__init__.py     API y rutas (Flask)
sge/matricula.py    reglas de negocio y transacciones
sge/db.py           esquema SQLite y datos de ejemplo
sge/static/         interfaz web
tests/              pruebas automáticas
carga.py            prueba de carga
capturas.py         capturas de la interfaz
```

## Cómo pasarlo a Java, Spring Boot y PostgreSQL
| En el prototipo | En producción |
|---|---|
| Rutas de Flask | `@RestController` con los mismos servicios |
| `sqlite3` | Spring Data JPA o `JdbcTemplate` |
| `BEGIN IMMEDIATE` | `@Transactional` y `SELECT ... FOR UPDATE` sobre la fila del curso antes de contar los cupos |
| Errores con código (`SIN_CUPO`...) | Excepciones de negocio con `@ControllerAdvice` |
| `unittest` | JUnit 5 y pruebas de concurrencia con varios hilos |
