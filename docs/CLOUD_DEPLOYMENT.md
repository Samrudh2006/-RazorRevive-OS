# ☁️ RazorRevive-OS: Cloud Deployment Guide (GitHub Student Pack)

Deploy **RazorRevive-OS** to production in under 5 minutes using your **GitHub Student Developer Pack** benefits.

---

## 1. Option A: 1-Click Deployment on Azure (Free $100 Student Credits)

### Step 1: Install Azure CLI or Use Cloud Shell
```bash
az login
```

### Step 2: Build & Deploy Container to Azure Container Apps
```bash
# Create Resource Group
az group create --name razorrevive-rg --location eastus

# Deploy App directly from Dockerfile / Container
az containerapp up \
  --name razorrevive-os \
  --resource-group razorrevive-rg \
  --ingress external \
  --target-port 8000 \
  --source .
```
Your live URL will be generated: `https://razorrevive-os.eastus.azurecontainerapps.io`

---

## 2. Option B: Deploy on Heroku (Free $13/mo Student Credits)

```bash
# 1. Login to Heroku CLI
heroku login

# 2. Create App
heroku create razorrevive-os

# 3. Deploy via Container or Git Push
git push heroku main
```

---

## 3. Custom Domain Setup (Namecheap / .TECH from Student Pack)

1. Claim your free 1-year domain (e.g. `razorrevive.tech`) from the GitHub Student Pack.
2. In your DNS settings (Cloudflare or Namecheap), add a **CNAME** record:
   * **Host:** `@` or `app`
   * **Target:** Your Azure / Heroku generated domain.
3. Access your live application at `https://razorrevive.tech`!

---

## 4. Environment Variables Reference

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `RAZORPAY_KEY_ID` | `rzp_test_...` | Razorpay API key ID |
| `RAZORPAY_KEY_SECRET` | `...` | Razorpay API key secret |
| `WEBHOOK_SECRET` | `...` | HMAC-SHA256 signature verification secret |
| `SENTRY_DSN` | *(Optional)* | Sentry real-time exception tracking (from Student Pack) |
| `ENVIRONMENT` | `production` | Deployment mode |
