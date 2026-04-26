#!/bin/bash
# Startup script for Azure App Service
echo "[STARTUP] Starting MiniBank with gunicorn..."
gunicorn --bind=0.0.0.0 --timeout 600 app:app
