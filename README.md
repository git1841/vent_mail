# Email Market Pro - MySQL Version

Plateforme d'achat/vente d'emails - FastAPI + MySQL + JWT

## Configuration MySQL

Modifiez les parametres de connexion dans `database.py`:

```python
MYSQL_CONFIG = {
    "host": "localhost",       # Adresse du serveur MySQL
    "user": "root",            # Nom d'utilisateur MySQL
    "password": "",            # Mot de passe MySQL
    "database": "email_market", # Nom de la base de donnees
    "port": 3306               # Port MySQL
}
```

## Installation

1. Installez les dependances:
```bash
pip install -r requirements.txt
```

2. Assurez-vous que MySQL est en cours d'execution et accessible.

3. Lancez l'application:
```bash
python main.py
```

L'application cree automatiquement la base de donnees et les tables si elles n'existent pas.

## Compte Admin par defaut

- Nom: `admin`
- Mot de passe: `admin123`

## Caracteristiques

- Mots de passe stockes EN CLAIR (non cryptes) dans MySQL
- Affichage complet des mots de passe dans le panneau admin
- Authentification JWT
- Gestion des emails avec statuts: en_attente, valide, rejete, paye
- Wallet client avec transactions
- Gestion du prix par email via l'admin
