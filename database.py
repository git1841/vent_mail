"""
Module de base de donnees - MySQL avec mysql.connector
Toutes les donnees sont stockees en texte clair (pas de cryptage)
"""
import mysql.connector
from mysql.connector import Error
from datetime import datetime
from contextlib import contextmanager

# Configuration MySQL - MODIFIEZ CES PARAMETRES SELON VOTRE SERVEUR
# MYSQL_CONFIG = {
#     "host": "localhost",       # Adresse du serveur MySQL
#     "user": "root",            # Nom d'utilisateur MySQL
#     "password": "",            # Mot de passe MySQL (vide par defaut sur XAMPP)
#     "database": "email_market", # Nom de la base de donnees
#     "port": 3306               # Port MySQL (3306 par defaut)
# }

MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "user": "appuser",
    "password": "password",
    "database": "email_market",
    "port": 3307
}

def get_connection():
    """Cree et retourne une connexion MySQL"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        return conn
    except Error as e:
        print(f"Erreur de connexion MySQL: {e}")
        # Si la base de donnees n'existe pas, essayer de se connecter sans database
        if "Unknown database" in str(e):
            try:
                temp_config = MYSQL_CONFIG.copy()
                del temp_config["database"]
                conn = mysql.connector.connect(**temp_config)
                cursor = conn.cursor()
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_CONFIG['database']} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                conn.commit()
                cursor.close()
                conn.close()
                # Reconnecter avec la base de donnees
                conn = mysql.connector.connect(**MYSQL_CONFIG)
                return conn
            except Error as e2:
                print(f"Erreur lors de la creation de la base de donnees: {e2}")
                raise
        raise

@contextmanager
def get_db():
    """Context manager pour les connexions MySQL"""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def init_db():
    """Initialise la base de donnees avec toutes les tables"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Table des clients - MOT DE PASSE EN CLAIR
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nom_utilisateur VARCHAR(100) UNIQUE NOT NULL,
                mot_de_passe VARCHAR(255) NOT NULL,
                telephone VARCHAR(20) NOT NULL,
                operateur VARCHAR(20) NOT NULL,
                solde DECIMAL(12,2) DEFAULT 0.0,
                nb_emails INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Table des admins - MOT DE PASSE EN CLAIR
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nom VARCHAR(100) UNIQUE NOT NULL,
                mot_de_passe VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Table des emails soumis - MOT DE PASSE EN CLAIR
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id INT NOT NULL,
                email VARCHAR(255) NOT NULL,
                mot_de_passe VARCHAR(255) NOT NULL,
                type_email VARCHAR(50) DEFAULT 'Autre',
                prix DECIMAL(10,2) DEFAULT 0.0,
                statut VARCHAR(20) DEFAULT 'en_attente',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                validated_at TIMESTAMP NULL,
                paye_at TIMESTAMP NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Table des transactions (wallet)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id INT NOT NULL,
                montant DECIMAL(12,2) NOT NULL,
                type VARCHAR(20) NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Table des parametres (prix des emails)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parametres (
                id INT AUTO_INCREMENT PRIMARY KEY,
                cle VARCHAR(100) UNIQUE NOT NULL,
                valeur VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Insertion des parametres par defaut (IGNORE pour eviter les doublons)
        cursor.execute("""
            INSERT IGNORE INTO parametres (cle, valeur) VALUES 
            ('prix_email', '500'),
            ('nom_site', 'Email Market Pro'),
            ('devise', 'Ar')
        """)
        
        # Insertion d'un admin par defaut (admin/admin123) - EN CLAIR
        cursor.execute("""
            INSERT IGNORE INTO admins (nom, mot_de_passe) VALUES (%s, %s)
        """, ("admin", "admin123"))
        
        conn.commit()
        print("Base de donnees MySQL initialisee avec succes!")
        
    except Error as e:
        print(f"Erreur lors de l'initialisation: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def get_prix_email():
    """Recupere le prix actuel d'un email"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT valeur FROM parametres WHERE cle = 'prix_email'")
        row = cursor.fetchone()
        return float(row['valeur']) if row else 500.0

def set_prix_email(nouveau_prix):
    """Modifie le prix d'un email"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "UPDATE parametres SET valeur = %s WHERE cle = 'prix_email'",
            (str(nouveau_prix),)
        )
        conn.commit()
