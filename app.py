import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, g, send_from_directory, abort
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "clave_secreta"
DATABASE = "inventario_sena.db"

# ==========================================
# CONEXIÓN A LA BASE DE DATOS
# ==========================================
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

# ==========================================
# INICIALIZAR BD (SE EJECUTA SIEMPRE)
# ==========================================
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        # Tabla usuarios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE,
                clave TEXT
            )
        """)

        # Crear admin por defecto
        cursor.execute("SELECT * FROM usuarios WHERE usuario = 'admin'")
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO usuarios (usuario, clave) VALUES (?, ?)",
                ("admin", generate_password_hash("1234"))
            )

        # Tabla equipos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equipos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                placa_sena TEXT,
                marca TEXT,
                modelo TEXT,
                serial TEXT,
                procesador TEXT,
                ram TEXT,
                almacenamiento TEXT,
                estado TEXT
            )
        """)

        conn.commit()

# Ejecutar init_db SIEMPRE (PC + Render)
init_db()

# ==========================================
# LOGIN
# ==========================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("username") or request.form.get("usuario")
        clave = request.form.get("password") or request.form.get("clave")

        if not usuario or not clave:
            return render_template("login.html", error="Por favor completa usuario y contraseña")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
        user = cursor.fetchone()

        if user and check_password_hash(user[2], clave):
            session["admin"] = True
            session["usuario"] = usuario
            return redirect("/admin")

        return render_template("login.html", error="Credenciales incorrectas")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ==========================================
# INDEX PÚBLICO
# ==========================================
@app.route("/")
def index_publico():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM equipos ORDER BY id DESC")
    equipos = cursor.fetchall()
    return render_template("index_publico.html", equipos=equipos)

# ==========================================
# INDEX ADMIN
# ==========================================
@app.route("/admin")
def index_admin():
    if not session.get("admin"):
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM equipos ORDER BY id ASC")
    equipos = cursor.fetchall()
    return render_template("index_admin.html", equipos=equipos)

# ==========================================
# AGREGAR EQUIPO
# ==========================================
@app.route("/agregar", methods=["GET", "POST"])
def agregar():
    if not session.get("admin"):
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        datos = (
            request.form["placa_sena"],
            request.form["marca"],
            request.form["modelo"],
            request.form["serial"],
            request.form["procesador"],
            request.form["ram"],
            request.form["almacenamiento"],
            request.form["estado"]
        )

        cursor.execute("""
            INSERT INTO equipos (placa_sena, marca, modelo, serial, procesador, ram, almacenamiento, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, datos)

        conn.commit()
        return redirect("/admin")

    return render_template("agregar.html")

# ==========================================
# EDITAR EQUIPO
# ==========================================
@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar(id):
    if not session.get("admin"):
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        datos = (
            request.form["placa_sena"],
            request.form["marca"],
            request.form["modelo"],
            request.form["serial"],
            request.form["procesador"],
            request.form["ram"],
            request.form["almacenamiento"],
            request.form["estado"],
            id
        )

        cursor.execute("""
            UPDATE equipos SET placa_sena=?, marca=?, modelo=?, serial=?, 
                procesador=?, ram=?, almacenamiento=?, estado=? 
            WHERE id=?
        """, datos)

        conn.commit()
        return redirect("/admin")

    cursor.execute("SELECT * FROM equipos WHERE id=?", (id,))
    equipo = cursor.fetchone()

    return render_template("editar.html", equipo=equipo)

# ==========================================
# ELIMINAR EQUIPO
# ==========================================
@app.route("/eliminar/<int:id>")
def eliminar(id):
    if not session.get("admin"):
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM equipos WHERE id=?", (id,))
    conn.commit()

    return redirect("/admin")

# ==========================================
# BUSCAR (ADMIN Y PÚBLICO)
# ==========================================
@app.route("/buscar", methods=["GET"])
def buscar():
    conn = get_db()
    cursor = conn.cursor()

    filtro = request.args.get("filtro", "")
    valor = f"%{filtro}%"

    cursor.execute("""
        SELECT * FROM equipos 
        WHERE placa_sena LIKE ? OR marca LIKE ? OR modelo LIKE ? OR serial LIKE ?
        OR procesador LIKE ? OR ram LIKE ? OR almacenamiento LIKE ? OR estado LIKE ?
    """, (valor, valor, valor, valor, valor, valor, valor, valor))

    equipos = cursor.fetchall()

    if session.get("admin"):
        return render_template("index_admin.html", equipos=equipos)
    else:
        return render_template("index_publico.html", equipos=equipos)

# ==========================================
# ARCHIVOS / DOCUMENTOS (si existen)
# ==========================================
@app.route('/descargar_documento/<int:id>')
def descargar_documento(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(equipos)")
    cols = [r[1] for r in cursor.fetchall()]

    if 'documento' not in cols:
        return render_template('no_documento.html', id=id), 404

    cursor.execute("SELECT documento FROM equipos WHERE id=?", (id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        return render_template('no_documento.html', id=id), 404

    filename = row[0]
    docs_dir = os.path.join(app.root_path, 'static', 'docs')

    if not os.path.exists(os.path.join(docs_dir, filename)):
        return render_template('no_documento.html', id=id), 404

    return send_from_directory(docs_dir, filename, as_attachment=True)

# ==========================================
# INICIO DE APP (SOLO LOCAL)
# ==========================================
if __name__ == "__main__":
    app.run(debug=True)
