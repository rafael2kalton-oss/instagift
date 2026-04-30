from flask import Flask, render_template, request, jsonify
import uuid, re, os, requests
from bs4 import BeautifulSoup

app = Flask(__name__, template_folder="templates")

SUPABASE_URL = "https://xmivfkpywjbrcrkniqbu.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_secret_0M-YowSnhrciNuzmJMS7AQ_QwA9GUjz")
SCRAPER_KEY  = os.getenv("SCRAPER_KEY", "3388267b140bf86c58e9ab0c2057c124")
AMAZON_TAG   = "instagift20-20"
ML_ID        = "DaniloBasilio40"

HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def sb_get(tabela, filtro=None):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}" + (f"?{filtro}" if filtro else "")
    return requests.get(url, headers=HEADERS_SB).json()

def sb_post(tabela, dados):
    return requests.post(f"{SUPABASE_URL}/rest/v1/{tabela}", headers=HEADERS_SB, json=dados).json()

def sb_patch(tabela, filtro, dados):
    return requests.patch(f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}", headers=HEADERS_SB, json=dados).json()

def sb_delete(tabela, filtro):
    return requests.delete(f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}", headers=HEADERS_SB).status_code

def detectar_plataforma(link):
    l = link.lower()
    if "amazon.com.br" in l or "amzn.to" in l: return "amazon"
    if "mercadolivre.com.br" in l or "mercadolibre.com" in l or "meli.com" in l: return "mercadolivre"
    if "shopee.com.br" in l: return "shopee"
    return "outro"

def injetar_afiliado(link, plataforma):
    if plataforma == "amazon":
        link = re.sub(r'[?&]tag=[^&]+', '', link)
        link += ('&' if '?' in link else '?') + 'tag=' + AMAZON_TAG
    elif plataforma == "mercadolivre":
        link = re.sub(r'[?&]matt_tool=[^&]+', '', link)
        link += ('&' if '?' in link else '?') + f'matt_tool=97&partner_id={ML_ID}'
    return link

def extrair_ml(link):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        # tenta catálogo /p/
        m = re.search(r'/p/(MLB\w+)', link, re.IGNORECASE)
        if m:
            r = requests.get(f"https://api.mercadolibre.com/products/{m.group(1)}", headers=headers, timeout=10).json()
            nome   = r.get("name", "")[:100]
            imagem = (r.get("pictures") or [{}])[0].get("url", "")
            # pega item para preço
            r2 = requests.get(f"https://api.mercadolibre.com/products/{m.group(1)}/items", headers=headers, timeout=10).json()
            item_id = (r2.get("results") or [None])[0]
            if item_id:
                r3 = requests.get(f"https://api.mercadolibre.com/items/{item_id}", headers=headers, timeout=10).json()
                preco = str(r3.get("price","")).replace(".",",")
                if not imagem:
                    imagem = (r3.get("pictures") or [{}])[0].get("url","")
                return nome, imagem, preco
            return nome, imagem, ""
        # tenta item direto MLB
        m2 = re.search(r'(MLB\d+)', link, re.IGNORECASE)
        if m2:
            r = requests.get(f"https://api.mercadolibre.com/items/{m2.group(1)}", headers=headers, timeout=10).json()
            nome   = r.get("title","")[:100]
            imagem = (r.get("pictures") or [{}])[0].get("url","")
            preco  = str(r.get("price","")).replace(".",",")
            return nome, imagem, preco
    except Exception as e:
        print("ML erro:", e)
    return "", "", ""

def extrair_dados(link, plataforma):
    if plataforma == "mercadolivre":
        n, i, p = extrair_ml(link)
        if n: return n, i, p

    # scraping direto
    try:
        r = requests.get(link, headers={"User-Agent":"Mozilla/5.0","Accept-Language":"pt-BR"}, timeout=8)
        html = r.text if r.status_code == 200 else ""
    except:
        html = ""

    # ScraperAPI fallback
    if len(html) < 1000 and SCRAPER_KEY:
        try:
            render = "true" if plataforma == "amazon" else "false"
            html = requests.get(f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={link}&render={render}", timeout=30).text
        except:
            html = ""

    if not html: return "", "", ""

    soup = BeautifulSoup(html, "html.parser")
    nome   = (soup.find("meta", property="og:title")  or {}).get("content","")[:100]
    imagem = (soup.find("meta", property="og:image")  or {}).get("content","")
    pm     = re.search(r'R\$\s*[\d.,]+', html)
    preco  = pm.group(0).replace("R$","").strip() if pm else ""
    return nome, imagem, preco

# -------- ROTAS --------

@app.route("/")
def index(): return render_template("criar_story.html")

@app.route("/criar-lista")
def criar_lista_page():
    return render_template("criar_lista.html", lista_id=str(uuid.uuid4())[:8])

@app.route("/lista/<lista_id>")
def lista_page(lista_id): return render_template("criar_lista.html", lista_id=lista_id)

@app.route("/vitrine/<lista_id>")
def vitrine(lista_id): return render_template("vitrine.html", lista_id=lista_id)

@app.route("/api/preview-produto", methods=["POST"])
def preview_produto():
    link = request.json.get("link","").strip()
    if not link: return jsonify({"ok":False}), 400
    plataforma   = detectar_plataforma(link)
    link_afiliado = injetar_afiliado(link, plataforma)
    nome, imagem, preco = extrair_dados(link_afiliado, plataforma)
    return jsonify({"ok": bool(nome or imagem), "nome":nome, "imagem":imagem, "preco":preco})

@app.route("/api/adicionar-produto", methods=["POST"])
def adicionar_produto():
    data        = request.json
    link        = data.get("link","").strip()
    lista_id    = data.get("lista_id","").strip()
    if not link or not lista_id: return jsonify({"erro":"Dados inválidos"}), 400

    plataforma    = detectar_plataforma(link)
    link_afiliado = injetar_afiliado(link, plataforma)
    nome, imagem, preco = extrair_dados(link_afiliado, plataforma)

    # garante lista
    lista = sb_get("listas", f"id=eq.{lista_id}")
    if not lista or not isinstance(lista, list) or len(lista) == 0:
