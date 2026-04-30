from flask import Flask, render_template, request, jsonify
import uuid, re, requests
from bs4 import BeautifulSoup

app = Flask(__name__, template_folder="templates")

SUPABASE_URL = "https://xmivfkpywjbrcrkniqbu.supabase.co"
SUPABASE_KEY = "sb_secret_0M-YowSnhrciNuzmJMS7AQ_QwA9GUjz"
SCRAPER_KEY = "3388267b140bf86c58e9ab0c2057c124"
AMAZON_TAG = "instagift20-20"
ML_ID = "DaniloBasilio40"
ML_CLIENT_ID = "5415799706798482"
ML_CLIENT_SECRET = "GIPTdLAoQf4CKVycmLCr9WhAeV4sA2Pq"

HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

ml_token_cache = {"token": None}

def sb_get(tabela, filtro=None):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}"
    if filtro:
        url += f"?{filtro}"
    return requests.get(url, headers=HEADERS_SB).json()

def sb_post(tabela, dados):
    return requests.post(f"{SUPABASE_URL}/rest/v1/{tabela}", headers=HEADERS_SB, json=dados).json()

def sb_patch(tabela, filtro, dados):
    return requests.patch(f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}", headers=HEADERS_SB, json=dados).json()

def sb_delete(tabela, filtro):
    return requests.delete(f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}", headers=HEADERS_SB).status_code

def detectar_plataforma(link):
    l = link.lower()
    if "amazon.com.br" in l or "amzn.to" in l:
        return "amazon"
    if "mercadolivre.com.br" in l or "mercadolibre.com" in l or "meli.com" in l or "produto.mercadolivre" in l:
        return "mercadolivre"
    if "shopee.com.br" in l:
        return "shopee"
    return "outro"

def injetar_afiliado(link, plataforma):
    if plataforma == "amazon":
        link = re.sub(r'[?&]tag=[^&]+', '', link)
        link += ('&' if '?' in link else '?') + 'tag=' + AMAZON_TAG
    elif plataforma == "mercadolivre":
        link = re.sub(r'[?&]matt_tool=[^&]+', '', link)
        link += ('&' if '?' in link else '?') + f'matt_tool=97&partner_id={ML_ID}'
    return link

def get_ml_token():
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

def extrair_ml(link):
    try:
        token = get_ml_token()
        auth = {"Authorization": f"Bearer {token}"} if token else {"User-Agent": "Mozilla/5.0"}

        link_limpo = link.split('#')[0]

        # Tenta /p/ catalogo
        m = re.search(r'/p/(MLB\w+)', link_limpo, re.IGNORECASE)
        if m:
            catalog_id = m.group(1)
            r = requests.get(f"https://api.mercadolibre.com/products/{catalog_id}", headers=auth, timeout=10).json()
            nome = r.get("name", "")[:100]
            pics = r.get("pictures") or []
            imagem = pics[0].get("url", "") if pics else ""
            r2 = requests.get(f"https://api.mercadolibre.com/products/{catalog_id}/items", headers=auth, timeout=10).json()
            resultados = r2.get("results") or []
            if resultados:
                item_id = resultados[0]
                r3 = requests.get(f"https://api.mercadolibre.com/items/{item_id}", headers=auth, timeout=10).json()
                preco = str(r3.get("price", "")).replace(".", ",")
                if not imagem:
                    pics3 = r3.get("pictures") or []
                    imagem = pics3[0].get("url", "") if pics3 else ""
                return nome, imagem, preco
            return nome, imagem, ""

        # Tenta MLB direto no link
        m2 = re.search(r'MLB[-_]?(\d+)', link_limpo, re.IGNORECASE)
        if m2:
            item_id = f"MLB{m2.group(1)}"
            r = requests.get(f"https://api.mercadolibre.com/items/{item_id}", headers=auth, timeout=10).json()
            # Se retornou 403 ou erro usa ScraperAPI
            if r.get("status") == 403 or r.get("code") == "PA_UNAUTHORIZED_RESULT_FROM_POLICIES":
                print("ML API bloqueou — usando ScraperAPI")
                return "", "", ""
            nome = r.get("title", "")[:100]
            pics = r.get("pictures") or []
            imagem = pics[0].get("url", "") if pics else ""
            preco = str(r.get("price", "")).replace(".", ",")
            if nome:
                return nome, imagem, preco

    except Exception as e:
        print("ML erro:", e)
    return "", "", ""

def extrair_dados(link, plataforma):
    if plataforma == "mercadolivre":
        n, i, p = extrair_ml(link)
        if n:
            return n, i, p
        # Fallback ScraperAPI para ML quando API oficial falha
        print("ML fallback ScraperAPI")
        try:
            html = requests.get(
                f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={link.split('#')[0]}&render=false&country_code=br",
                timeout=60
            ).text
            if html and len(html) > 1000:
                soup = BeautifulSoup(html, "html.parser")
                nome = ""
                imagem = ""
                preco = ""
                t = soup.find("meta", property="og:title")
                if t:
                    nome = t.get("content", "")[:100]
                    nome = re.sub(r'\s*[:|]\s*Mercado Livre.*$', '', nome)
                i = soup.find("meta", property="og:image")
                if i:
                    imagem = i.get("content", "")
                pm = re.search(r'R\$\s*[\d.,]+', html)
                if pm:
                    preco = pm.group(0).replace("R$", "").strip()
                if nome or imagem:
                    return nome, imagem, preco
        except Exception as e:
            print("ML ScraperAPI erro:", e)

    try:
        r = requests.get(link, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR"}, timeout=8)
        html = r.text if r.status_code == 200 else ""
    except:
        html = ""

    if plataforma == "amazon" or len(html) < 1000:
        try:
            render = "true" if plataforma == "amazon" else "false"
            html = requests.get(
                f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={link}&render={render}&country_code=br&premium=true",
                timeout=60
            ).text
        except:
            html = ""

    if not html:
        return "", "", ""

    soup = BeautifulSoup(html, "html.parser")
    nome = ""
    imagem = ""
    preco = ""

    t = soup.find("meta", property="og:title")
    if t:
        nome = t.get("content", "")[:100]

    i = soup.find("meta", property="og:image")
    if i:
        imagem = i.get("content", "")

    if not imagem and plataforma == "amazon":
        img = soup.find("img", {"id": "landingImage"}) or soup.find("img", {"id": "imgBlkFront"})
        if img and img.get("src") and "http" in img.get("src", ""):
            imagem = img["src"]
        if not imagem:
            img = soup.find("img", {"data-old-hires": True})
            if img:
                imagem = img["data-old-hires"]

    if nome:
        nome = re.sub(r'\s*[:|]\s*Amazon.*$', '', nome)
        nome = re.sub(r'\s*[:|]\s*Mercado Livre.*$', '', nome)
        nome = re.sub(r'\s*[:|]\s*Shopee.*$', '', nome)

    if plataforma == "amazon":
        preco_tag = soup.find("span", {"class": "a-price-whole"})
        if preco_tag:
            preco_frac = soup.find("span", {"class": "a-price-fraction"})
            preco = preco_tag.text.strip().replace('.', '').replace(',', '')
            if preco_frac:
                preco = preco + ',' + preco_frac.text.strip()

    if not preco:
        pm = re.search(r'R\$\s*[\d.,]+', html)
        if pm:
            preco = pm.group(0).replace("R$", "").strip()

    return nome, imagem, preco

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

@app.route("/vitrine/<lista_id>")
def vitrine(lista_id):
    return render_template("vitrine.html", lista_id=lista_id)

@app.route("/api/preview-produto", methods=["POST"])
def preview_produto():
    link = request.json.get("link", "").strip()
    if not link:
        return jsonify({"ok": False}), 400
    plataforma = detectar_plataforma(link)
    link_afiliado = injetar_afiliado(link, plataforma)
    nome, imagem, preco = extrair_dados(link_afiliado, plataforma)
    return jsonify({"ok": bool(nome or imagem), "nome": nome, "imagem": imagem, "preco": preco})

@app.route("/api/adicionar-produto", methods=["POST"])
def adicionar_produto():
    data = request.json
    link = data.get("link", "").strip()
    lista_id = data.get("lista_id", "").strip()
    if not link or not lista_id:
        return jsonify({"erro": "Dados inválidos"}), 400
    plataforma = detectar_plataforma(link)
    link_afiliado = injetar_afiliado(link, plataforma)
    nome, imagem, preco = extrair_dados(link_afiliado, plataforma)
    if not nome:
        nome = "Produto"
    lista = sb_get("listas", f"id=eq.{lista_id}")
    if not lista or not isinstance(lista, list) or len(lista) == 0:
        sb_post("listas", {"id": lista_id, "nome": "Minha Lista"})
    produto = sb_post("produtos", {
        "lista_id": lista_id,
        "nome": nome,
        "preco": preco,
        "imagem_url": imagem,
        "link_original": link,
        "link_afiliado": link_afiliado,
        "plataforma": plataforma,
        "reservado": 0
    })
    if isinstance(produto, list):
        return jsonify({"ok": True, "produto": produto[0]})
    return jsonify({"ok": True, "produto": produto})

@app.route("/api/produtos/<lista_id>")
def listar_produtos(lista_id):
    produtos = sb_get("produtos", f"lista_id=eq.{lista_id}&order=id.asc")
    if isinstance(produtos, list):
        return jsonify(produtos)
    return jsonify([])

@app.route("/api/remover-produto/<int:produto_id>", methods=["DELETE"])
def remover_produto(produto_id):
    sb_delete("produtos", f"id=eq.{produto_id}")
    return jsonify({"ok": True})

@app.route("/api/reservar/<int:produto_id>", methods=["POST"])
def reservar(produto_id):
    produtos = sb_get("produtos", f"id=eq.{produto_id}")
    if not produtos or not isinstance(produtos, list):
        return jsonify({"erro": "Não encontrado"}), 404
    if produtos[0].get("reservado"):
        return jsonify({"erro": "Já reservado"}), 400
    sb_patch("produtos", f"id=eq.{produto_id}", {"reservado": 1})
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True)
