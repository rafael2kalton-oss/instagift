from flask import Flask, render_template, request, jsonify
import uuid
import re

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_OK = True
except:
    REQUESTS_OK = False

app = Flask(__name__)

SUPABASE_URL = "https://xmivfkpywjbrcrkniqbu.supabase.co"
SUPABASE_KEY = "sb_secret_0M-YowSnhrciNuzmJMS7AQ_QwA9GUjz"
HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

AMAZON_TAG = "instagift20-20"
ML_ID = "DaniloBasilio40"

HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://www.mercadolivre.com.br/",
}

def sb_get(tabela, filtro=None):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}"
    if filtro:
        url += f"?{filtro}"
    r = requests.get(url, headers=HEADERS_SB)
    return r.json()

def sb_post(tabela, dados):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}"
    r = requests.post(url, headers=HEADERS_SB, json=dados)
    return r.json()

def sb_patch(tabela, filtro, dados):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}"
    r = requests.patch(url, headers=HEADERS_SB, json=dados)
    return r.json()

def sb_delete(tabela, filtro):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}"
    r = requests.delete(url, headers=HEADERS_SB)
    return r.status_code

def detectar_plataforma(link):
    if "amazon.com.br" in link or "amzn.to" in link:
        return "amazon"
    elif "mercadolivre.com.br" in link or "mercadolibre.com" in link or "meli.com" in link or "produto.mercadolivre" in link:
        return "mercadolivre"
    elif "shopee.com.br" in link:
        return "shopee"
    return "outro"

def limpar_e_injetar(link, plataforma):
    try:
        if plataforma == "amazon":
            link = re.sub(r'[?&]tag=[^&]+', '', link)
            link = link + ('&' if '?' in link else '?') + 'tag=' + AMAZON_TAG
        elif plataforma == "mercadolivre":
            link = re.sub(r'[?&]matt_tool=[^&]+', '', link)
            link = re.sub(r'[?&]partner_id=[^&]+', '', link)
            link = link + ('&' if '?' in link else '?') + 'matt_tool=97&partner_id=' + ML_ID
    except:
        pass
    return link

def resolver_link_ml(link):
    """Se o link tem /p/ tenta seguir o redirecionamento para pegar o link real do produto"""
    try:
        if "/p/" in link:
            session = requests.Session()
            session.headers.update(HEADERS_WEB)
            response = session.get(link, timeout=10, allow_redirects=True)
            # Pega a URL final após redirecionamentos
            url_final = response.url
            if "/p/" not in url_final:
                return url_final
            # Tenta achar o link do primeiro produto na pagina
            soup = BeautifulSoup(response.text, 'html.parser')
            # Procura link de variacao do produto
            variacao = soup.find("a", {"class": "ui-pdp-thumbnail"})
            if not variacao:
                variacao = soup.find("a", href=re.compile(r'/MLB-\d+'))
            if variacao and variacao.get("href"):
                return variacao["href"]
    except:
        pass
    return link

def extrair_dados_produto(link, plataforma):
    nome = ""
    imagem = ""
    preco = ""
    try:
        if REQUESTS_OK:
            # Para ML com /p/ tenta resolver o link primeiro
            if plataforma == "mercadolivre" and "/p/" in link:
                link = resolver_link_ml(link)

            session = requests.Session()
            session.headers.update(HEADERS_WEB)
            response = session.get(link, timeout=10, allow_redirects=True)
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            # Tenta og:image
            img_tag = soup.find("meta", property="og:image")
            if img_tag and img_tag.get("content"):
                imagem = img_tag["content"]

            # Tenta og:title
            title_tag = soup.find("meta", property="og:title")
            if title_tag and title_tag.get("content"):
                nome = title_tag["content"].strip()

            # Fallbacks por plataforma
            if not imagem:
                if plataforma == "amazon":
                    img = soup.find("img", {"id": "landingImage"}) or soup.find("img", {"id": "imgBlkFront"})
                    if img and img.get("src"):
                        imagem = img["src"]
                elif plataforma == "mercadolivre":
                    # Tenta pegar imagem do ML de outras formas
                    img = soup.find("img", {"class": "ui-pdp-image"})
                    if not img:
                        img = soup.find("figure", {"class": "ui-pdp-gallery__figure"})
                        if img:
                            img = img.find("img")
                    if img and img.get("src") and "http" in img.get("src", ""):
                        imagem = img["src"]
                    elif img and img.get("data-zoom"):
                        imagem = img["data-zoom"]
                elif plataforma == "shopee":
                    img = soup.find("meta", {"name": "twitter:image"})
                    if img and img.get("content"):
                        imagem = img["content"]

            # Limpa nome
            if nome:
                nome = re.sub(r'\s*[:|]\s*Amazon.*$', '', nome)
                nome = re.sub(r'\s*[:|]\s*Mercado Livre.*$', '', nome)
                nome = re.sub(r'\s*[:|]\s*Shopee.*$', '', nome)
                nome = nome[:100]

            # Extrai preco
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

@app.route("/api/preview-produto", methods=["POST"])
def preview_produto():
    data = request.json
    link = data.get("link", "").strip()
    if not link:
        return jsonify({"ok": False}), 400
    plataforma = detectar_plataforma(link)
    link_afiliado = limpar_e_injetar(link, plataforma)
    nome, imagem, preco = extrair_dados_produto(link_afiliado, plataforma)
    if nome or imagem:
        return jsonify({"ok": True, "nome": nome, "imagem": imagem, "preco": preco})
    return jsonify({"ok": False})

@app.route("/api/adicionar-produto", methods=["POST"])
def adicionar_produto():
    data = request.json
    lista_id = data.get("lista_id")
    link = data.get("link", "").strip()
    nome_manual = data.get("nome", "").strip()
    imagem_manual = data.get("imagem", "").strip()
    preco_manual = data.get("preco", "").strip()

    if not lista_id or not link:
        return jsonify({"erro": "Dados incompletos"}), 400

    plataforma = detectar_plataforma(link)
    link_afiliado = limpar_e_injetar(link, plataforma)
    nome_auto, imagem_auto, preco_auto = extrair_dados_produto(link_afiliado, plataforma)

    nome = nome_manual if nome_manual else nome_auto
    imagem = imagem_manual if imagem_manual else imagem_auto
    preco = preco_manual if preco_manual else preco_auto

    if not nome:
        nome = "Produto"

    lista = sb_get("listas", f"id=eq.{lista_id}")
    if not lista:
        sb_post("listas", {"id": lista_id, "nome": "Minha Lista"})

    resultado = sb_post("produtos", {
        "lista_id": lista_id,
        "nome": nome,
        "preco": preco,
        "imagem_url": imagem,
        "link_original": link,
        "link_afiliado": link_afiliado,
        "plataforma": plataforma,
        "reservado": 0
    })

    if isinstance(resultado, list) and len(resultado) > 0:
        p = resultado[0]
        return jsonify({
            "ok": True,
            "produto": {
                "id": p["id"],
                "nome": p["nome"],
                "preco": p.get("preco", ""),
                "imagem_url": p.get("imagem_url", ""),
                "link_afiliado": p.get("link_afiliado", ""),
                "plataforma": p.get("plataforma", "")
            }
        })
    return jsonify({"erro": "Erro ao salvar produto"}), 500

@app.route("/api/produtos/<lista_id>")
def get_produtos(lista_id):
    produtos = sb_get("produtos", f"lista_id=eq.{lista_id}&order=id.asc")
    if isinstance(produtos, list):
        return jsonify(produtos)
    return jsonify([])

@app.route("/api/remover-produto/<int:produto_id>", methods=["DELETE"])
def remover_produto(produto_id):
    sb_delete("produtos", f"id=eq.{produto_id}")
    return jsonify({"ok": True})

@app.route("/vitrine/<lista_id>")
def vitrine(lista_id):
    return render_template("vitrine.html", lista_id=lista_id)

@app.route("/api/reservar/<int:produto_id>", methods=["POST"])
def reservar(produto_id):
    produtos = sb_get("produtos", f"id=eq.{produto_id}")
    if not produtos or not isinstance(produtos, list):
        return jsonify({"erro": "Produto nao encontrado"}), 404
    if produtos[0].get("reservado"):
        return jsonify({"erro": "Ja reservado"}), 400
    sb_patch("produtos", f"id=eq.{produto_id}", {"reservado": 1})
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True)
