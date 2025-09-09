
from flask import Flask, request, jsonify
import sqlite3
import subprocess
import re
from typing import List, Dict, Any
import sys
from datetime import datetime

app = Flask(__name__)

DB_FILE = "winget_packages.db"

# Initialiser la DB
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            package_id TEXT UNIQUE NOT NULL,
            version TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Parser la sortie de winget list
def parse_winget_output(output: str) -> List[Dict[str, str]]:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Début du parsing de la sortie winget...")
    packages = []
    lines = output.strip().split('\n')
    if len(lines) < 2:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Aucune donnée valide à parser.")
        return packages
    
    # Trouver les indices des colonnes (Name, Id, Version)
    header = lines[0].lower()
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = re.split(r'\s{2,}', line.strip())  # Split sur multiples espaces/tabs
        if len(parts) >= 3:  # Name, Id, Version au minimum
            packages.append({
                'name': parts[0].strip(),
                'package_id': parts[1].strip(),
                'version': parts[2].strip()
            })
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {len(packages)} packages parsés.")
    return packages

# Route pour rafraîchir la DB via winget
@app.route('/api/refresh', methods=['POST'])
def refresh_packages():
    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Lancement de winget list...")
        result = subprocess.run(
            ['winget', 'list', '--accept-source-agreements'],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Erreur winget: {result.stderr}")
            return jsonify({"error": f"Erreur winget: {result.stderr}"}), 500
        
        parsed_packages = parse_winget_output(result.stdout)
        if not parsed_packages:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Aucun package à insérer.")
            return jsonify({"error": "Aucun package parsé"}), 400
        
        # Stocker en DB avec progression
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        total = len(parsed_packages)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Insertion de {total} packages dans la base...")
        
        for i, pkg in enumerate(parsed_packages, 1):
            cursor.execute("""
                INSERT OR REPLACE INTO packages (name, package_id, version)
                VALUES (?, ?, ?)
            """, (pkg['name'], pkg['package_id'], pkg['version']))
            if i % 50 == 0 or i == total:  # Afficher tous les 50 packages ou à la fin
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {i}/{total} packages insérés...")
        
        conn.commit()
        conn.close()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Insertion terminée : {total} packages.")
        
        return jsonify({
            "success": True,
            "count": total,
            "message": f"{total} packages stockés/mis à jour"
        })
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Erreur: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Fonction pour interroger la DB
def query_packages(query: str = "", publisher: str = "", sort: str = "name", page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Construire WHERE
    conditions = []
    params = []
    if query:
        conditions.append("(name LIKE ? OR package_id LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
    if publisher:
        conditions.append("package_id LIKE ?")
        params.append(f"%{publisher}%")
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    # Compter total
    cursor.execute(f"SELECT COUNT(*) FROM packages {where_clause}", params)
    total = cursor.fetchone()[0]
    
    # Trier
    order_by = f"ORDER BY {sort}" if sort in ["name", "package_id", "version"] else "ORDER BY name"
    
    # Pagination
    offset = (page - 1) * page_size
    cursor.execute(f"""
        SELECT name, package_id, version FROM packages
        {where_clause} {order_by} LIMIT ? OFFSET ?
    """, params + [page_size, offset])
    
    packages = [{"name": row[0], "package_id": row[1], "version": row[2]} for row in cursor.fetchall()]
    
    conn.close()
    return {
        "Packages": packages,
        "Total": total,
        "CurrentPage": page,
        "TotalPages": (total + page_size - 1) // page_size
    }

# Route pour interroger les packages
@app.route('/api/packages', methods=['GET'])
def get_packages():
    query = request.args.get('query', '').strip()
    publisher = request.args.get('publisher', '').strip()
    sort = request.args.get('sort', 'name')
    page = max(1, int(request.args.get('page', 1)))
    page_size = min(100, max(1, int(request.args.get('pageSize', 50))))
    
    result = query_packages(query, publisher, sort, page, page_size)
    return jsonify(result)

# Route pour packages Microsoft
@app.route('/api/packages/microsoft', methods=['GET'])
def get_microsoft_packages():
    page = max(1, int(request.args.get('page', 1)))
    page_size = min(100, max(1, int(request.args.get('pageSize', 50))))
    sort = request.args.get('sort', 'name')
    
    result = query_packages(publisher="Microsoft", sort=sort, page=page, page_size=page_size)
    return jsonify(result)

if __name__ == '__main__':
    init_db()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Lancement du serveur Flask sur le port 4006...")
    app.run(debug=True, host='0.0.0.0', port=4006)
