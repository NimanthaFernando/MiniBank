#!/bin/bash
# Startup script for Azure App Service
# Installs ODBC Driver 18 for SQL Server, then starts gunicorn

echo "[STARTUP] Installing ODBC Driver 18 for SQL Server..."

# Install prerequisites
apt-get update -qq
apt-get install -y -qq curl gnupg2 apt-transport-https unixodbc-dev > /dev/null 2>&1

# Add Microsoft repo and install ODBC driver
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg 2>/dev/null
curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list 2>/dev/null
apt-get update -qq
ACCEPT_EULA=Y apt-get install -y -qq msodbcsql18 > /dev/null 2>&1

echo "[STARTUP] ODBC Driver installed. Starting gunicorn..."

# Start the app
gunicorn --bind=0.0.0.0 --timeout 600 app:app
