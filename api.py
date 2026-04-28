from flask import Flask, render_template, request, jsonify
import sqlite3
import uuid
import re
import urllib.request
import urllib.parse

app = Flask(__name__)

DB = "banco.db"

# IDs de afiliado
AMAZON_TAG = "instagift20-20"
ML_ID = "DaniloBasilio40"

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
            link_original TEXT,
            link_afiliado TEXT,
            plataforma TEXT,
            reservado INTEGER DEFAULT 0
        )
    """)
    con.commit()
    con.close()

init_db()

def detectar_plataforma(link):
    if "amazon.com.br" in link or "amzn.to" in link:
        return "amazon"
    elif "mercadolivre.com.br" in link or "mercadolibre.com" in link or "meli.com" in link:
        return "mercadolivre"
    elif "shopee.com.br" in link:
        return "shopee"
    return "outro"

def limpar_e_injetar(link, plataforma):
    try:
        if plataforma == "amazon":
            # Remove tag existente e injeta o nosso
            link = re.sub(r'[?&]tag=[^&]+', '', link)
            if '?' in link:
                link = link + '&tag=' + AMAZON_TAG
            else:
                link = link + '?tag=' + AMAZON_TAG
            return link

        elif plataforma == "mercadolivre":
            # ML usa matt_tool e partner
            link = re.sub(r'[?&]matt_tool=[^&]+', '', link)
            link = re.sub(r'[?&]partner_id=[^&]+', '', link)
            if '?' in link:
                link = link + '&matt_tool=97&partner_id=' + ML_ID
            else:
                link = link + '?matt_tool=97&partner_id=' + ML_ID
            return link

        elif plataforma == "shopee":
            # Shopee — mantém link limpo por enquanto
            return link

    except:
        return link
    return link

def extrair_dados_produto(link, plataforma):
    """Extrai título e imagem do produto via scraping simples"""
    nome = "Produto"
    imagem = ""
    preco = ""

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(link, headers=headers)
        response = urllib.request.urlopen(req, timeout=8)
        html = response.read().decode('utf-8', errors='ignore')

        # Extrai título
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            nome = title_match.group(1).strip()
            # Limpa o nome
            nome = re.sub(r'\s*[:|]\s*Amazon.*$', '', nome)
            nome = re.sub(r'\s*[:|]\s*Mercado Livre.*$', '', nome)
            nome = re.sub(r'\s*[:|]\s*Shopee.*$', '', nome)
            nome = nome[:80]  # Limita tamanho

        # Extrai imagem og
        img_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if img_match:
            imagem = img_match.group(1)

        # Extrai preço
        preco_match = re.search(r'R\$\s*[\d.,]+', html)
        if preco_match:
            preco = preco_match.group(0).replace('R$', '').strip()

    except Exception as e:
        print("Erro scraping:", e)

    return nome, imagem, preco

# ── ROTAS ──

@app.route("/")
def index():
    return render_template("criar_story.html")

@app.route("/criar-lista")
def criar_lista_page():
    lista_id = str(uuid.uuid4())[:8]
    return render_template("criar_lista.html", lista_id=lista_id)

@app.route("/lista/<lista_id>")
def lista_page(lista_id):
    return render_template("criar_lista.html", lista_id=lista_id)

@app.route("/api/adicionar-produto", methods=["POST"])
def adicionar_produto():
    data = request.json
    lista_id = data.get("lista_id")
    link = data.get("link", "").strip()
    nome_manual = data.get("nome", "")

    if not lista_id or not link:
        return jsonify({"erro": "Dados incompletos"}), 400

    plataforma = detectar_plataforma(link)
    link_afiliado = limpar_e_injetar(link, plataforma)
    nome, imagem, preco = extrair_dados_produto(link_afiliado, plataforma)

    if nome_manual:
        nome = nome_manual

    con = sqlite3.connect(DB)
    cur = con.cursor()

    # Cria lista se não existir
    cur.execute("SELECT id FROM listas WHERE id = ?", (lista_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO listas (id, nome) VALUES (?, ?)", (lista_id, "Minha Lista"))

    cur.execute("""
        INSERT INTO produtos (lista_id, nome, preco, imagem_url, link_original, link_afiliado, plataforma)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (lista_id, nome, preco, imagem, link, link_afiliado, plataforma))
    con.commit()
    produto_id = cur.lastrowid
    con.close()

    return jsonify({
        "ok": True,
        "produto": {
            "id": produto_id,
            "nome": nome,
            "preco": preco,
            "imagem_url": imagem,
            "link_afiliado": link_afiliado,
            "plataforma": plataforma
        }
    })

@app.route("/api/produtos/<lista_id>")
def get_produtos(lista_id):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT id, nome, preco, imagem_url, link_afiliado, plataforma, reservado FROM produtos WHERE lista_id = ?", (lista_id,))
    produtos = cur.fetchall()
    con.close()
    return jsonify([{
        "id": p[0], "nome": p[1], "preco": p[2],
        "imagem_url": p[3], "link_afiliado": p[4],
        "plataforma": p[5], "reservado": p[6]
    } for p in produtos])

@app.route("/api/remover-produto/<int:produto_id>", methods=["DELETE"])
def remover_produto(produto_id):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
    con.commit()
    con.close()
    return jsonify({"ok": True})

@app.route("/vitrine/<lista_id>")
def vitrine(lista_id):
    return render_template("vitrine.html", lista_id=lista_id)

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

if __name__ == "__main__":
    app.run(debug=True)
