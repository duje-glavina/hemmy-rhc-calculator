# HEMMY - Right Heart Catheterization Hemodynamics Calculator (Web Version)

**Author:** Josip A. Borovac, MD, PhD
**Version:** 1.4.0 (Web)

A web-based hemodynamic calculator for right heart catheterization data analysis, following ESC/ERS guidelines for pulmonary hypertension classification.

## Features

- Complete RHC hemodynamic calculations (CO, CI, PVR, PAPi, etc.)
- ESC/ERS pulmonary hypertension classification
- Shunt assessment (Qp/Qs)
- Treatment recommendations based on hemodynamic phenotype
- Professional medical report generation
- Print-friendly output

## Running Locally

### Prerequisites
- Python 3.8 or higher

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open your browser and navigate to:
```
http://localhost:5000
```

## Deploying to Render

### Quick Deploy

1. Create a new account at [Render.com](https://render.com) (free tier available)

2. Click "New +" → "Web Service"

3. Connect your GitHub repository (or upload this folder)

4. Configure the service:
   - **Name:** hemmy-rhc (or any name you prefer)
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Plan:** Free

5. Click "Create Web Service"

6. Wait 2-3 minutes for deployment to complete

7. Your app will be live at: `https://hemmy-rhc.onrender.com` (or your custom name)

### Important Notes for Render Free Tier

- The service will spin down after 15 minutes of inactivity
- First load after inactivity takes 30-60 seconds to wake up
- Completely free for personal/clinical use
- No credit card required for free tier

## Alternative Deployment Options

### Deploy to Vercel (Alternative)
1. Install Vercel CLI: `npm i -g vercel`
2. Run: `vercel`
3. Follow prompts

### Deploy to Railway (Alternative)
1. Sign up at [Railway.app](https://railway.app)
2. Click "Deploy from GitHub"
3. Select this repository
4. Railway auto-detects and deploys

## File Structure

```
JAB - Hemmy/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── templates/
│   ├── index.html        # Input form
│   └── results.html      # Results display
├── static/
│   └── style.css         # Styling
├── Hemmy Final.py        # Original console version
└── README.md             # This file
```

## Usage

1. Fill in patient demographics (name/ID optional)
2. Enter anthropometric data (height, weight, hemoglobin)
3. Input oxygen saturations
4. Enter hemodynamic pressures from RHC
5. Optionally add systemic pressures for SVR/CPO calculation
6. Click "Calculate Hemodynamics"
7. Review comprehensive report with ESC/ERS classification
8. Print or save report as needed

## Medical Disclaimer

This tool is for clinical decision support only. All results should be interpreted by qualified healthcare professionals in the context of full clinical evaluation. Treatment recommendations are high-level and require complete diagnostic work-up.

## License

© 2024-2026 Josip A. Borovac, MD, PhD. For clinical use.
