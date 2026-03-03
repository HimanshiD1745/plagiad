# Plagiad (Beginner-Friendly Full-Stack Starter)

> ⚠️ Important: no tool can honestly guarantee **97%+ accuracy for every case**. This project gives you a practical starter with transparent heuristic analysis, login, history, and downloadable reports.

## What this app includes

- User register/login with SQLite database
- Upload area at the top of dashboard for:
  - text input
  - PDF upload
  - image upload
- Line-by-line analysis with labels:
  - `direct`
  - `paraphrasing`
  - `mosaic`
  - `human-likely`
- Basic AI image model guess (filename/signature heuristic)
- Analysis history saved per user
- Report page with line highlights + overall summary
- Download report as `.html`

## Step-by-step setup

1. **Open terminal in project folder**
   ```bash
   cd /workspace/plagiad
   ```
2. **Create virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Run the app**
   ```bash
   python app.py
   ```
5. **Open in browser**
   - http://localhost:5000
6. **Use it**
   - Register account
   - Login
   - Upload PDF/image or paste text
   - Click Analyze
   - Open report and download report

## Project structure

- `app.py` - backend routes, DB models, analysis logic
- `templates/` - frontend HTML pages
- `static/styles.css` - custom UI styling
- `uploads/` - uploaded files
- `reports/` - reserved folder for report artifacts

## Next upgrades for real production

- Replace heuristic analyzer with dedicated ML/NLP + dataset-backed evaluation
- Add OCR for images and scanned PDFs
- Use Celery/RQ for async analysis jobs
- Add JWT or OAuth and role-based admin panel
- Export PDF reports with embedded highlights
- Add plagiarism source matching against indexed web/corpus
