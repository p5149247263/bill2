# Gas Bill Compare App (GitHub + Vercel)

Upload two gas bill PDFs and download an Excel comparison file.

## Project structure

- `api/compare.py`: Flask API endpoint (`/api/compare`, `/api/health`)
- `api/gas_bill_core.py`: PDF parsing and `.xlsx` generation logic
- `public/index.html`: upload UI
- `public/app.js`: frontend submit/download logic
- `public/styles.css`: styling
- `vercel.json`: Vercel routing config

## Local run (optional)

```bash
cd /Users/ra20508781/Documents/gas-bill-vercel-app
python3 -m pip install -r requirements.txt
python3 -m flask --app api/compare.py run --port 5001
```

Open:
- `http://127.0.0.1:5001/api/health`

The UI is static in `public/`; for local API testing use Postman/curl or Vercel dev.

## Deploy using GitHub + Vercel

1. Create a GitHub repo and push this folder:

```bash
cd /Users/ra20508781/Documents/gas-bill-vercel-app
git init
git add .
git commit -m "Initial gas bill compare app"
git branch -M main
git remote add origin <YOUR_GITHUB_REPO_URL>
git push -u origin main
```

2. In Vercel:
- Import the GitHub repo
- Framework preset: `Other`
- Root directory: repo root
- Build command: leave empty
- Output directory: leave empty
- Deploy

After deploy, open your app URL and upload two PDFs.
