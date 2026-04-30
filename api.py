from flask import Flask, render_template, request, jsonify
import uuid
import re
import os

from dotenv import load_dotenv
load_dotenv()

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_OK = True
except:
    REQUESTS_OK = False

app = Flask(__name__)

# ---------------- ENV ----------------

SUPABASE_URL = "https://xmivfkpywjbrcrkniqbu.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SCRAPER_KEY = os.getenv("SCRAPER_KEY")

if not SUPABASE_KEY:
    raise Exception("SUPABASE_KEY não definida no .env")

HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

AMAZON_TAG = "instagift20-20"
ML_ID = "DaniloBasilio40"

# ---------------- SUPABASE ----------------

def sb_get(tabela, filtro=None):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}"
    if filtro:
        url += f"?{filtro}"
    return requests.get(url, headers=HEADERS_SB).json()

def sb_post(tabela, dados):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}"
    return requests.post(url, headers=HEADERS_SB, json=dados).json()

def sb_patch(tabela, filtro, dados):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}"
    return requests.patch(url, headers=HEADERS_SB, json=dados).json()

def sb_delete(tabela, filtro):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}"
    return requests.delete(url, headers=HEADERS_SB).status_code

# ---------------- DETECÇÃO ----------------

def detectar_plataforma(link):
    link = link.lower()

    if "amazon.com.br" in link or "amzn.to" in link:
        return "amazon"

    elif (
        "mercadolivre.com.br" in link
        or "mercadolibre.com" in link
        or "meli.com" in link
        or "produto.mercadolivre.com.br" in link
        or "/p/" in link
    ):
        return "mercadolivre"

    elif "shopee.com.br" in link:
        return "shopee"

    return "outro"

# ---------------- LINK AFILIADO ----------------

def limpar_e_injetar(link, plataforma):
    try:
        if plataforma == "amazon":
            link = re.sub(r'[?&]tag=[^&]+', '', link)
            link += ('&' if '?' in link else '?') + 'tag=' + AMAZON_TAG

        elif plataforma == "mercadolivre":
            link = re.sub(r'[?&]matt_tool=[^&]+', '', link)
            link = re.sub(r'[?&]partner_id=[^&]+', '', link)
            link += ('&' if '?' in link else '?') + 'matt_tool=97&partner_id=' + ML_ID
    except:
        pass

    return link

# ---------------- ML ID ----------------

def extrair_item_id_ml(link):
    try:
        link_limpo = link.split('#')[0].split('?')[0]

        match = re.search(r'(MLB[-_]?\d+)', link_limpo, re.IGNORECASE)
        if match:
            return match.group(1).replace('-', '').replace('_', '')

        match2 = re.search(r'MLB(\d+)', link_limpo, re.IGNORECASE)
        if match2:
            return f"MLB{match2.group(1)}"

    except Exception as e:
        print("Erro ID ML:", e)

    return None

# ---------------- ML API ----------------

def extrair_dados_ml_api(link):
    nome = ""
    imagem = ""
    preco = ""

    try:
        item_id = extrair_item_id_ml(link)

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }

        # catálogo
        if "/p/" in link or not item_id:
            match = re.search(r'/p/(MLB\w+)', link, re.IGNORECASE)

            if match:
                catalog_id = match.group(1)

                try:
                    r = requests.get(
                        f"https://api.mercadolibre.com/products/{catalog_id}",
                        headers=headers,
                        timeout=10
                    )
                    data = r.json()

                    if "name" in data:
                        nome = data["name"][:100]

                    if "pictures" in data and data["pictures"]:
                        imagem = data["pictures"][0].get("url", "")

                    r2 = requests.get(
                        f"https://api.mercadolibre.com/products/{catalog_id}/items",
                        headers=headers,
                        timeout=10
                    )
                    data2 = r2.json()

                    if "results" in data2 and data2["results"]:
                        item_id = data2["results"][0]

                except Exception as e:
                    print("Erro catálogo ML:", e)

        # item direto
        if item_id:
            r = requests.get(
                f"https://api.mercadolibre.com/items/{item_id}",
                headers=headers,
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
        print("ML erro:", e)

    return nome, imagem, preco

# ---------------- SCRAPER ----------------

def extrair_com_scraperapi(link, plataforma=""):
    if not SCRAPER_KEY:
        return None

    try:
        render = "true" if plataforma == "amazon" else "false"
        url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={link}&render={render}"
        return requests.get(url, timeout=30).text
    except Exception as e:
        print("Scraper erro:", e)
        return None

# ---------------- EXTRAÇÃO ----------------

def extrair_dados_produto(link, plataforma):
    nome = ""
    imagem = ""
    preco = ""

    try:
        if plataforma == "mercadolivre":
            nome, imagem, preco = extrair_dados_ml_api(link)
            if nome:
                return nome, imagem, preco

        html = None

        try:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept-Language": "pt-BR"
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

        img = soup.find("meta", property="og:image")
        if img:
            imagem = img.get("content", "")

        title = soup.find("meta", property="og:title")
        if title:
            nome = title.get("content", "")[:100]

        preco_match = re.search(r'R\$\s*[\d.,]+', html)
        if preco_match:
            preco = preco_match.group(0).replace("R$", "").strip()

    except Exception as e:
        print("Erro geral:", e)

    return nome, imagem, preco

# ---------------- ROTAS ----------------

@app.route("/")
def index():
    return render_template("criar_story.html")

@app.route("/api/preview-produto", methods=["POST"])
def preview_produto():
    data = request.json
    link = data.get("link", "").strip()

    if not link:
        return jsonify({"ok": False}), 400

    plataforma = detectar_plataforma(link)
    link_afiliado = limpar_e_injetar(link, plataforma)

    nome, imagem, preco = extrair_dados_produto(link_afiliado, plataforma)

    return jsonify({
        "ok": True if nome or imagem else False,
        "nome": nome,
        "imagem": imagem,
        "preco": preco
    })

# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)
