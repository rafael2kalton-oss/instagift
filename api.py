from flask import Flask, render_template, request, jsonify, redirect
import uuid, re, requests, resend, stripe, anthropic, base64
from bs4 import BeautifulSoup
import os
from datetime import datetime, timedelta

app = Flask(__name__, template_folder="templates")

SUPABASE_URL = "https://xmivfkpywjbrcrkniqbu.supabase.co"
SUPABASE_KEY = "sb_secret_0M-YowSnhrciNuzmJMS7AQ_QwA9GUjz"
SCRAPER_KEY = "3388267b140bf86c58e9ab0c2057c124"
AMAZON_TAG = "instagift20-20"
ML_ID = "DaniloBasilio40"
SHOPEE_ID = "18374451025"
MAGALU_ID = "magazinevitrinedodanilo"
ML_CLIENT_ID = "5415799706798482"
ML_CLIENT_SECRET = "GIPTdLAoQf4CKVycmLCr9WhAeV4sA2Pq"
RESEND_KEY = "re_BMvckQ8G_KZdPini3AxGzHUTirGtsiixC"
STRIPE_SECRET_KEY = "sk_test_51TXRmJ41uxxrCBOGBQ26wvpgxbg7fNQVZqHsf8fjvHkRYht1SgikEQnFtxUTXPMozTDOrRK5G9PDkxu7MSb9jWHM009jcBfsmv"
STRIPE_PUBLIC_KEY = "pk_test_51TXRmJ41uxxrCBOGc4Rt0AKAErdUeGMKi7nXCBM1dlxsKs0HVw09tORnGfku1YNLif1GiBIGziNMrdT30091vAVts7"
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
STRIPE_CONVITE_IA_PRICE = "price_1Tb4Tk41uxxrCBOG2iuUoC2J"

STRIPE_PACOTES = {
    "5":  {"price_id": "price_1TXS6H41uxxrCBOGqrRYbBhv", "fotos": 5,  "valor": "R$ 9,90"},
    "10": {"price_id": "price_1TXSBn41uxxrCBOGWfYbpFCt", "fotos": 10, "valor": "R$ 19,90"},
    "25": {"price_id": "price_1TXSCB41uxxrCBOGaliEnmy3", "fotos": 25, "valor": "R$ 49,90"},
    "cofrinho": {"price_id": "price_1TYuZj41uxxrCBOGVDjlG7Pf", "fotos": 0, "valor": "R$ 15,90"},
    "celebracao": {"price_id": "price_1TYudb41uxxrCBOGuOcE4aeo", "fotos": 5, "valor": "R$ 25,90"},
    "convite_ia": {"price_id": STRIPE_CONVITE_IA_PRICE, "fotos": 0, "valor": "R$ 9,90"},
}

stripe.api_key = STRIPE_SECRET_KEY
resend.api_key = RESEND_KEY

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

def resolver_redirect(link):
    try:
        dominios_encurtados = [
            'amzn.to', 'a.co', 'br.shp.ee', 's.shopee', 'meli.la',
            'mglu.me', 'onelink.shein.com', 'api-shein.shein.com',
            'share.google', 'bit.ly', 'tinyurl.com'
        ]
        precisa_resolver = any(d in link.lower() for d in dominios_encurtados)
        if precisa_resolver:
            r = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, allow_redirects=True)
            return r.url
    except Exception as e:
        print(f"Erro ao resolver redirect: {e}")
    return link

def detectar_plataforma(link):
    l = link.lower()
    if "amazon.com.br" in l or "amzn.to" in l or "a.co/" in l: return "amazon"
    if "magazinevoce.com.br" in l or "magazineluiza.com.br" in l or "magalu.com.br" in l or "mglu.me" in l: return "magalu"
    if "mercadolivre.com.br" in l or "mercadolibre.com" in l or "meli.com" in l or "meli.la" in l or "produto.mercadolivre" in l: return "mercadolivre"
    if "shopee.com.br" in l or "br.shp.ee" in l or "s.shopee" in l: return "shopee"
    if "shein.com" in l or "onelink.shein.com" in l or "api-shein.shein.com" in l: return "shein"
    return "outro"

def injetar_afiliado(link, plataforma):
    if plataforma == "amazon":
        asin = re.search(r'/dp/([A-Z0-9]{10})', link)
        if asin:
            link = f"https://www.amazon.com.br/dp/{asin.group(1)}?tag={AMAZON_TAG}"
        else:
            link = re.sub(r'[?&]tag=[^&]+', '', link)
            link += ('&' if '?' in link else '?') + 'tag=' + AMAZON_TAG
    elif plataforma == "mercadolivre":
        link = re.sub(r'[?&]matt_tool=[^&]+', '', link)
        link += ('&' if '?' in link else '?') + f'matt_tool=97&partner_id={ML_ID}'
    elif plataforma == "shopee":
        link = re.sub(r'[?&]smtt=[^&]+', '', link)
        link += ('&' if '?' in link else '?') + f'smtt=0.0.9&source_identifier=affiliate&subfolder_id={SHOPEE_ID}'
    elif plataforma == "magalu":
        m = re.search(r'/([^/]+)/p/', link)
        if m:
            slug = m.group(1)
            sku = re.search(r'/p/([^/?]+)', link)
            if sku:
                link = f"https://www.magazinevoce.com.br/{MAGALU_ID}/{slug}/p/{sku.group(1)}/"
        elif "magazineluiza.com.br" in link or "magalu.com.br" in link:
            link = f"https://www.magazinevoce.com.br/{MAGALU_ID}/"
    elif plataforma == "shein":
        link = re.sub(r'[?&]url_from=[^&]+', '', link)
        link += ('&' if '?' in link else '?') + 'url_from=affiliate_koc_6312284765'
    return link

def get_ml_token():
    try:
        if ml_token_cache["token"]:
            return ml_token_cache["token"]
        r = requests.post("https://api.mercadolibre.com/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": ML_CLIENT_ID,
            "client_secret": ML_CLIENT_SECRET
        }, timeout=10)
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
        m2 = re.search(r'MLB[-_]?(\d+)', link_limpo, re.IGNORECASE)
        if not m2:
            try:
                r_red = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=8, allow_redirects=True)
                link_limpo = r_red.url
                m2 = re.search(r'MLB[-_]?(\d+)', link_limpo, re.IGNORECASE)
            except: pass
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
                if not imagem:
                    pics3 = r3.get("pictures") or []
                    imagem = pics3[0].get("url", "") if pics3 else ""
            return nome, imagem, ""
        if m2:
            item_id = f"MLB{m2.group(1)}"
            r = requests.get(f"https://api.mercadolibre.com/items/{item_id}", headers=auth, timeout=10).json()
            if r.get("status") == 403 or "UNAUTHORIZED" in str(r.get("code", "")):
                try:
                    r_search = requests.get(f"https://api.mercadolibre.com/sites/MLB/search?q={item_id}&limit=1", headers=auth, timeout=8).json()
                    resultados = r_search.get("results", [])
                    if resultados:
                        return resultados[0].get("title", "")[:100], "", ""
                except: pass
                return "", "", ""
            nome = r.get("title", "")[:100]
            pics = r.get("pictures") or []
            imagem = pics[0].get("url", "") if pics else ""
            if nome: return nome, imagem, ""
    except Exception as e:
        print("ML erro:", e)
    return "", "", ""

def extrair_shopee(link):
    try:
        html = requests.get(f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={link}&render=false&country_code=br", timeout=20).text
        soup = BeautifulSoup(html, "html.parser")
        nome = ""
        t = soup.find("meta", property="og:title")
        if t:
            nome = t.get("content", "")[:100]
            nome = re.sub(r'\s*[:|]\s*Shopee.*$', '', nome)
        imagem = ""
        i = soup.find("meta", property="og:image")
        if i: imagem = i.get("content", "")
        return nome, imagem, ""
    except Exception as e:
        print("Shopee erro:", e)
        return "", "", ""

def extrair_magalu(link):
    try:
        html = requests.get(f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={link}&render=false&country_code=br", timeout=20).text
        soup = BeautifulSoup(html, "html.parser")
        nome = imagem = preco = ""
        t = soup.find("meta", property="og:title")
        if t:
            nome = t.get("content", "")[:100]
            nome = re.sub(r'\s*[:|]\s*Magazine Luiza.*$', '', nome)
            nome = re.sub(r'\s*[:|]\s*Magalu.*$', '', nome)
        i = soup.find("meta", property="og:image")
        if i: imagem = i.get("content", "")
        pm = re.search(r'R\$\s*[\d.,]+', html)
        if pm: preco = pm.group(0).replace("R$", "").strip()
        return nome, imagem, preco
    except Exception as e:
        print("Magalu erro:", e)
        return "", "", ""

def extrair_shein(link):
    try:
        if "onelink.shein.com" in link or "api-shein.shein.com" in link or "sharejump" in link:
            try:
                r_red = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, allow_redirects=True)
                link = r_red.url
            except Exception as e:
                print("Shein redirect erro:", e)
        nome = imagem = preco = ""
        goods_id = None
        m = re.search(r'goods[_-]id[=/-](\d+)', link, re.IGNORECASE)
        if not m: m = re.search(r'/(\d{6,12})\.html', link)
        if not m: m = re.search(r'[?&]goods_id=(\d+)', link)
        if m: goods_id = m.group(1)
        if goods_id:
            try:
                api_url = f"https://api-shein.shein.com/v2/goods/detail?goods_id={goods_id}&currency=BRL&lang=pt"
                r_api = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=10)
                data = r_api.json()
                info = data.get("info", {}) or {}
                detail = info.get("goods_info", {}) or {}
                if detail.get("goods_name"): nome = detail["goods_name"][:100]
                if detail.get("goods_img"): imagem = "https:" + detail["goods_img"] if detail["goods_img"].startswith("//") else detail["goods_img"]
                preco_info = detail.get("retailPrice", {}) or {}
                if preco_info.get("amountWithSymbol"): preco = preco_info["amountWithSymbol"].replace("R$", "").strip()
            except Exception as e:
                print("Shein API erro:", e)
        if not nome or not imagem:
            try:
                html = requests.get(f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={link}&render=true&country_code=br", timeout=25).text
                soup = BeautifulSoup(html, "html.parser")
                if not nome:
                    t = soup.find("meta", property="og:title")
                    if t:
                        nome = t.get("content", "")[:100]
                        nome = re.sub(r'\s*[:|]\s*SHEIN.*$', '', nome, flags=re.IGNORECASE)
                if not imagem:
                    i = soup.find("meta", property="og:image")
                    if i: imagem = i.get("content", "")
                if not imagem:
                    img = soup.find("img", {"class": re.compile(r'crop-image-container|goods-img', re.I)})
                    if img: imagem = img.get("src", "") or img.get("data-src", "")
                if not preco:
                    pm = re.search(r'R\$\s*[\d.,]+', html)
                    if pm: preco = pm.group(0).replace("R$", "").strip()
            except Exception as e:
                print("Shein ScraperAPI erro:", e)
        return nome, imagem, preco
    except Exception as e:
        print("Shein erro geral:", e)
        return "", "", ""

def extrair_dados(link, plataforma):
    link = resolver_redirect(link)
    if plataforma == "shopee":
        n, i, p = extrair_shopee(link)
        if n: return n, i, p
    if plataforma == "magalu":
        n, i, p = extrair_magalu(link)
        if n: return n, i, p
    if plataforma == "shein":
        n, i, p = extrair_shein(link)
        if n: return n, i, p
    if plataforma == "mercadolivre":
        n, i, p = extrair_ml(link)
        if n: return n, i, p
    try:
        r = requests.get(link, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR"}, timeout=8)
        html = r.text if r.status_code == 200 else ""
    except: html = ""
    if plataforma == "amazon" or len(html) < 1000:
        try:
            render = "true" if plataforma == "amazon" else "false"
            html = requests.get(f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={link}&render={render}&country_code=br&premium=true", timeout=25).text
        except Exception as e:
            print("ScraperAPI erro:", e)
            html = ""
    if not html: return "", "", ""
    soup = BeautifulSoup(html, "html.parser")
    nome = imagem = preco = ""
    t = soup.find("meta", property="og:title")
    if t: nome = t.get("content", "")[:100]
    i = soup.find("meta", property="og:image")
    if i: imagem = i.get("content", "")
    if not imagem and plataforma == "amazon":
        img = soup.find("img", {"id": "landingImage"}) or soup.find("img", {"id": "imgBlkFront"})
        if img and img.get("src") and "http" in img.get("src", ""): imagem = img["src"]
        if not imagem:
            img = soup.find("img", {"data-old-hires": True})
            if img: imagem = img["data-old-hires"]
    if nome:
        nome = re.sub(r'\s*[:|]\s*Amazon.*$', '', nome)
        nome = re.sub(r'\s*[:|]\s*Mercado Livre.*$', '', nome)
        nome = re.sub(r'\s*[:|]\s*Shopee.*$', '', nome)
        nome = re.sub(r'\s*[:|]\s*Magazine Luiza.*$', '', nome)
    if plataforma == "amazon":
        preco_tag = soup.find("span", {"class": "a-price-whole"})
        if preco_tag:
            preco_frac = soup.find("span", {"class": "a-price-fraction"})
            preco = preco_tag.text.strip().replace('.', '').replace(',', '')
            if preco_frac: preco = preco + ',' + preco_frac.text.strip()
    if not preco and plataforma != "mercadolivre":
        pm = re.search(r'R\$\s*[\d.,]+', html)
        if pm: preco = pm.group(0).replace("R$", "").strip()
    return nome, imagem, preco

def enviar_email_comprador(email_comprador, nome_comprador, nome_produto, token, base_url, link_produto=""):
    link_confirmacao = f"{base_url}/confirmar-compra/{token}"
    link_btn = f'<a href="{link_produto}" style="display:block;background:#1a1a2e;color:#8A63D2;text-align:center;padding:14px;border-radius:12px;font-size:14px;font-weight:700;text-decoration:none;margin-bottom:16px;border:1px solid rgba(138,99,210,0.3);">Acessar o presente novamente</a>' if link_produto else ""
    try:
        resend.Emails.send({
            "from": "FestStory <onboarding@resend.dev>",
            "to": email_comprador,
            "subject": "Confirme que voce comprou o presente!",
            "html": f"<div style='font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#0D0D0D;color:#fff;padding:32px;border-radius:16px;'><h2 style='color:#8A63D2;'>Ola, {nome_comprador}!</h2><p style='color:#fff;font-weight:700;'>{nome_produto}</p>{link_btn}<a href='{link_confirmacao}' style='display:block;background:#22c55e;color:#fff;text-align:center;padding:18px;border-radius:12px;font-size:16px;font-weight:700;text-decoration:none;margin-bottom:24px;'>Sim, eu comprei o presente!</a><p style='color:#444;font-size:12px;text-align:center;'>Com carinho, FestStory</p></div>"
        })
    except Exception as e:
        print("Erro email comprador:", e)

def enviar_email_aniversariante(email_aniversariante, nome_comprador, nome_produto):
    try:
        resend.Emails.send({
            "from": "FestStory <onboarding@resend.dev>",
            "to": email_aniversariante,
            "subject": "Voce ganhou um presente!",
            "html": f"<div style='font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#0D0D0D;color:#fff;padding:32px;border-radius:16px;'><h2 style='color:#8A63D2;'>Que surpresa incrivel!</h2><p style='color:#fff;font-weight:700;'>{nome_produto}</p><p style='color:#888;'>presenteado por {nome_comprador}</p></div>"
        })
    except Exception as e:
        print("Erro email aniversariante:", e)

@app.route("/")
def index():
    return render_template("criar_story.html")

@app.route("/criar-lista")
def criar_lista_page():
    lista_id = request.args.get("id", "").strip()
    if not lista_id:
        lista_id = str(uuid.uuid4())[:8]
    return render_template("criar_lista.html", lista_id=lista_id)

@app.route("/lista/<lista_id>")
def lista_page(lista_id):
    return render_template("criar_lista.html", lista_id=lista_id)

@app.route("/vitrine/<lista_id>")
def vitrine(lista_id):
    return render_template("vitrine.html", lista_id=lista_id)

@app.route("/api/lista-info/<lista_id>")
def lista_info(lista_id):
    lista = sb_get("listas", f"id=eq.{lista_id}")
    if lista and isinstance(lista, list):
        return jsonify(lista[0])
    return jsonify({})

@app.route("/api/salvar-email-lista", methods=["POST"])
def salvar_email_lista():
    data = request.json
    lista_id = data.get("lista_id", "").strip()
    email = data.get("email", "").strip()
    if not lista_id or not email:
        return jsonify({"erro": "Dados incompletos"}), 400
    lista = sb_get("listas", f"id=eq.{lista_id}")
    if not lista or not isinstance(lista, list) or len(lista) == 0:
        sb_post("listas", {"id": lista_id, "nome": "Minha Lista", "email_aniversariante": email})
    else:
        sb_patch("listas", f"id=eq.{lista_id}", {"email_aniversariante": email})
    return jsonify({"ok": True})

@app.route("/api/salvar-info-lista", methods=["POST"])
def salvar_info_lista():
    data = request.json
    lista_id = data.get("lista_id", "").strip()
    if not lista_id:
        return jsonify({"erro": "Dados incompletos"}), 400
    atualizacao = {}
    if data.get("nome"): atualizacao["nome"] = data["nome"]
    if data.get("data_evento"): atualizacao["data_evento"] = data["data_evento"]
    if data.get("evento"): atualizacao["evento"] = data["evento"]
    lista = sb_get("listas", f"id=eq.{lista_id}")
    if not lista or not isinstance(lista, list) or len(lista) == 0:
        atualizacao["id"] = lista_id
        sb_post("listas", atualizacao)
    else:
        if atualizacao:
            sb_patch("listas", f"id=eq.{lista_id}", atualizacao)
    return jsonify({"ok": True})

@app.route("/api/preview-produto", methods=["POST"])
def preview_produto():
    link = request.json.get("link", "").strip()
    if not link: return jsonify({"ok": False}), 400
    link = resolver_redirect(link)
    plataforma = detectar_plataforma(link)
    link_afiliado = injetar_afiliado(link, plataforma)
    nome, imagem, preco = extrair_dados(link_afiliado, plataforma)
    return jsonify({"ok": bool(nome or imagem), "nome": nome, "imagem": imagem, "preco": preco})

@app.route("/api/adicionar-produto", methods=["POST"])
def adicionar_produto():
    data = request.json
    link = data.get("link", "").strip()
    lista_id = data.get("lista_id", "").strip()
    if not link or not lista_id: return jsonify({"erro": "Dados invalidos"}), 400
    link = resolver_redirect(link)
    plataforma = detectar_plataforma(link)
    link_afiliado = injetar_afiliado(link, plataforma)
    nome, imagem, preco = extrair_dados(link_afiliado, plataforma)
    precisa_manual = not nome or not imagem
    if not nome: nome = "Produto"
    lista = sb_get("listas", f"id=eq.{lista_id}")
    if not lista or not isinstance(lista, list) or len(lista) == 0:
        sb_post("listas", {"id": lista_id, "nome": "Minha Lista"})
    produto = sb_post("produtos", {"lista_id": lista_id, "nome": nome, "preco": preco, "imagem_url": imagem, "link_original": link, "link_afiliado": link_afiliado, "plataforma": plataforma, "reservado": 0})
    p = produto[0] if isinstance(produto, list) else produto
    return jsonify({"ok": True, "produto": p, "manual": precisa_manual, "plataforma": plataforma})

@app.route("/api/produtos/<lista_id>")
def listar_produtos(lista_id):
    produtos = sb_get("produtos", f"lista_id=eq.{lista_id}&order=id.asc")
    return jsonify(produtos if isinstance(produtos, list) else [])

@app.route("/api/remover-produto/<int:produto_id>", methods=["DELETE"])
def remover_produto(produto_id):
    produto = sb_get("produtos", f"id=eq.{produto_id}")
    if produto and isinstance(produto, list) and len(produto) > 0:
        lista_id = produto[0].get("lista_id", "")
        if lista_id:
            todos = sb_get("produtos", f"lista_id=eq.{lista_id}")
            if isinstance(todos, list) and len(todos) == 1:
                confirmar = request.args.get("confirmar", "")
                if confirmar != "sim":
                    return jsonify({"ok": False, "ultimo": True}), 200
    sb_delete("produtos", f"id=eq.{produto_id}")
    return jsonify({"ok": True})

@app.route("/api/liberar-produto/<int:produto_id>", methods=["POST"])
def liberar_produto(produto_id):
    sb_patch("produtos", f"id=eq.{produto_id}", {"reservado": 0, "token_confirmacao": None, "reservado_em": None, "nome_comprador": None, "email_comprador": None})
    return jsonify({"ok": True})

@app.route("/api/adicionar-produto-manual", methods=["POST"])
def adicionar_produto_manual():
    data = request.json
    link = data.get("link", "").strip()
    lista_id = data.get("lista_id", "").strip()
    nome = data.get("nome", "Produto").strip()
    preco = data.get("preco", "").strip()
    imagem_base64 = data.get("imagem_base64", "")
    plataforma = data.get("plataforma", "outro")
    if not link or not lista_id: return jsonify({"erro": "Dados invalidos"}), 400
    link_afiliado = injetar_afiliado(link, plataforma)
    lista = sb_get("listas", f"id=eq.{lista_id}")
    if not lista or not isinstance(lista, list) or len(lista) == 0:
        sb_post("listas", {"id": lista_id, "nome": "Minha Lista"})
    produto = sb_post("produtos", {"lista_id": lista_id, "nome": nome, "preco": preco, "imagem_url": imagem_base64, "link_original": link, "link_afiliado": link_afiliado, "plataforma": plataforma, "reservado": 0})
    if isinstance(produto, list): return jsonify({"ok": True, "produto": produto[0]})
    return jsonify({"ok": True, "produto": produto})

@app.route("/api/reservar/<int:produto_id>", methods=["POST"])
def reservar(produto_id):
    data = request.json or {}
    nome_comprador = data.get("nome", "").strip()
    email_comprador = data.get("email", "").strip()
    if not nome_comprador or not email_comprador:
        return jsonify({"erro": "Nome e e-mail obrigatorios"}), 400
    produtos = sb_get("produtos", f"id=eq.{produto_id}")
    if not produtos or not isinstance(produtos, list):
        return jsonify({"erro": "Produto nao encontrado"}), 404
    if produtos[0].get("reservado"):
        return jsonify({"erro": "Ja reservado"}), 400
    token = str(uuid.uuid4())
    agora = datetime.utcnow().isoformat()
    sb_patch("produtos", f"id=eq.{produto_id}", {"reservado": 1, "token_confirmacao": token, "reservado_em": agora, "nome_comprador": nome_comprador, "email_comprador": email_comprador})
    nome_produto = produtos[0].get("nome", "Produto")
    link_produto = produtos[0].get("link_afiliado", "")
    base_url = request.host_url.rstrip('/')
    enviar_email_comprador(email_comprador, nome_comprador, nome_produto, token, base_url, link_produto)
    return jsonify({"ok": True})

@app.route("/confirmar-compra/<token>")
def confirmar_compra(token):
    produtos = sb_get("produtos", f"token_confirmacao=eq.{token}")
    if not produtos or not isinstance(produtos, list):
        return "<h2>Link invalido ou expirado.</h2>", 404
    produto = produtos[0]
    reservado_em = produto.get("reservado_em")
    if reservado_em:
        dt = datetime.fromisoformat(reservado_em.replace('Z', ''))
        if datetime.utcnow() > dt + timedelta(hours=3):
            sb_patch("produtos", f"id=eq.{produto['id']}", {"reservado": 0, "token_confirmacao": None, "reservado_em": None, "nome_comprador": None, "email_comprador": None})
            return render_template("confirmacao.html", status="expirado")
    sb_patch("produtos", f"id=eq.{produto['id']}", {"reservado": 2, "token_confirmacao": None})
    lista = sb_get("listas", f"id=eq.{produto['lista_id']}")
    if lista and isinstance(lista, list):
        email_aniversariante = lista[0].get("email_aniversariante")
        if email_aniversariante:
            enviar_email_aniversariante(email_aniversariante, produto.get("nome_comprador", "Alguem"), produto.get("nome", "Produto"))
    return render_template("confirmacao.html", status="confirmado", nome_produto=produto.get("nome", "Produto"))

@app.route("/api/limpar-reservas-expiradas", methods=["POST"])
def limpar_reservas_expiradas():
    try:
        agora = datetime.utcnow()
        prazo_limite = agora - timedelta(hours=3)
        produtos = sb_get("produtos", "reservado=eq.1")
        if not isinstance(produtos, list): return jsonify({"status": "sucesso", "liberados": 0}), 200
        liberados = 0
        for p in produtos:
            reservado_em = p.get("reservado_em")
            if reservado_em:
                dt_reserva = datetime.fromisoformat(reservado_em.replace('Z', ''))
                if dt_reserva < prazo_limite:
                    sb_patch("produtos", f"id=eq.{p['id']}", {"reservado": 0, "token_confirmacao": None, "reservado_em": None, "nome_comprador": None, "email_comprador": None})
                    liberados += 1
        return jsonify({"status": "sucesso", "liberados": liberados}), 200
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route("/api/editar-produto/<int:produto_id>", methods=["POST"])
def editar_produto(produto_id):
    data = request.json or {}
    nome = data.get("nome", "").strip()
    preco = data.get("preco", "").strip()
    imagem_base64 = data.get("imagem_base64", "")
    atualizacao = {}
    if nome: atualizacao["nome"] = nome
    if preco: atualizacao["preco"] = preco
    if imagem_base64: atualizacao["imagem_url"] = imagem_base64
    if atualizacao: sb_patch("produtos", f"id=eq.{produto_id}", atualizacao)
    return jsonify({"ok": True})

@app.route("/api/stripe/checkout", methods=["POST"])
def stripe_checkout():
    data = request.json or {}
    lista_id = data.get("lista_id", "").strip()
    pacote = data.get("pacote", "").strip()
    if not lista_id or pacote not in STRIPE_PACOTES:
        return jsonify({"erro": "Dados invalidos"}), 400
    info = STRIPE_PACOTES[pacote]
    base_url = request.host_url.rstrip('/')
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": info["price_id"], "quantity": 1}],
            mode="payment",
            success_url=f"{base_url}/stripe/sucesso?lista_id={lista_id}&pacote={pacote}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/configurar-premium/{lista_id}",
            metadata={"lista_id": lista_id, "pacote": pacote}
        )
        return jsonify({"ok": True, "url": session.url})
    except Exception as e:
        print("Stripe erro:", e)
        return jsonify({"erro": str(e)}), 500

@app.route("/stripe/sucesso")
def stripe_sucesso():
    lista_id = request.args.get("lista_id", "")
    pacote = request.args.get("pacote", "")
    session_id = request.args.get("session_id", "")
    if not lista_id or pacote not in STRIPE_PACOTES:
        return redirect(f"/configurar-premium/{lista_id}")
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            fotos_extras = STRIPE_PACOTES[pacote]["fotos"]
            config = sb_get("config_premium", f"lista_id=eq.{lista_id}")
            config_existe = config and isinstance(config, list) and len(config) > 0
            atualizacao = {}
            if fotos_extras > 0:
                limite_atual = config[0].get("limite_fotos", 10) if config_existe else 10
                atualizacao["limite_fotos"] = limite_atual + fotos_extras
            if pacote == "cofrinho":
                atualizacao["cofrinho_ativo"] = True
            if pacote == "celebracao":
                atualizacao["cofrinho_ativo"] = True
                atualizacao["estilo_mural"] = "carrossel"
            if atualizacao:
                if config_existe:
                    sb_patch("config_premium", f"lista_id=eq.{lista_id}", atualizacao)
                else:
                    atualizacao["lista_id"] = lista_id
                    sb_post("config_premium", atualizacao)
    except Exception as e:
        print("Stripe sucesso erro:", e)
    try:
        valor = float(STRIPE_PACOTES.get(pacote, {}).get("valor", "R$ 0").replace("R$ ", "").replace(",", "."))
        sb_post("vendas", {"lista_id": lista_id, "pacote": pacote, "valor": valor})
    except Exception as e:
        print("Erro registrar venda:", e)
    if pacote == "convite_ia":
        try:
            cfg_ia = sb_get("config_premium", f"lista_id=eq.{lista_id}")
            if cfg_ia and isinstance(cfg_ia, list) and len(cfg_ia) > 0:
                sb_patch("config_premium", f"lista_id=eq.{lista_id}", {"ia_pago": True})
            else:
                sb_post("config_premium", {"lista_id": lista_id, "ia_pago": True})
        except Exception as e:
            print("IA pago erro:", e)
        return redirect(f"/configurar-premium/{lista_id}?ia_pago=true")
    return redirect(f"/configurar-premium/{lista_id}?compra=ok&fotos={STRIPE_PACOTES.get(pacote, {}).get('fotos', 0)}")

@app.route("/api/limite-fotos/<lista_id>")
def get_limite_fotos(lista_id):
    config = sb_get("config_premium", f"lista_id=eq.{lista_id}")
    if config and isinstance(config, list) and len(config) > 0:
        return jsonify({"limite": config[0].get("limite_fotos", 10)})
    return jsonify({"limite": 10})

@app.route("/configurar-premium/<lista_id>")
def configurar_premium(lista_id):
    return render_template("configurar_premium.html", lista_id=lista_id)

@app.route("/api/config-premium/<lista_id>")
def get_config_premium(lista_id):
    config = sb_get("config_premium", f"lista_id=eq.{lista_id}")
    fotos = sb_get("fotos_mural", f"lista_id=eq.{lista_id}&order=ordem.asc")
    recados = sb_get("recados", f"lista_id=eq.{lista_id}&order=criado_em.desc")
    return jsonify({
        "config": config[0] if config and isinstance(config, list) else {},
        "fotos": fotos if isinstance(fotos, list) else [],
        "recados": recados if isinstance(recados, list) else []
    })

@app.route("/api/salvar-config-premium", methods=["POST"])
def salvar_config_premium():
    data = request.json or {}
    lista_id = data.get("lista_id", "").strip()
    if not lista_id: return jsonify({"erro": "Dados invalidos"}), 400
    config_existente = sb_get("config_premium", f"lista_id=eq.{lista_id}")
    payload = {
        "lista_id": lista_id,
        "mensagem_celebrante": data.get("mensagem_celebrante", ""),
        "texto_convite": data.get("texto_convite", ""),
        "usa_convite_padrao": data.get("usa_convite_padrao", True),
        "nome_celebrante": data.get("nome_celebrante", ""),
        "data_evento": data.get("data_evento", ""),
        "paleta": data.get("paleta", "dourado"),
        "estilo_mural": data.get("estilo_mural", "normal"),
        "local_evento": data.get("local_evento", ""),
        "chave_pix": data.get("chave_pix", ""),
        "cofrinho_ativo": data.get("cofrinho_ativo", False),
        "estilo_convite": data.get("estilo_convite", "classico"),
        "imagem_fundo_convite": data.get("imagem_fundo_convite", ""),
        "foto_capa": data.get("foto_capa", ""),
        "convite_ia_imagem": data.get("convite_ia_imagem", ""),
        "cor_texto_convite": data.get("cor_texto_convite", "claro"),
    }
    if config_existente and isinstance(config_existente, list) and len(config_existente) > 0:
        sb_patch("config_premium", f"lista_id=eq.{lista_id}", payload)
    else:
        sb_post("config_premium", payload)
    return jsonify({"ok": True})

@app.route("/api/salvar-foto-mural", methods=["POST"])
def salvar_foto_mural():
    data = request.json or {}
    lista_id = data.get("lista_id", "").strip()
    url_foto = data.get("url_foto", "").strip()
    ordem = data.get("ordem", 0)
    if not lista_id or not url_foto: return jsonify({"erro": "Dados invalidos"}), 400
    config = sb_get("config_premium", f"lista_id=eq.{lista_id}")
    limite = 10
    if config and isinstance(config, list) and len(config) > 0:
        limite = config[0].get("limite_fotos", 10)
    fotos_existentes = sb_get("fotos_mural", f"lista_id=eq.{lista_id}")
    if isinstance(fotos_existentes, list) and len(fotos_existentes) >= limite:
        return jsonify({"erro": f"Limite de {limite} fotos atingido!", "limite": True}), 400
    foto = sb_post("fotos_mural", {"lista_id": lista_id, "url_foto": url_foto, "ordem": ordem})
    return jsonify({"ok": True, "foto": foto[0] if isinstance(foto, list) else foto})

@app.route("/api/remover-foto-mural/<int:foto_id>", methods=["DELETE"])
def remover_foto_mural(foto_id):
    sb_delete("fotos_mural", f"id=eq.{foto_id}")
    return jsonify({"ok": True})

@app.route("/api/salvar-recado", methods=["POST"])
def salvar_recado():
    data = request.json or {}
    lista_id = data.get("lista_id", "").strip()
    nome = data.get("nome", "").strip()
    mensagem = data.get("mensagem", "").strip()
    if not lista_id or not nome or not mensagem: return jsonify({"erro": "Preencha nome e mensagem"}), 400
    recado = sb_post("recados", {"lista_id": lista_id, "nome": nome, "mensagem": mensagem})
    return jsonify({"ok": True, "recado": recado[0] if isinstance(recado, list) else recado})

@app.route("/api/excluir-recado/<int:recado_id>", methods=["DELETE"])
def excluir_recado(recado_id):
    sb_delete("recados", f"id=eq.{recado_id}")
    return jsonify({"ok": True})

@app.route("/api/recados/<lista_id>")
def listar_recados(lista_id):
    recados = sb_get("recados", f"lista_id=eq.{lista_id}&order=criado_em.desc")
    return jsonify(recados if isinstance(recados, list) else [])

@app.route("/api/salvar-presenca", methods=["POST"])
def salvar_presenca():
    data = request.json or {}
    lista_id = data.get("lista_id", "").strip()
    nome = data.get("nome", "").strip()
    status = data.get("status", "confirmado")
    acompanhantes = data.get("acompanhantes", 0)
    if not lista_id or not nome: return jsonify({"erro": "Dados invalidos"}), 400
    presenca = sb_post("presencas", {"lista_id": lista_id, "nome": nome, "status": status, "acompanhantes": acompanhantes})
    try:
        lista = sb_get("listas", f"id=eq.{lista_id}")
        config = sb_get("config_premium", f"lista_id=eq.{lista_id}")
        if lista and isinstance(lista, list) and lista[0].get("email_aniversariante"):
            email_dest = lista[0]["email_aniversariante"]
            nome_evento = config[0].get("nome_celebrante", "seu evento") if config and isinstance(config, list) else "seu evento"
            status_label = "Confirmou presenca" if status == "confirmado" else "Talvez" if status == "talvez" else "Nao vai comparecer"
            acomp_texto = f" com {acompanhantes} acompanhante(s)" if acompanhantes > 0 else ""
            resend.Emails.send({
                "from": "FestStory <onboarding@resend.dev>",
                "to": email_dest,
                "subject": f"Nova confirmacao de presenca - {nome_evento}",
                "html": f"<div style='font-family:Arial;max-width:500px;margin:0 auto;background:#FFF8EC;padding:32px;border-radius:16px;'><h2 style='color:#C9A84C;'>Nova confirmacao!</h2><p><strong>{nome}{acomp_texto}</strong> - {status_label}</p></div>"
            })
    except Exception as e:
        print("Erro email presenca:", e)
    return jsonify({"ok": True, "presenca": presenca[0] if isinstance(presenca, list) else presenca})

@app.route("/api/presencas/<lista_id>")
def listar_presencas(lista_id):
    presencas = sb_get("presencas", f"lista_id=eq.{lista_id}&order=criado_em.asc")
    return jsonify(presencas if isinstance(presencas, list) else [])

@app.route("/premium/<lista_id>")
def premium(lista_id):
    return render_template("premium.html", lista_id=lista_id)

@app.route("/minha-celebracao/<lista_id>")
def minha_celebracao(lista_id):
    return render_template("minha_celebracao.html", lista_id=lista_id)

@app.route("/api/verificar-expiracao/<lista_id>")
def verificar_expiracao(lista_id):
    try:
        config = sb_get("config_premium", f"lista_id=eq.{lista_id}")
        if not config or not isinstance(config, list) or len(config) == 0:
            return jsonify({"expirada": False, "motivo": None})
        cfg = config[0]
        data_evento_str = cfg.get("data_evento")
        criado_em_str = cfg.get("criado_em")
        hoje = datetime.utcnow()
        if data_evento_str:
            data_evento = datetime.fromisoformat(data_evento_str)
            if hoje > data_evento + timedelta(days=7):
                return jsonify({"expirada": True, "motivo": "evento_encerrado"})
        if criado_em_str:
            criado_em = datetime.fromisoformat(criado_em_str.replace('Z', ''))
            if hoje > criado_em + timedelta(days=180):
                return jsonify({"expirada": True, "motivo": "prazo_expirado"})
        return jsonify({"expirada": False, "motivo": None})
    except Exception as e:
        return jsonify({"expirada": False, "motivo": None})

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/acesso/<lista_id>")
def acesso_direto(lista_id):
    return render_template("configurar_premium.html", lista_id=lista_id)

@app.route("/api/enviar-magic-link", methods=["POST"])
def enviar_magic_link():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    if not email: return jsonify({"erro": "E-mail obrigatorio"}), 400
    listas = sb_get("listas", f"email_aniversariante=eq.{email}")
    lista_id = None
    if listas and isinstance(listas, list) and len(listas) > 0:
        lista_id = listas[0]["id"]
    else:
        lista_id = str(uuid.uuid4())[:8]
        sb_post("listas", {"id": lista_id, "nome": "Minha Lista", "email_aniversariante": email})
    links_existentes = sb_get("magic_links", f"email=eq.{email}&usado=eq.false")
    if links_existentes and isinstance(links_existentes, list) and len(links_existentes) > 0:
        token = links_existentes[0]["token"]
    else:
        token = str(uuid.uuid4())
        expira_em = (datetime.utcnow() + timedelta(days=187)).isoformat()
        sb_post("magic_links", {"lista_id": lista_id, "email": email, "token": token, "expira_em": expira_em})
    link = request.host_url.rstrip("/") + f"/acesso-magico/{token}"
    try:
        resend.Emails.send({
            "from": "FestStory <onboarding@resend.dev>",
            "to": email,
            "subject": "✦ Seu link de acesso — FestStory",
            "html": f"""<div style='font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#FFF8EC;padding:40px 32px;border-radius:20px;border:1px solid rgba(201,168,76,0.3);'><div style='text-align:center;margin-bottom:28px;'><div style='font-family:Georgia,serif;font-size:32px;color:#C9A84C;font-weight:700;'>FestStory</div><p style='color:#C9A84C;font-size:14px;letter-spacing:0.2em;margin-top:4px;'>✦ &nbsp; ✦ &nbsp; ✦</p></div><h2 style='font-family:Georgia,serif;color:#2C2C2C;font-size:22px;font-weight:700;margin-bottom:10px;text-align:center;'>Seu link chegou!</h2><p style='color:#888;font-size:14px;line-height:1.7;margin-bottom:28px;text-align:center;font-style:italic;'>Clique no botão abaixo para acessar sua Página do Evento e criar sua lista de presentes.</p><a href='{link}' style='display:block;background:linear-gradient(135deg,#C9A84C,#A8722A);color:#fff;text-align:center;padding:18px 24px;border-radius:50px;font-size:17px;font-weight:700;text-decoration:none;margin-bottom:20px;letter-spacing:0.03em;box-shadow:0 4px 20px rgba(201,168,76,0.4);'>✦ ACESSAR MINHA PÁGINA</a><p style='color:#bbb;font-size:11px;text-align:center;line-height:1.6;'>Este link é exclusivo para você e fica salvo por 6 meses.<br>Se não solicitou, ignore este e-mail.</p></div>"""
        })
    except Exception as e:
        print("Erro magic link email:", e)
    return jsonify({"ok": True})

@app.route("/acesso-magico/<token>")
def acesso_magico(token):
    links = sb_get("magic_links", f"token=eq.{token}&usado=eq.false")
    if not links or not isinstance(links, list) or len(links) == 0:
        return render_template("login.html")
    link = links[0]
    expira_em = datetime.fromisoformat(link["expira_em"].replace("Z",""))
    if datetime.utcnow() > expira_em:
        return render_template("login.html")
    lista_id = link["lista_id"]
    return redirect(f"/lista/{lista_id}")

PRESIDENTE_TOKEN = "instagift-presidente"

@app.route("/presidente/<token>")
def presidente(token):
    if token != PRESIDENTE_TOKEN:
        return redirect("/")
    return render_template("presidente.html")

@app.route("/api/presidente/metricas")
def presidente_metricas():
    try:
        listas = sb_get("listas", "order=criado_em.desc&limit=100") or []
        if not isinstance(listas, list): listas = []
        paginas = sb_get("config_premium", "limit=100") or []
        if not isinstance(paginas, list): paginas = []
        recados = sb_get("recados", "limit=100") or []
        if not isinstance(recados, list): recados = []
        try:
            vendas = sb_get("vendas", "order=criado_em.desc&limit=100") or []
            if not isinstance(vendas, list): vendas = []
        except Exception:
            vendas = []
        faturamento = 0
        vendas_por_pacote = {}
        vendas_hoje = 0
        hoje = datetime.utcnow().date()
        for v in vendas:
            try:
                faturamento += float(v.get("valor", 0))
            except Exception:
                pass
            pacote = v.get("pacote", "")
            vendas_por_pacote[pacote] = vendas_por_pacote.get(pacote, 0) + 1
            criado = v.get("criado_em", "")
            if criado and criado[:10] == str(hoje):
                vendas_hoje += 1
        return jsonify({
            "total_listas": len(listas),
            "paginas_ativas": len(paginas),
            "total_recados": len(recados),
            "vendas_hoje": vendas_hoje,
            "faturamento_total": round(faturamento, 2),
            "vendas_por_pacote": vendas_por_pacote,
        })
    except Exception as e:
        print("Presidente metricas erro:", e)
        return jsonify({"total_listas": 0, "paginas_ativas": 0, "total_recados": 0, "vendas_hoje": 0, "faturamento_total": 0, "vendas_por_pacote": {}})

@app.route("/api/presidente/vendas")
def presidente_vendas():
    try:
        vendas = sb_get("vendas", "order=criado_em.desc&limit=50")
        if not isinstance(vendas, list):
            return jsonify([])
        return jsonify(vendas)
    except Exception as e:
        return jsonify([])

@app.route("/api/presidente/paginas")
def presidente_paginas():
    try:
        paginas = sb_get("config_premium", "order=criado_em.desc&limit=100")
        return jsonify(paginas if isinstance(paginas, list) else [])
    except Exception as e:
        return jsonify([])

@app.route("/api/presidente/liberar-premium", methods=["POST"])
def presidente_liberar_premium():
    data = request.json or {}
    lista_id = data.get("lista_id", "").strip()
    limite_fotos = data.get("limite_fotos", 20)
    cofrinho_ativo = data.get("cofrinho_ativo", False)
    if not lista_id:
        return jsonify({"erro": "Lista ID obrigatorio"}), 400
    config = sb_get("config_premium", f"lista_id=eq.{lista_id}")
    atualizacao = {"limite_fotos": limite_fotos, "cofrinho_ativo": cofrinho_ativo}
    if cofrinho_ativo:
        atualizacao["estilo_mural"] = "carrossel"
    if config and isinstance(config, list) and len(config) > 0:
        sb_patch("config_premium", f"lista_id=eq.{lista_id}", atualizacao)
    else:
        atualizacao["lista_id"] = lista_id
        sb_post("config_premium", atualizacao)
    try:
        sb_post("vendas", {"lista_id": lista_id, "pacote": "cofrinho" if cofrinho_ativo else "manual", "valor": 0})
    except Exception:
        pass
    return jsonify({"ok": True})

@app.route("/api/presidente/excluir-pagina", methods=["POST"])
def presidente_excluir_pagina():
    data = request.json or {}
    lista_id = data.get("lista_id", "").strip()
    if not lista_id:
        return jsonify({"erro": "Lista ID obrigatorio"}), 400
    sb_delete("config_premium", f"lista_id=eq.{lista_id}")
    sb_delete("fotos_mural",    f"lista_id=eq.{lista_id}")
    sb_delete("recados",        f"lista_id=eq.{lista_id}")
    sb_delete("presencas",      f"lista_id=eq.{lista_id}")
    sb_delete("magic_links",    f"lista_id=eq.{lista_id}")
    sb_delete("produtos",       f"lista_id=eq.{lista_id}")
    sb_delete("listas",         f"id=eq.{lista_id}")
    return jsonify({"ok": True})

@app.route("/api/presidente/liberar-cortesia", methods=["POST"])
def presidente_liberar_cortesia():
    data = request.json or {}
    lista_id = data.get("lista_id", "").strip()
    if not lista_id:
        return jsonify({"erro": "Lista ID obrigatorio"}), 400
    config = sb_get("config_premium", f"lista_id=eq.{lista_id}")
    config_existe = config and isinstance(config, list) and len(config) > 0
    atualizacao = {}
    if data.get("cofrinho_ativo"):
        atualizacao["cofrinho_ativo"] = True
    if data.get("estilo_mural"):
        atualizacao["estilo_mural"] = data["estilo_mural"]
    fotos_extras = int(data.get("fotos_extras", 0))
    if fotos_extras > 0:
        limite_atual = config[0].get("limite_fotos", 10) if config_existe else 10
        atualizacao["limite_fotos"] = limite_atual + fotos_extras
    if data.get("convite_ia"):
        atualizacao["ia_pago"] = True
    if atualizacao:
        if config_existe:
            sb_patch("config_premium", f"lista_id=eq.{lista_id}", atualizacao)
        else:
            atualizacao["lista_id"] = lista_id
            sb_post("config_premium", atualizacao)
    return jsonify({"ok": True})

@app.route("/api/gerar-convite-ia", methods=["POST"])
def gerar_convite_ia():
    data = request.json or {}
    lista_id = data.get("lista_id", "").strip()
    descricao = data.get("descricao", "").strip()
    nome_evento = data.get("nome_evento", "").strip()
    data_evento_str = data.get("data_evento", "").strip()
    imagem_ref_b64 = data.get("imagem_referencia", "")
    if not lista_id or not descricao:
        return jsonify({"erro": "Dados incompletos"}), 400
    config = sb_get("config_premium", f"lista_id=eq.{lista_id}")
    config_existe = config and isinstance(config, list) and len(config) > 0
    cfg = config[0] if config_existe else {}
    ia_pago = cfg.get("ia_pago", False)
    ia_geracoes = int(cfg.get("ia_geracoes", 0) or 0)
    LIMITE_GERACOES = 3

    # ✦ Sem pagamento — redireciona para Stripe
    if not ia_pago:
        try:
            base_url = request.host_url.rstrip("/")
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": STRIPE_CONVITE_IA_PRICE, "quantity": 1}],
                mode="payment",
                success_url=f"{base_url}/configurar-premium/{lista_id}?ia_pago=true",
                cancel_url=f"{base_url}/configurar-premium/{lista_id}",
                metadata={"lista_id": lista_id, "pacote": "convite_ia"}
            )
            return jsonify({"pagamento_url": session.url})
        except Exception as e:
            print("Stripe IA erro:", e)
            return jsonify({"erro": "Erro ao criar pagamento"}), 500

    # ✦ Limite de gerações atingido — força novo pagamento
    if ia_geracoes >= LIMITE_GERACOES:
        try:
            # Reseta ia_pago para forçar novo pagamento
            sb_patch("config_premium", f"lista_id=eq.{lista_id}", {"ia_pago": False, "ia_geracoes": 0})
            base_url = request.host_url.rstrip("/")
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": STRIPE_CONVITE_IA_PRICE, "quantity": 1}],
                mode="payment",
                success_url=f"{base_url}/configurar-premium/{lista_id}?ia_pago=true",
                cancel_url=f"{base_url}/configurar-premium/{lista_id}",
                metadata={"lista_id": lista_id, "pacote": "convite_ia"}
            )
            return jsonify({"limite_atingido": True, "pagamento_url": session.url})
        except Exception as e:
            print("Stripe IA limite erro:", e)
            return jsonify({"erro": "Erro ao criar pagamento"}), 500

    try:
        data_fmt = ""
        if data_evento_str:
            try:
                d = datetime.fromisoformat(data_evento_str)
                meses = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"]
                data_fmt = f"{d.day} de {meses[d.month-1]} de {d.year}"
            except: data_fmt = data_evento_str

        prompt_texto = f"""Crie um convite digital DESLUMBRANTE e SOFISTICADO como SVG 800x600px.

Evento: {nome_evento or "Celebração Especial"}
Data: {data_fmt or "Em breve"}
Estilo solicitado: {descricao}

INSTRUÇÕES DETALHADAS:
- Fundo com gradiente rico e profundo no tema solicitado
- Título principal do evento em fonte grande, elegante e bem legível
- Data formatada com destaque especial e artístico
- Elementos decorativos elaborados: flores, estrelas, ornamentos, molduras, padrões geométricos conforme o tema
- Subtítulos e textos de apoio bem posicionados
- Layout equilibrado com espaçamento generoso
- Cores harmoniosas, saturadas e sofisticadas
- Bordas decorativas ou molduras elegantes
- Pelo menos 3 camadas de elementos visuais (fundo, decoração, texto)
- SVG completamente auto-contido, sem imagens externas
- Mínimo de 50 elementos SVG para máxima riqueza visual

Retorne APENAS o código SVG completo começando com <svg, sem markdown, sem explicações."""

        content = [{"type": "text", "text": prompt_texto}]
        if imagem_ref_b64 and len(imagem_ref_b64) > 100:
            if "," in imagem_ref_b64:
                header, b64data = imagem_ref_b64.split(",", 1)
                media_type = header.split(":")[1].split(";")[0] if ":" in header else "image/jpeg"
            else:
                b64data, media_type = imagem_ref_b64, "image/jpeg"
            content = [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64data}},
                {"type": "text", "text": prompt_texto + "\n\nUse a imagem de referência acima como inspiração para o estilo visual."}
            ]

        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            system="Você é um designer gráfico de elite especializado em convites digitais de luxo. Cria SVGs extremamente detalhados, ricos e visualmente impressionantes. Sempre retorna APENAS o código SVG começando com <svg, sem markdown, sem explicações. Seus convites têm no mínimo 50 elementos visuais e são verdadeiras obras de arte digitais.",
            messages=[{"role": "user", "content": content}]
        )
        svg_text = resp.content[0].text.strip()
        if not svg_text.startswith("<svg"):
            m = re.search(r'<svg.*?</svg>', svg_text, re.DOTALL)
            svg_text = m.group(0) if m else svg_text
        svg_b64 = base64.b64encode(svg_text.encode('utf-8')).decode('utf-8')
        imagem_data = f"data:image/svg+xml;base64,{svg_b64}"

        # ✦ Incrementa contador de gerações
        nova_geracao = ia_geracoes + 1
        restantes = LIMITE_GERACOES - nova_geracao
        upd = {"convite_ia_imagem": imagem_data, "ia_pago": True, "estilo_convite": "ia", "ia_geracoes": nova_geracao}
        if config_existe:
            sb_patch("config_premium", f"lista_id=eq.{lista_id}", upd)
        else:
            upd["lista_id"] = lista_id
            sb_post("config_premium", upd)

        try:
            sb_post("vendas", {"lista_id": lista_id, "pacote": "convite_ia", "valor": 9.90})
        except: pass

        # ✦ Mensagem de aviso conforme gerações restantes
        if restantes == 2:
            aviso = "✨ Convite gerado! Você ainda tem 2 gerações disponíveis."
        elif restantes == 1:
            aviso = "⚠️ Atenção! Esta foi sua penúltima geração. Aproveite bem a próxima — é a última!"
        elif restantes == 0:
            aviso = "🎨 Esta foi sua última geração incluída. Para criar um novo convite, será necessário adquirir novamente por R$ 9,90."
        else:
            aviso = f"✨ Convite gerado! Você ainda tem {restantes} geração(ões) disponível(eis)."

        return jsonify({"ok": True, "imagem": imagem_data, "geracoes_restantes": restantes, "aviso": aviso})
    except Exception as e:
        print("Gerar convite IA erro:", e)
        return jsonify({"erro": f"Erro ao gerar: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
