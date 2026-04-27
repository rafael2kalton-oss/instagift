from flask import Flask, render_template, request, jsonify, session
import sqlite3
import os
import uuid

app = Flask(__name__)
app.secret_key = "instagift2026"

DB = "banco.db"

def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS listas (
            id TEXT PRIMARY KEY,
            nome TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lista_id TEXT,
            nome TEXT,
            preco TEXT,
            imagem_url TEXT,
            link_compra TEXT,
            reservado INTEGER DEFAULT 0
        )
    """)
    con.commit()
    con.close()

init_db()

# Página principal — criar story
@app.route("/")
def index():
    return render_template("criar_story.html")

# Criar lista de presentes (loja cadastra)
@app.route("/admin")
def admin():
    return render_template("admin.html")

# API — salvar lista
@app.route("/api/lista", methods=["POST"])
def criar_lista():
    data = request.json
    lista_id = str(uuid.uuid4())[:8]
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("INSERT INTO listas (id, nome) VALUES (?, ?)", (lista_id, data["nome"]))
    for p in data["produtos"]:
        cur.execute("""
            INSERT INTO produtos (lista_id, nome, preco, imagem_url, link_compra)
            VALUES (?, ?, ?, ?, ?)
        """, (lista_id, p["nome"], p["preco"], p["imagem_url"], p["link_compra"]))
    con.commit()
    con.close()
    return jsonify({"lista_id": lista_id, "link": f"/vitrine/{lista_id}"})

# API — buscar produtos da lista
@app.route("/api/lista/<lista_id>")
def get_lista(lista_id):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT nome FROM listas WHERE id = ?", (lista_id,))
    lista = cur.fetchone()
    cur.execute("SELECT id, nome, preco, imagem_url, link_compra, reservado FROM produtos WHERE lista_id = ?", (lista_id,))
    produtos = cur.fetchall()
    con.close()
    if not lista:
        return jsonify({"erro": "Lista não encontrada"}), 404
    return jsonify({
        "nome": lista[0],
        "produtos": [
            {"id": p[0], "nome": p[1], "preco": p[2], "imagem_url": p[3], "link_compra": p[4], "reservado": p[5]}
            for p in produtos
        ]
    })

# API — reservar produto
@app.route("/api/reservar/<int:produto_id>", methods=["POST"])
def reservar(produto_id):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT reservado FROM produtos WHERE id = ?", (produto_id,))
    p = cur.fetchone()
    if not p:
        return jsonify({"erro": "Produto não encontrado"}), 404
    if p[0]:
        return jsonify({"erro": "Já reservado"}), 400
    cur.execute("UPDATE produtos SET reservado = 1 WHERE id = ?", (produto_id,))
    con.commit()
    con.close()
    return jsonify({"ok": True})

# Vitrine pública
@app.route("/vitrine/<lista_id>")
def vitrine(lista_id):
    return render_template("vitrine.html", lista_id=lista_id)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)