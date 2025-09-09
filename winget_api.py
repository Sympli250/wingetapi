
from flask import Flask, request, jsonify, Response
import sqlite3
import subprocess
import re
from typing import List, Dict, Any
from datetime import datetime
import sys
import json
GREEN = "\033[92m"
RESET = "\033[0m"

app = Flask(__name__)

DB_FILE = "winget_packages.db"


def log_with_time(message: str) -> None:
    """Print a timestamped log message."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def print_progress(current: int, total: int) -> None:
    """Display a colored progress bar."""
    bar_length = 30
    progress = current / total if total else 0
    filled = int(bar_length * progress)
    bar = GREEN + "#" * filled + RESET + "-" * (bar_length - filled)
    sys.stdout.write(
        f"\r[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{bar}] {current}/{total} ({progress*100:.1f}%)"
    )
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")

# Swagger/OpenAPI specification
SWAGGER_SPEC = {
    "openapi": "3.0.2",
    "info": {"title": "Winget API", "version": "1.0"},
    "paths": {
        "/api/refresh": {
            "post": {
                "summary": "Rafraîchir la liste des packages via winget",
                "responses": {
                    "200": {"description": "Packages mis à jour"},
                    "400": {"description": "Erreur de parsing"},
                    "500": {"description": "Erreur winget"},
                },
            }
        },
        "/api/fullupdate": {
            "post": {
                "summary": "Mettre à jour les packages via winget search JSON",
                "responses": {
                    "200": {"description": "Packages mis à jour"},
                    "400": {"description": "Erreur de parsing"},
                    "500": {"description": "Erreur winget"},
                },
            }
        },
        "/api/packages": {
            "get": {
                "summary": "Lister les packages",
                "parameters": [
                    {"name": "query", "in": "query", "schema": {"type": "string"}},
                    {"name": "publisher", "in": "query", "schema": {"type": "string"}},
                    {
                        "name": "sort",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": ["name", "package_id", "version"],
                        },
                    },
                    {
                        "name": "page",
                        "in": "query",
                        "schema": {"type": "integer", "default": 1},
                    },
                    {
                        "name": "pageSize",
                        "in": "query",
                        "schema": {"type": "integer", "default": 50},
                    },
                ],
                "responses": {"200": {"description": "Liste de packages"}},
            }
        },
        "/api/packages/microsoft": {
            "get": {
                "summary": "Lister les packages Microsoft",
                "parameters": [
                    {
                        "name": "page",
                        "in": "query",
                        "schema": {"type": "integer", "default": 1},
                    },
                    {
                        "name": "pageSize",
                        "in": "query",
                        "schema": {"type": "integer", "default": 50},
                    },
                    {
                        "name": "sort",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": ["name", "package_id", "version"],
                        },
                    },
                ],
                "responses": {"200": {"description": "Liste de packages"}},
            }
        },
    },
}


@app.route("/swagger.json")
def swagger_json() -> Response:
    """Return the OpenAPI specification."""
    return jsonify(SWAGGER_SPEC)


@app.route("/docs")
def swagger_ui() -> Response:
    """Simple Swagger UI leveraging the public CDN."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
      <title>Winget API Documentation</title>
      <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist/swagger-ui.css" />
    </head>
    <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
    <script>
    SwaggerUIBundle({url: '/swagger.json', dom_id: '#swagger-ui'});
    </script>
    </body>
    </html>
    """
    return Response(html, mimetype="text/html")

# Initialiser la DB
def init_db():
    """Create database tables if they do not exist."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                package_id TEXT UNIQUE NOT NULL,
                version TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

# Parser la sortie de winget list
def parse_winget_output(output: str) -> List[Dict[str, str]]:
    """Parse the raw output from ``winget list`` into a structured list."""
    log_with_time("Début du parsing de la sortie winget...")
    packages: List[Dict[str, str]] = []
    lines = output.strip().split("\n")
    if len(lines) < 2:
        log_with_time("Aucune donnée valide à parser.")
        return packages

    # Find column indexes dynamically from the header line
    header_parts = re.split(r"\s{2,}", lines[0].strip().lower())
    try:
        idx_name = header_parts.index("name")
        idx_id = header_parts.index("id")
        idx_version = header_parts.index("version")
    except ValueError:
        log_with_time("Impossible de détecter les colonnes.")
        return packages

    for line in lines[1:]:
        if not line.strip():
            continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) > max(idx_name, idx_id, idx_version):
            packages.append(
                {
                    "name": parts[idx_name].strip(),
                    "package_id": parts[idx_id].strip(),
                    "version": parts[idx_version].strip(),
                }
            )

    log_with_time(f"{len(packages)} packages parsés.")
    return packages

# Route pour rafraîchir la DB via winget
@app.route('/api/refresh', methods=['POST'])
def refresh_packages():
    """Refresh the package cache by invoking ``winget list``."""
    try:
        log_with_time("Lancement de winget list...")
        start_cmd = datetime.now()
        result = subprocess.run(
            ["winget", "list", "--accept-source-agreements"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        log_with_time(
            f"Commande winget terminée en {(datetime.now() - start_cmd).total_seconds():.2f}s"
        )
    except FileNotFoundError:
        msg = "Commande winget introuvable"
        log_with_time(msg)
        return jsonify({"error": msg}), 500
    except Exception as e:  # subprocess error
        log_with_time(f"Erreur: {e}")
        return jsonify({"error": str(e)}), 500

    if result.returncode != 0:
        log_with_time(f"Erreur winget: {result.stderr}")
        return jsonify({"error": f"Erreur winget: {result.stderr}"}), 500

    parsed_packages = parse_winget_output(result.stdout)
    if not parsed_packages:
        log_with_time("Aucun package à insérer.")
        return jsonify({"error": "Aucun package parsé"}), 400

    # Stocker en DB avec progression
    total = len(parsed_packages)
    log_with_time(f"Insertion de {total} packages dans la base...")
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        print_progress(0, total)
        for i, pkg in enumerate(parsed_packages, 1):
            cursor.execute(
                """
                INSERT OR REPLACE INTO packages (name, package_id, version)
                VALUES (?, ?, ?)
                """,
                (pkg["name"], pkg["package_id"], pkg["version"]),
            )
            print_progress(i, total)

    log_with_time(f"Insertion terminée : {total} packages.")
    return jsonify(
        {
            "success": True,
            "count": total,
            "message": f"{total} packages stockés/mis à jour",
        }
    )


@app.route('/api/fullupdate', methods=['POST'])
def full_update() -> Response:
    """Run ``winget search`` with JSON output and refresh the DB."""
    try:
        log_with_time("Lancement de winget search (full update)...")
        start_cmd = datetime.now()
        result = subprocess.run(
            [
                "winget",
                "search",
                "",
                "--source",
                "winget",
                "--accept-source-agreements",
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        log_with_time(
            f"Commande winget terminée en {(datetime.now() - start_cmd).total_seconds():.2f}s"
        )
    except FileNotFoundError:
        msg = "Commande winget introuvable"
        log_with_time(msg)
        return jsonify({"error": msg}), 500
    except Exception as e:
        log_with_time(f"Erreur: {e}")
        return jsonify({"error": str(e)}), 500

    if result.returncode != 0:
        log_with_time(f"Erreur winget: {result.stderr}")
        return jsonify({"error": f"Erreur winget: {result.stderr}"}), 500

    with open("winget_packages.json", "w", encoding="utf-8") as f:
        f.write(result.stdout)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        log_with_time(f"Erreur JSON: {e}")
        return jsonify({"error": "Erreur JSON"}), 400

    packages: List[Dict[str, str]] = []
    if isinstance(data, dict):
        if "sources" in data:
            for src in data.get("sources", []):
                for pkg in src.get("packages", []):
                    packages.append(
                        {
                            "name": pkg.get("name", ""),
                            "package_id": pkg.get("id") or pkg.get("packageIdentifier", ""),
                            "version": pkg.get("version", ""),
                        }
                    )
        elif "data" in data:
            for pkg in data.get("data", []):
                packages.append(
                    {
                        "name": pkg.get("Name", ""),
                        "package_id": pkg.get("Id") or pkg.get("PackageIdentifier", ""),
                        "version": pkg.get("Version", ""),
                    }
                )

    if not packages:
        log_with_time("Aucun package à insérer.")
        return jsonify({"error": "Aucun package parsé"}), 400

    total = len(packages)
    log_with_time(f"Insertion de {total} packages dans la base (full update)...")
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        print_progress(0, total)
        for i, pkg in enumerate(packages, 1):
            cursor.execute(
                """
                INSERT OR REPLACE INTO packages (name, package_id, version)
                VALUES (?, ?, ?)
                """,
                (pkg["name"], pkg["package_id"], pkg["version"]),
            )
            print_progress(i, total)

    log_with_time(f"Insertion terminée : {total} packages.")
    return jsonify({"success": True, "count": total, "message": f"{total} packages stockés/mis à jour"})
# Fonction pour interroger la DB
def query_packages(
    query: str = "",
    publisher: str = "",
    sort: str = "name",
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """Query the package database with optional filters and pagination."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # Construire WHERE
        conditions = []
        params: List[Any] = []
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
        order_by = (
            f"ORDER BY {sort}" if sort in ["name", "package_id", "version"] else "ORDER BY name"
        )

        # Pagination
        offset = (page - 1) * page_size
        cursor.execute(
            f"""
            SELECT name, package_id, version FROM packages
            {where_clause} {order_by} LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        )

        packages = [
            {"name": row[0], "package_id": row[1], "version": row[2]}
            for row in cursor.fetchall()
        ]

    return {
        "Packages": packages,
        "Total": total,
        "CurrentPage": page,
        "TotalPages": (total + page_size - 1) // page_size,
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
    log_with_time("Lancement du serveur Flask sur le port 4006...")
    app.run(debug=True, host='0.0.0.0', port=4006)
