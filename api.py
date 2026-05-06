from flask import Flask, render_template, request, jsonify
import uuid, re, requests, resend
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

app = Flask(__name__, template_folder="templates")

SUPABASE_URL = "https://xmivfkpywjbrcrkniqbu.supabase.co"
SUPABASE_KEY = "sb_secret_0M-YowSnhrciNuzmJMS7AQ_QwA9GUjz"
SCRAPER_KEY = "3388267b140bf86c58e9ab0c2057c124"
AMAZON_TAG = "instagift20-20"
ML_ID = "DaniloBasilio40"
SHOPEE_ID = "18374451025"
ML_CLIENT_ID = "5415799706798482"
ML_CLIENT_SECRET = "GIPTdLAoQf4CKVycmLCr9WhAeV4sA2Pq"
RESEND_KEY = "re_BMvckQ8G_KZdPini3AxGzHUTirGtsiixC"

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

        m2 = re.search(r'MLB[-_]?(\d+)', link_limpo, re.IGNORECASE)
        if m2:
            item_id = f"MLB{m2.group(1)}"
            r = requests.get(f"https://api.mercadolibre.com/items/{item_id}", headers=auth, timeout=10).json()
            if r.get("status") == 403 or "UNAUTHORIZED" in str(r.get("code", "")):
                try:
                    r_search = requests.get(
                        f"https://api.mercadolibre.com/sites/MLB/search?q={item_id}&limit=1",
                        headers=auth, timeout=8
                    ).json()
                    resultados = r_search.get("results", [])
                    if resultados:
                        prod = resultados[0]
                        nome = prod.get("title", "")[:100]
                        preco = str(prod.get("price", "")).replace(".", ",")
                        return nome, "", preco
                except:
                    pass
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

def extrair_shopee(link):
    try:
        m = re.search(r'i\.(\d+)\.(\d+)', link)
        if not m:
            return "", "", ""
        html = requests.get(
            f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={link}&render=false&country_code=br",
            timeout=20
        ).text
        soup = BeautifulSoup(html, "html.parser")
        nome = ""
        t = soup.find("meta", property="og:title")
        if t:
            nome = t.get("content", "")[:100]
            nome = re.sub(r'\s*[:|]\s*Shopee.*$', '', nome)
        imagem = ""
        i = soup.find("meta", property="og:image")
        if i:
            imagem = i.get("content", "")
        return nome, imagem, ""
    except Exception as e:
        print("Shopee erro:", e)
        return "", "", ""

def extrair_dados(link, plataforma):
    if plataforma == "shopee":
        n, i, p = extrair_shopee(link)
        if n:
            return n, i, p
    if plataforma == "mercadolivre":
        n, i, p = extrair_ml(link)
        if n:
            return n, i, p

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
                timeout=25
            ).text
        except Exception as e:
            print("ScraperAPI erro:", e)
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

def enviar_email_comprador(email_comprador, nome_comprador, nome_produto, token, base_url, link_produto=""):
    link_confirmacao = f"{base_url}/confirmar-compra/{token}"
    link_btn = f'<a href="{link_produto}" style="display:block;background:#1a1a2e;color:#8A63D2;text-align:center;padding:14px;border-radius:12px;font-size:14px;font-weight:700;text-decoration:none;margin-bottom:16px;border:1px solid rgba(138,99,210,0.3);">🛍️ Acessar o presente novamente</a>' if link_produto else ""
    try:
        resend.Emails.send({
            "from": "InstaGift <onboarding@resend.dev>",
            "to": email_comprador,
            "subject": "🎁 Confirme que você comprou o presente!",
            "html": f"""
            <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#0D0D0D;color:#fff;padding:32px;border-radius:16px;">
                <div style="text-align:center;margin-bottom:24px;">
                    <div style="font-size:48px;margin-bottom:8px;">🎁</div>
                    <h2 style="color:#8A63D2;margin-bottom:4px;">Olá, {nome_comprador}!</h2>
                    <p style="color:#666;font-size:13px;">Sua reserva está confirmada</p>
                </div>
                <div style="background:#1a1a1a;border-radius:12px;padding:16px;margin-bottom:24px;">
                    <p style="color:#888;font-size:12px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">Presente reservado</p>
                    <p style="color:#fff;font-weight:700;font-size:16px;">{nome_produto}</p>
                </div>
                <p style="color:#aaa;margin-bottom:16px;line-height:1.6;">Após finalizar sua compra, clique no botão abaixo para confirmar. Assim a pessoa especial saberá que vai receber esse presente! 💜</p>
                {link_btn}
                <a href="{link_confirmacao}" style="display:block;background:#22c55e;color:#fff;text-align:center;padding:18px;border-radius:12px;font-size:16px;font-weight:700;text-decoration:none;margin-bottom:24px;">✅ Sim, eu comprei o presente!</a>
                <div style="background:#1a1a1a;border-radius:10px;padding:14px;margin-bottom:24px;">
                    <p style="color:#666;font-size:12px;line-height:1.6;">⏰ Este link expira em <strong style="color:#aaa;">3 horas</strong>. Se não confirmar dentro do prazo, o presente voltará a ficar disponível para outros.</p>
                </div>
                <p style="color:#444;font-size:12px;text-align:center;">Com carinho, InstaGift 💜</p>
            </div>
            """
        })
    except Exception as e:
        print("Erro email comprador:", e)

def enviar_email_aniversariante(email_aniversariante, nome_comprador, nome_produto):
    try:
        resend.Emails.send({
            "from": "InstaGift <onboarding@resend.dev>",
            "to": email_aniversariante,
            "subject": "🎉 Você ganhou um presente! Alguém te surpreendeu!",
            "html": f"""
            <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#0D0D0D;color:#fff;padding:32px;border-radius:16px;">
                <div style="text-align:center;margin-bottom:28px;">
                    <div style="font-size:56px;margin-bottom:12px;">🎉</div>
                    <h2 style="color:#8A63D2;font-size:22px;margin-bottom:6px;">Que surpresa incrível!</h2>
                    <p style="color:#888;font-size:13px;">Alguém especial pensou em você 💜</p>
                </div>
                <div style="background:linear-gradient(135deg,rgba(138,99,210,0.15),rgba(176,136,245,0.08));border:1px solid rgba(138,99,210,0.3);border-radius:16px;padding:24px;text-align:center;margin-bottom:24px;">
                    <p style="color:#b088f5;font-size:13px;margin-bottom:8px;">PRESENTE CONFIRMADO</p>
                    <p style="color:#fff;font-weight:700;font-size:18px;margin-bottom:12px;">{nome_produto}</p>
                    <p style="color:#888;font-size:13px;">presenteado com carinho por</p>
                    <p style="color:#fff;font-weight:600;font-size:16px;margin-top:4px;">{nome_comprador}</p>
                </div>
                <p style="color:#aaa;text-align:center;line-height:1.7;margin-bottom:24px;">A compra foi confirmada e seu presente está garantido! Que seu evento seja incrível e cheio de momentos especiais. 🎁✨</p>
                <p style="color:#444;font-size:12px;text-align:center;">Com muito carinho, InstaGift 💜</p>
            </div>
            """
        })
    except Exception as e:
        print("Erro email aniversariante:", e)

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
        nome = "Produto Shopee" if plataforma == "shopee" else "Produto"
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

@app.route("/api/liberar-produto/<int:produto_id>", methods=["POST"])
def liberar_produto(produto_id):
    sb_patch("produtos", f"id=eq.{produto_id}", {
        "reservado": 0,
        "token_confirmacao": None,
        "reservado_em": None,
        "nome_comprador": None,
        "email_comprador": None
    })
    return jsonify({"ok": True})

@app.route("/api/atualizar-nome-produto/<int:produto_id>", methods=["POST"])
def atualizar_nome_produto(produto_id):
    data = request.json or {}
    nome = data.get("nome", "").strip()
    if not nome:
        return jsonify({"erro": "Nome vazio"}), 400
    sb_patch("produtos", f"id=eq.{produto_id}", {"nome": nome})
    return jsonify({"ok": True})

@app.route("/api/reservar/<int:produto_id>", methods=["POST"])
def reservar(produto_id):
    data = request.json or {}
    nome_comprador = data.get("nome", "").strip()
    email_comprador = data.get("email", "").strip()

    if not nome_comprador or not email_comprador:
        return jsonify({"erro": "Nome e e-mail obrigatórios"}), 400

    produtos = sb_get("produtos", f"id=eq.{produto_id}")
    if not produtos or not isinstance(produtos, list):
        return jsonify({"erro": "Produto não encontrado"}), 404
    if produtos[0].get("reservado"):
        return jsonify({"erro": "Já reservado"}), 400

    token = str(uuid.uuid4())
    agora = datetime.utcnow().isoformat()

    sb_patch("produtos", f"id=eq.{produto_id}", {
        "reservado": 1,
        "token_confirmacao": token,
        "reservado_em": agora,
        "nome_comprador": nome_comprador,
        "email_comprador": email_comprador
    })

    nome_produto = produtos[0].get("nome", "Produto")
    link_produto = produtos[0].get("link_afiliado", "")
    base_url = request.host_url.rstrip('/')
    enviar_email_comprador(email_comprador, nome_comprador, nome_produto, token, base_url, link_produto)

    return jsonify({"ok": True})

@app.route("/confirmar-compra/<token>")
def confirmar_compra(token):
    produtos = sb_get("produtos", f"token_confirmacao=eq.{token}")
    if not produtos or not isinstance(produtos, list):
        return "<h2>Link inválido ou expirado.</h2>", 404

    produto = produtos[0]
    reservado_em = produto.get("reservado_em")

    if reservado_em:
        dt = datetime.fromisoformat(reservado_em.replace('Z', ''))
        if datetime.utcnow() > dt + timedelta(hours=3):
            sb_patch("produtos", f"id=eq.{produto['id']}", {
                "reservado": 0,
                "token_confirmacao": None,
                "reservado_em": None,
                "nome_comprador": None,
                "email_comprador": None
            })
            return render_template("confirmacao.html", status="expirado")

    sb_patch("produtos", f"id=eq.{produto['id']}", {
        "reservado": 2,
        "token_confirmacao": None
    })

    lista = sb_get("listas", f"id=eq.{produto['lista_id']}")
    if lista and isinstance(lista, list):
        email_aniversariante = lista[0].get("email_aniversariante")
        if email_aniversariante:
            enviar_email_aniversariante(
                email_aniversariante,
                produto.get("nome_comprador", "Alguém"),
                produto.get("nome", "Produto")
            )

    return render_template("confirmacao.html", status="confirmado", nome_produto=produto.get("nome", "Produto"))

@app.route("/api/limpar-reservas-expiradas", methods=["POST"])
def limpar_reservas_expiradas():
    try:
        agora = datetime.utcnow()
        prazo_limite = agora - timedelta(hours=3)
        produtos = sb_get("produtos", "reservado=eq.1")
        if not isinstance(produtos, list):
            return jsonify({"status": "sucesso", "liberados": 0}), 200
        liberados = 0
        for p in produtos:
            reservado_em = p.get("reservado_em")
            if reservado_em:
                dt_reserva = datetime.fromisoformat(reservado_em.replace('Z', ''))
                if dt_reserva < prazo_limite:
                    sb_patch("produtos", f"id=eq.{p['id']}", {
                        "reservado": 0,
                        "token_confirmacao": None,
                        "reservado_em": None,
                        "nome_comprador": None,
                        "email_comprador": None
                    })
                    liberados += 1
        return jsonify({"status": "sucesso", "liberados": liberados}), 200
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
