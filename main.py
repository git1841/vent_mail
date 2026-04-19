"""
Email Market Pro - Plateforme d'achat/vente d'emails
FastAPI + JWT + MySQL (mysql.connector)
Mots de passe stockes et affiches en CLAIR (non cryptes)
"""
from fastapi import FastAPI, Request, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import re
from fastapi.encoders import jsonable_encoder


from database import init_db, get_db, get_prix_email, set_prix_email

# Configuration
SECRET_KEY = "email-market-pro-secret-key-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# Initialisation
# app = FastAPI(title="Email Market Pro")
app = FastAPI(
    title="Email Market Pro",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialiser la DB au demarrage
@app.on_event("startup")
async def startup():
    init_db()

# ==================== FONCTIONS UTILITAIRES ====================

def verify_password(plain_password, stored_password):
    """Verification en CLAIR - pas de cryptage"""
    return plain_password == stored_password

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

async def get_current_client(request: Request):
    """Recupere le client connecte via le token JWT"""
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("role") != "client":
        return None
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM clients WHERE id = %s", (payload.get("user_id"),))
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None

async def get_current_admin(request: Request):
    """Recupere l'admin connecte via le token JWT"""
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("role") != "admin":
        return None
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins WHERE id = %s", (payload.get("user_id"),))
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None

def validate_madagascar_phone(phone: str, operateur: str) -> bool:
    """Valide le numero de telephone malgache"""
    phone = phone.replace(" ", "").replace("-", "")
    patterns = {
        "Telma": r"^(034|038)\d{7}$",
        "Orange": r"^(032|037)\d{7}$",
        "Airtel": r"^(033|039)\d{7}$"
    }
    pattern = patterns.get(operateur, r"^(03[2-9])\d{7}$")
    return bool(re.match(pattern, phone))

# ==================== ROUTES PUBLIQUES ====================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Page d'accueil"""
    client = await get_current_client(request)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "client": client,
        "prix_email": get_prix_email()
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Page de connexion"""
    client = await get_current_client(request)
    admin = await get_current_admin(request)
    if client:
        return RedirectResponse(url="/dashboard", status_code=302)
    if admin:
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None
    })

@app.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("client")
):
    """Traitement de la connexion - MOT DE PASSE EN CLAIR"""
    from database import get_db
    
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        if role == "admin":
            cursor.execute("SELECT * FROM admins WHERE nom = %s", (username,))
            user = cursor.fetchone()
            if not user or not verify_password(password, user["mot_de_passe"]):
                return templates.TemplateResponse("login.html", {
                    "request": request,
                    "error": "Nom d'utilisateur ou mot de passe incorrect"
                }, status_code=401)
            
            token = create_access_token({
                "user_id": user["id"],
                "role": "admin",
                "username": user["nom"]
            })
            response = RedirectResponse(url="/admin", status_code=302)
            response.set_cookie(key="access_token", value=token, httponly=True, max_age=604800)
            return response
        else:
            cursor.execute("SELECT * FROM clients WHERE nom_utilisateur = %s", (username,))
            user = cursor.fetchone()
            if not user or not verify_password(password, user["mot_de_passe"]):
                return templates.TemplateResponse("login.html", {
                    "request": request,
                    "error": "Nom d'utilisateur ou mot de passe incorrect"
                }, status_code=401)
            
            token = create_access_token({
                "user_id": user["id"],
                "role": "client",
                "username": user["nom_utilisateur"]
            })
            response = RedirectResponse(url="/dashboard", status_code=302)
            response.set_cookie(key="access_token", value=token, httponly=True, max_age=604800)
            return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Page d'inscription"""
    client = await get_current_client(request)
    if client:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("register.html", {
        "request": request,
        "error": None
    })

@app.post("/register")
async def register_post(
    request: Request,
    nom_utilisateur: str = Form(...),
    mot_de_passe: str = Form(...),
    confirm_password: str = Form(...),
    telephone: str = Form(...),
    operateur: str = Form(...)
):
    """Traitement de l'inscription - MOT DE PASSE EN CLAIR"""
    from database import get_db
    
    # Validations
    if mot_de_passe != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Les mots de passe ne correspondent pas"
        }, status_code=400)
    
    if len(mot_de_passe) < 6:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Le mot de passe doit contenir au moins 6 caracteres"
        }, status_code=400)
    
    if not validate_madagascar_phone(telephone, operateur):
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": f"Numero invalide pour {operateur}. Format: 0{operateur[1:3]}XXXXXXX"
        }, status_code=400)
    
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Verifier si le nom d'utilisateur existe
        cursor.execute("SELECT id FROM clients WHERE nom_utilisateur = %s", (nom_utilisateur,))
        if cursor.fetchone():
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Ce nom d'utilisateur est deja pris"
            }, status_code=400)
        
        # INSERER LE MOT DE PASSE EN CLAIR (pas de hash)
        cursor.execute("""
            INSERT INTO clients (nom_utilisateur, mot_de_passe, telephone, operateur, solde, nb_emails)
            VALUES (%s, %s, %s, %s, 0.0, 0)
        """, (nom_utilisateur, mot_de_passe, telephone, operateur))
        
        conn.commit()
        
        # Rediriger vers la page de connexion
        response = RedirectResponse(url="/login", status_code=302)
        return response

@app.get("/logout")
async def logout():
    """Deconnexion"""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response

# ==================== ROUTES CLIENT ====================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, client: dict = Depends(get_current_client)):
    """Tableau de bord client"""
    if not client:
        return RedirectResponse(url="/login", status_code=302)
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Stats
        cursor.execute("SELECT COUNT(*) as total FROM emails WHERE client_id = %s", (client["id"],))
        total_emails = cursor.fetchone()["total"]
        
        cursor.execute("""
            SELECT COUNT(*) as en_attente FROM emails 
            WHERE client_id = %s AND statut = 'en_attente'
        """, (client["id"],))
        en_attente = cursor.fetchone()["en_attente"]
        
        cursor.execute("""
            SELECT COUNT(*) as valides FROM emails 
            WHERE client_id = %s AND statut = 'valide'
        """, (client["id"],))
        valides = cursor.fetchone()["valides"]
        
        cursor.execute("""
            SELECT COUNT(*) as payes FROM emails 
            WHERE client_id = %s AND statut = 'paye'
        """, (client["id"],))
        payes = cursor.fetchone()["payes"]
        
        # Derniers emails
        cursor.execute("""
            SELECT * FROM emails WHERE client_id = %s 
            ORDER BY created_at DESC LIMIT 10
        """, (client["id"],))
        emails = [dict(row) for row in cursor.fetchall()]
        
        # Dernieres transactions
        cursor.execute("""
            SELECT * FROM transactions WHERE client_id = %s 
            ORDER BY created_at DESC LIMIT 5
        """, (client["id"],))
        transactions = [dict(row) for row in cursor.fetchall()]
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "client": client,
        "prix_email": get_prix_email(),
        "stats": {
            "total_emails": total_emails,
            "en_attente": en_attente,
            "valides": valides,
            "payes": payes,
            "solde": client["solde"]
        },
        "emails": emails,
        "transactions": transactions
    })

@app.get("/emails/add", response_class=HTMLResponse)
async def add_email_page(request: Request, client: dict = Depends(get_current_client)):
    """Page d'ajout d'emails"""
    if not client:
        return RedirectResponse(url="/login", status_code=302)
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM emails WHERE client_id = %s AND statut = 'en_attente'
            ORDER BY created_at DESC
        """, (client["id"],))
        pending_emails = [dict(row) for row in cursor.fetchall()]
    
    return templates.TemplateResponse("add_emails.html", {
        "request": request,
        "client": client,
        "prix_email": get_prix_email(),
        "pending_emails": pending_emails
    })

@app.post("/emails/add")
async def add_email_post(
    request: Request,
    email: str = Form(...),
    mot_de_passe: str = Form(...),
    type_email: str = Form("Autre"),
    client: dict = Depends(get_current_client)
):
    """Ajouter un email - MOT DE PASSE EN CLAIR"""
    if not client:
        raise HTTPException(status_code=401, detail="Non authentifie")
    
    from database import get_db
    prix = get_prix_email()
    
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            INSERT INTO emails (client_id, email, mot_de_passe, type_email, prix, statut)
            VALUES (%s, %s, %s, %s, %s, 'en_attente')
        """, (client["id"], email, mot_de_passe, type_email, prix))
        conn.commit()
    
    return RedirectResponse(url="/emails/add", status_code=302)

@app.post("/emails/add-bulk")
async def add_email_bulk(
    request: Request,
    emails_bulk: str = Form(...),
    type_email: str = Form("Autre"),
    client: dict = Depends(get_current_client)
):
    """Ajouter plusieurs emails en vrac (format: email:password par ligne) - EN CLAIR"""
    if not client:
        raise HTTPException(status_code=401, detail="Non authentifie")
    
    from database import get_db
    prix = get_prix_email()
    
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        lignes = emails_bulk.strip().split('\n')
        count = 0
        for ligne in lignes:
            ligne = ligne.strip()
            if not ligne:
                continue
            parts = ligne.split(':', 1)
            if len(parts) == 2:
                email, password = parts[0].strip(), parts[1].strip()
                if email and password:
                    cursor.execute("""
                        INSERT INTO emails (client_id, email, mot_de_passe, type_email, prix, statut)
                        VALUES (%s, %s, %s, %s, %s, 'en_attente')
                    """, (client["id"], email, password, type_email, prix))
                    count += 1
        conn.commit()
    
    return RedirectResponse(url="/emails/add", status_code=302)

@app.get("/emails/delete/{email_id}")
async def delete_email(email_id: int, client: dict = Depends(get_current_client)):
    """Supprimer un email en attente"""
    if not client:
        raise HTTPException(status_code=401, detail="Non authentifie")
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            DELETE FROM emails WHERE id = %s AND client_id = %s AND statut = 'en_attente'
        """, (email_id, client["id"]))
        conn.commit()
    
    return RedirectResponse(url="/emails/add", status_code=302)

@app.get("/mes-emails", response_class=HTMLResponse)
async def mes_emails(request: Request, client: dict = Depends(get_current_client)):
    """Page de tous les emails du client"""
    if not client:
        return RedirectResponse(url="/login", status_code=302)
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM emails WHERE client_id = %s 
            ORDER BY created_at DESC
        """, (client["id"],))
        emails = [dict(row) for row in cursor.fetchall()]
    
    return templates.TemplateResponse("mes_emails.html", {
        "request": request,
        "client": client,
        "emails": emails,
        "prix_email": get_prix_email()
    })

@app.get("/mon-compte", response_class=HTMLResponse)
async def mon_compte(request: Request, client: dict = Depends(get_current_client)):
    """Page de compte client"""
    if not client:
        return RedirectResponse(url="/login", status_code=302)
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM transactions WHERE client_id = %s 
            ORDER BY created_at DESC LIMIT 20
        """, (client["id"],))
        transactions = [dict(row) for row in cursor.fetchall()]
    
    return templates.TemplateResponse("mon_compte.html", {
        "request": request,
        "client": client,
        "transactions": transactions
    })

# ==================== ROUTES ADMIN ====================

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, admin: dict = Depends(get_current_admin)):
    """Tableau de bord admin"""
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Stats globales
        cursor.execute("SELECT COUNT(*) as total FROM clients")
        total_clients = cursor.fetchone()["total"]
        
        cursor.execute("SELECT COUNT(*) as total FROM emails")
        total_emails = cursor.fetchone()["total"]
        
        # Emails aujourd'hui (MySQL syntax)
        cursor.execute("SELECT COUNT(*) as today FROM emails WHERE DATE(created_at) = CURDATE()")
        emails_today = cursor.fetchone()["today"]
        
        cursor.execute("""
            SELECT COUNT(*) as en_attente FROM emails WHERE statut = 'en_attente'
        """)
        en_attente = cursor.fetchone()["en_attente"]
        
        cursor.execute("""
            SELECT COUNT(*) as valides FROM emails WHERE statut = 'valide'
        """)
        valides_count = cursor.fetchone()["valides"]
        
        cursor.execute("""
            SELECT SUM(prix) as total FROM emails WHERE statut = 'valide'
        """)
        a_payer = cursor.fetchone()["total"] or 0
        
        # Emails en attente avec info client
        cursor.execute("""
            SELECT e.*, c.nom_utilisateur, c.telephone, c.operateur, c.mot_de_passe as client_password
            FROM emails e
            JOIN clients c ON e.client_id = c.id
            WHERE e.statut = 'en_attente'
            ORDER BY e.created_at DESC
        """)
        pending_emails = [dict(row) for row in cursor.fetchall()]
        
        # Tous les emails recents
        cursor.execute("""
            SELECT e.*, c.nom_utilisateur, c.telephone, c.operateur, c.mot_de_passe as client_password
            FROM emails e
            JOIN clients c ON e.client_id = c.id
            ORDER BY e.created_at DESC LIMIT 50
        """)
        all_emails = [dict(row) for row in cursor.fetchall()]
        
        # Tous les clients avec mot de passe en CLAIR
        cursor.execute("""
            SELECT c.*, COUNT(e.id) as total_emails
            FROM clients c
            LEFT JOIN emails e ON c.id = e.client_id
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """)
        clients = [dict(row) for row in cursor.fetchall()]
    
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "admin": admin,
        "prix_email": get_prix_email(),
        "stats": {
            "total_clients": total_clients,
            "total_emails": total_emails,
            "emails_today": emails_today,
            "en_attente": en_attente,
            "valides": valides_count,
            "a_payer": a_payer
        },
        "pending_emails": pending_emails,
        "all_emails": all_emails,
        "clients": clients
    })

@app.get("/admin/email/{email_id}/valider")
async def valider_email(email_id: int, admin: dict = Depends(get_current_admin)):
    """Valider un email (admin)"""
    if not admin:
        raise HTTPException(status_code=401, detail="Non autorise")
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            UPDATE emails SET statut = 'valide', validated_at = NOW() WHERE id = %s
        """, (email_id,))
        conn.commit()
    
    return RedirectResponse(url="/admin", status_code=302)

@app.get("/admin/email/{email_id}/rejeter")
async def rejeter_email(email_id: int, admin: dict = Depends(get_current_admin)):
    """Rejeter un email (admin)"""
    if not admin:
        raise HTTPException(status_code=401, detail="Non autorise")
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            UPDATE emails SET statut = 'rejete' WHERE id = %s
        """, (email_id,))
        conn.commit()
    
    return RedirectResponse(url="/admin", status_code=302)

@app.get("/admin/email/{email_id}/payer")
async def payer_email(email_id: int, admin: dict = Depends(get_current_admin)):
    """Payer un email valide (admin) - ajoute l'argent au wallet du client"""
    if not admin:
        raise HTTPException(status_code=401, detail="Non autorise")
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Recuperer l'email et le client
        cursor.execute("SELECT * FROM emails WHERE id = %s AND statut = 'valide'", (email_id,))
        email_row = cursor.fetchone()
        
        if not email_row:
            raise HTTPException(status_code=404, detail="Email non trouve ou non valide")
        
        client_id = email_row["client_id"]
        prix = email_row["prix"]
        email_addr = email_row["email"]
        
        # Mettre a jour le statut de l'email
        cursor.execute("""
            UPDATE emails SET statut = 'paye', paye_at = NOW() WHERE id = %s
        """, (email_id,))
        
        # Ajouter l'argent au wallet du client
        cursor.execute("""
            UPDATE clients SET solde = solde + %s, nb_emails = nb_emails + 1 WHERE id = %s
        """, (prix, client_id))
        
        # Creer une transaction
        cursor.execute("""
            INSERT INTO transactions (client_id, montant, type, description)
            VALUES (%s, %s, 'credit', %s)
        """, (client_id, prix, f"Paiement email: {email_addr}"))
        
        conn.commit()
    
    return RedirectResponse(url="/admin", status_code=302)

@app.post("/admin/client/{client_id}/wallet")
async def modifier_wallet(
    client_id: int,
    montant: float = Form(...),
    type_op: str = Form("ajouter"),
    description: str = Form(""),
    admin: dict = Depends(get_current_admin)
):
    """Ajouter ou retirer de l'argent du wallet d'un client"""
    if not admin:
        raise HTTPException(status_code=401, detail="Non autorise")
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        if type_op == "ajouter":
            cursor.execute("UPDATE clients SET solde = solde + %s WHERE id = %s", (montant, client_id))
            cursor.execute("""
                INSERT INTO transactions (client_id, montant, type, description)
                VALUES (%s, %s, 'credit', %s)
            """, (client_id, montant, description or "Ajout manuel admin"))
        else:
            # Verifier que le solde est suffisant
            cursor.execute("SELECT solde FROM clients WHERE id = %s", (client_id,))
            row = cursor.fetchone()
            if row and row["solde"] >= montant:
                cursor.execute("UPDATE clients SET solde = solde - %s WHERE id = %s", (montant, client_id))
                cursor.execute("""
                    INSERT INTO transactions (client_id, montant, type, description)
                    VALUES (%s, %s, 'debit', %s)
                """, (client_id, montant, description or "Retrait manuel admin"))
            else:
                raise HTTPException(status_code=400, detail="Solde insuffisant")
        
        conn.commit()
    
    return RedirectResponse(url="/admin", status_code=302)

@app.get("/admin/client/{client_id}")
async def client_detail_api(client_id: int, admin: dict = Depends(get_current_admin)):
    """API pour les details d'un client (pour le modal) - MOT DE PASSE EN CLAIR"""
    if not admin:
        raise HTTPException(status_code=401, detail="Non autorise")
    
    from database import get_db
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
        client_row = cursor.fetchone()
        
        if not client_row:
            raise HTTPException(status_code=404, detail="Client non trouve")
        
        cursor.execute("""
            SELECT * FROM emails WHERE client_id = %s ORDER BY created_at DESC LIMIT 10
        """, (client_id,))
        emails = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT * FROM transactions WHERE client_id = %s ORDER BY created_at DESC LIMIT 10
        """, (client_id,))
        transactions = [dict(row) for row in cursor.fetchall()]
    
    # return JSONResponse({
    #     "client": dict(client_row),
    #     "emails": emails,
    #     "transactions": transactions
        
    # })

    return JSONResponse(jsonable_encoder({
        "client": client_row,
        "emails": emails,
        "transactions": transactions
    }))

@app.post("/admin/parametres/prix")
async def update_prix(
    nouveau_prix: float = Form(...),
    admin: dict = Depends(get_current_admin)
):
    """Modifier le prix des emails"""
    if not admin:
        raise HTTPException(status_code=401, detail="Non autorise")
    
    set_prix_email(nouveau_prix)
    return RedirectResponse(url="/admin", status_code=302)







# ==================== LANCEMENT ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
