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
SCRAPER_KEY = "3388267b140bf86c58e9ab0c2057c124"
ML_CLIENT_ID = "5415799706798482"
ML_CLIENT_SECRET = "GIPTdLAoQf4CKVycmLCr9WhAeV4sA2Pq"

# Cache do token ML
ml_token_cache = {"token": None}

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

def get_ml_token():
    """Obtem token de acesso da API oficial do ML"""
    try:
        if ml_token_cache["token"]:
            return ml_token_cache["token"]
        r = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": ML_CLIENT_ID,
                "client_secret": ML_CLIENT_SECRET
            },
            timeout=10
        )
        data = r.json()
        if "access_token" in data:
            ml_token_cache["token"] = data["access_token"]
            return data["access_token"]
    except Exception as e:
        print("ML token erro:", e)
    return None

def extrair_item_id_ml(link):
    """Extrai o ID do produto ML do link"""
    # Remove tudo depois do # primeiro
    link_limpo = link.split('#')[0]
    # Tenta pegar MLB seguido de numeros
    match = re.search(r'MLB[-_]?(\d+)', link_limpo, re.IGNORECASE)
    if match:
        return f"MLB{match.group(1)}"
    # Tenta pegar ID do formato produto.mercadolivre.com.br/MLB-XXXXXXXXX
    match2 = re.search(r'/(MLB-\d+)', link_limpo, re.IGNORECASE)
    if match2:
        return match2.group(1).replace('-', '')
    return None

def extrair_dados_ml_api(link):
    """Usa API oficial do ML para pegar dados do produto"""
    nome = ""
    imagem = ""
    preco = ""
    try:
        token = get_ml_token()
        if not token:
            return nome, imagem, preco

        # Tenta pegar item_id do link
        item_id = extrair_item_id_ml(link)

        # Se link tem /p/ é uma pagina de catalogo
        if "/p/" in link or not item_id:
            # Extrai ID do catalogo
            match = re.search(r'/p/(MLB\w+)', link, re.IGNORECASE)
            if match:
                catalog_id = match.group(1)
                # Busca via catalogo
                r = requests.get(
                    f"https://api.mercadolibre.com/products/{catalog_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10
                )
                data = r.json()
                if "name" in data:
                    nome = data["name"][:100]
                if "pictures" in data and data["pictures"]:
                    imagem = data["pictures"][0].get("url", "")
                # Busca preco via search
                r2 = requests.get(
                    f"https://api.mercadolibre.com/products/{catalog_id}/items",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10
                )
                data2 = r2.json()
                if "results" in data2 and data2["results"]:
                    item_id = data2["results"][0]

        if item_id and not nome:
            # Busca dados do item especifico
            r = requests.get(
                f"https://api.mercadolibre.com/items/{item_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            data = r.json()
            if "title" in data:
                nome = data["title"][:100]
            if "pictures" in data and data["pictures"]:
                imagem = data["pictures"][0].get("url", "")
            if "price" in data:
                preco = str(data["price"]).replace(".", ",")

    except Exception as e:
        print("ML API erro:", e)

    return nome, imagem, preco

def extrair_com_scraperapi(link, plataforma=""):
    """Usa ScraperAPI — render=true apenas para Amazon"""
    try:
        render = "true" if plataforma == "amazon" else "false"
        url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={link}&render={render}"
        r = requests.get(url, timeout=60)
        return r.text
    except Exception as e:
        print("ScraperAPI erro:", e)
        return None

def extrair_dados_produto(link, plataforma):
    nome = ""
    imagem = ""
    preco = ""

    try:
        # Para ML usa API oficial primeiro
        if plataforma == "mercadolivre":
            nome, imagem, preco = extrair_dados_ml_api(link)
            if nome:
                return nome, imagem, preco

        # Para Amazon usa ScraperAPI com render=true
        if plataforma == "amazon":
            html = extrair_com_scraperapi(link, plataforma)
        else:
            # Tenta primeiro sem ScraperAPI
            html = None
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept-Language": "pt-BR,pt;q=0.9",
                }
                r = requests.get(link, headers=headers, timeout=8)
                if r.status_code == 200:
                    html = r.text
            except:
                pass
            if not html or len(html) < 1000:
                html = extrair_com_scraperapi(link, plataforma)

        if not html:
            return nome, imagem, preco

        soup = BeautifulSoup(html, 'html.parser')

        img_tag = soup.find("meta", property="og:image")
        if img_tag and img_tag.get("content"):
            imagem = img_tag["content"]

        title_tag = soup.find("meta", property="og:title")
        if title_tag and title_tag.get("content"):
            nome = title_tag["content"].strip()

        if not imagem:
            if plataforma == "amazon":
                img = soup.find("img", {"id": "landingImage"}) or soup.find("img", {"id": "imgBlkFront"})
                if img and img.get("src") and "http" in img.get("src", ""):
                    imagem = img["src"]
                if not imagem:
                    img = soup.find("img", {"data-old-hires": True})
                    if img:
                        imagem = img["data-old-hires"]
            elif plataforma == "shopee":
                img = soup.find("meta", {"name": "twitter:image"})
                if img and img.get("content"):
                    imagem = img["content"]

        if nome:
            nome = re.sub(r'\s*[:|]\s*Amazon.*$', '', nome)
            nome = re.sub(r'\s*[:|]\s*Mercado Livre.*$', '', nome)
            nome = re.sub(r'\s*[:|]\s*Shopee.*$', '', nome)
            nome = nome[:100]

        if plataforma == "amazon":
            preco_tag = soup.find("span", {"class": "a-price-whole"})
            if preco_tag:
                preco_frac = soup.find("span", {"class": "a-price-fraction"})
                preco = preco_tag.text.strip().replace('.', '').replace(',', '')
                if preco_frac:
                    preco = preco + ',' + preco_frac.text.strip()

        if not preco:
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
