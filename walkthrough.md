# MiniBank — Azure App Service "Application Error" Report

**Date:** 22 April 2026  
**Application:** MiniBank (Python Flask)  
**Platform:** Azure App Service (Linux, Python 3.11)  
**CI/CD:** GitHub Actions → Azure Web App Deploy  
**Repository:** [NimanthaFernando/MiniBank](https://github.com/NimanthaFernando/MiniBank)

---

## 1. Problem Description

After deploying the MiniBank Flask application to Azure App Service via GitHub Actions, the application displayed the following error page:

> **:( Application Error**  
> *If you are the application administrator, you can access the diagnostic resources.*

The application failed to start entirely — no routes were accessible, including the static login/register frontend pages.

---

## 2. Root Cause Analysis

Three issues were identified that collectively prevented the application from starting:

### 2.1 — `mysqlclient` C Library Build Failure (Primary Cause)

| Detail | Value |
|---|---|
| **Severity** | 🔴 Critical |
| **Affected File** | [requirements.txt](file:///d:/New%20folder%20(4)/minibank/requirements.txt) |

The `requirements.txt` listed `mysqlclient` and `flask-mysqldb` as dependencies. The `mysqlclient` package is a Python wrapper around the C library `libmysqlclient-dev`. During deployment, Azure's **Oryx build engine** attempted to `pip install` these packages, but **failed** because:

- Azure App Service's Python runtime does not include `libmysqlclient-dev`, `gcc`, or `pkg-config` by default
- `mysqlclient` cannot be compiled without these system-level C libraries
- The `pip install` step failed, causing the entire deployment to error out

> [!IMPORTANT]
> Even though the Dockerfile included `apt-get install` for these C libraries, **the GitHub Actions workflow deploys raw Python code** (not a Docker container). The Dockerfile was unused in this deployment path.

### 2.2 — Missing Startup Command

| Detail | Value |
|---|---|
| **Severity** | 🟡 Medium |
| **Affected File** | [main_minibank.yml](file:///d:/New%20folder%20(4)/minibank/.github/workflows/main_minibank.yml) |

The GitHub Actions workflow did not specify a `startup-command` in the Azure deploy step. Without this, Azure App Service doesn't know how to launch the Flask app via Gunicorn, falling back to a default that may not match the app structure.

### 2.3 — Hard MySQL Dependency at Import Time

| Detail | Value |
|---|---|
| **Severity** | 🟡 Medium |
| **Affected File** | [app.py](file:///d:/New%20folder%20(4)/minibank/app.py) |

The original `app.py` had top-level imports:

```python
from flask_mysqldb import MySQL
import MySQLdb.cursors
```

These imports ran **immediately at application startup**. Even if `pip install` had succeeded, the app would still crash at runtime because:

- No MySQL environment variables (`MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`) were configured in Azure App Service
- The app attempted to connect to `localhost` MySQL, which doesn't exist on Azure

---

## 3. Fixes Applied

### 3.1 — Made MySQL Dependencies Optional

**File:** [requirements.txt](file:///d:/New%20folder%20(4)/minibank/requirements.txt)

```diff
 Flask
 gunicorn
-flask-mysqldb
-mysqlclient
+# flask-mysqldb and mysqlclient are optional (needed only when DB is configured)
+# Uncomment below when deploying with a MySQL database:
+# flask-mysqldb
+# mysqlclient
```

**Rationale:** Removes the C library dependency that fails to build on Azure App Service. Since the user only needs the frontend to load, these are not required.

---

### 3.2 — Made MySQL Conditional in Application Code

**File:** [app.py](file:///d:/New%20folder%20(4)/minibank/app.py)

The MySQL initialization was wrapped in a conditional block:

```python
DB_AVAILABLE = False
mysql = None

if MYSQL_HOST and MYSQL_USER and MYSQL_PASSWORD:
    try:
        from flask_mysqldb import MySQL
        import MySQLdb.cursors
        # ... configure and initialize MySQL ...
        DB_AVAILABLE = True
    except Exception as e:
        print(f"[WARNING] MySQL not available: {e}. Running in frontend-only mode.")
```

Each database-dependent route now checks `DB_AVAILABLE` before attempting DB operations, returning a user-friendly flash message if unavailable.

**Rationale:** Allows the Flask app to start and serve frontend pages (login, register) even without a database connection.

---

### 3.3 — Added Startup Command to Deployment Workflow

**File:** [main_minibank.yml](file:///d:/New%20folder%20(4)/minibank/.github/workflows/main_minibank.yml)

```diff
       - name: 'Deploy to Azure Web App'
         uses: azure/webapps-deploy@v3
         with:
           app-name: 'Minibank'
           slot-name: 'Production'
+          startup-command: 'gunicorn --bind=0.0.0.0 --timeout 600 app:app'
```

**Rationale:** Explicitly tells Azure how to start the application with Gunicorn.

---

### 3.4 — Added startup.txt Fallback

**File:** [startup.txt](file:///d:/New%20folder%20(4)/minibank/startup.txt) `[NEW]`

```
gunicorn --bind=0.0.0.0 --timeout 600 app:app
```

**Rationale:** Backup startup command file that can be referenced from Azure Portal → Configuration → General Settings → Startup Command.

---

## 4. Deployment

All changes were committed and pushed to the `main` branch:

```
commit 628d4a7 - fix: make MySQL optional so frontend loads without DB on Azure
  4 files changed, 48 insertions(+), 12 deletions(-)
```

The push triggers the GitHub Actions workflow automatically, which will:
1. Build the Python app (install Flask + gunicorn only)
2. Upload the artifact
3. Deploy to Azure App Service with the startup command

---

## 5. Expected Result After Deployment

| Page | Status |
|---|---|
| `/` (Login page) | ✅ Renders successfully |
| `/register` | ✅ Renders successfully |
| `/login` (POST) | ⚠️ Shows "Database not configured" flash message |
| `/dashboard` | ⚠️ Redirects to login with flash message |

---

## 6. Future Recommendations

> [!TIP]
> To enable full database functionality later, follow these steps:

1. **Create an Azure Database for MySQL Flexible Server** in the Azure Portal
2. **Create the `bankdb` database** and required tables (`users`, `transactions`)
3. **Set environment variables** in Azure App Service → Configuration:
   - `MYSQL_HOST` = `yourserver.mysql.database.azure.com`
   - `MYSQL_USER` = your DB username
   - `MYSQL_PASSWORD` = your DB password
   - `MYSQL_DB` = `bankdb`
   - `SECRET_KEY` = a random secret string
4. **Uncomment** `flask-mysqldb` and `mysqlclient` in `requirements.txt`
5. **Re-deploy** — the app will detect the environment variables and enable full DB functionality

> [!WARNING]
> If you uncomment the MySQL packages in `requirements.txt`, you may also need to add `SCM_DO_BUILD_DURING_DEPLOYMENT=false` and instead include the `antenv/` virtual environment in the deployment artifact (built in the GitHub Actions runner where C compilation works). Alternatively, consider switching to **PyMySQL** (a pure Python MySQL client) which does not require C compilation:
> ```
> pip install PyMySQL
> ```
