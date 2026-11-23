# Student Second Hand Book Exchange App

Flask + SQLite + HTML + CSS + JavaScript.

## Run
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000

The first account you register becomes the administrator (can review reports and remove listings).
Set a real secret before sharing the app: `set SECRET_KEY=your-long-random-text` (Windows) or `export SECRET_KEY=...`.

## Features
Register / log in, sell or exchange listings with photo, live search and filters, edit / mark sold / delete,
in-app messages between buyer and seller, report suspicious listings, admin review page.

## Files
app.py (routes + database), templates/ (HTML), static/style.css, static/app.js
