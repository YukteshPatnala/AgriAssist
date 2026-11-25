# GitHub and Deployment Guide for AgriAssist

This guide takes you from an empty folder to a live link you can share. It assumes no prior Git experience.

---

## Part A: Understand the three links first

| Link | What it is | What it hosts | Example |
|---|---|---|---|
| **GitHub repository link** | The page where your code is stored and shown. | Source code, README, history. It does **not** run the app. | `https://github.com/your-username/agriassist` |
| **GitHub Pages link** | A free GitHub feature that serves **static** files (HTML, CSS, JavaScript) from a repository. | Only the frontend, and only if it is static. | `https://your-username.github.io/agriassist/` |
| **Live deployed application link** | The URL where the whole app runs. | The frontend on a static host, plus the FastAPI backend on a server host. | Frontend: `https://agriassist.netlify.app`; API: `https://agriassist-api.onrender.com` |

Important points:

- **GitHub does not run the FastAPI backend.** Python backends need a server that stays on. GitHub Pages can only serve static files, so it cannot run `uvicorn`.
- The correct approach is to **host the backend on a Python hosting service** (for example Render) and the **frontend on a static host** (for example Render Static Site, Netlify, Vercel, or GitHub Pages). The frontend calls the backend's live URL.
- The GitHub repository is the source for both. Each hosting service connects to it and rebuilds the app when you push changes.

---

## Part B: Set up GitHub

### 1. Create a GitHub account (if needed)

1. Go to https://github.com and click **Sign up**.
2. Choose a username. It appears in your links, so pick something professional, such as your name.
3. Verify your email address.

### 2. Create a new repository

1. Sign in and click the **+** at the top right, then **New repository**.
2. **Repository name:** `agriassist`
3. **Description:** "Multilingual-ready GenAI advisory chatbot for farmers using RAG".
4. Choose **Public** (needed for free GitHub Pages and most free hosting). Make sure you do not commit secrets, as explained below.
5. Do **not** tick "Add a README" or ".gitignore", because the project already has them.
6. Click **Create repository**. Keep this page open; it shows the commands you need.

### 3. Install Git

- **Windows:** download Git for Windows from https://git-scm.com and install with default options.
- **macOS:** run `git --version` in Terminal. If it is missing, macOS offers to install the developer tools.
- **Linux:** `sudo apt install git`

Check the install:

```bash
git --version
```

### 4. Set your identity (one-time)

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Use the same email as your GitHub account.

### 5. Initialise Git in the project folder

```bash
cd path/to/agriassist
git init -b main
```

### 6. Check what will be committed

```bash
git status
```

The `.gitignore` file already excludes `backend/.env`, `.venv/` and `__pycache__/`. **Confirm that `backend/.env` does not appear in the list.** Your API key lives in that file and must never go to GitHub. If it appears, stop and check your `.gitignore`.

### 7. Add and commit the files

```bash
git add .
git commit -m "Initial commit: AgriAssist RAG chatbot"
```

### 8. Connect the local project to GitHub

Replace `your-username` with your GitHub username:

```bash
git remote add origin https://github.com/your-username/agriassist.git
```

### 9. Push the project

```bash
git push -u origin main
```

- If Git asks for a password, GitHub no longer accepts account passwords. Use a **Personal Access Token** (GitHub Settings, Developer settings, Personal access tokens) or sign in with the GitHub CLI (`gh auth login`).
- Refresh the repository page. Your files should appear.

### 10. Update the repository after changes

```bash
git status                       # see what changed
git add .                        # stage all changes
git commit -m "Describe the change"
git push
```

Write short, clear commit messages, for example "Fix escalation message" or "Add wheat guide".

---

## Part C: Deploy the backend (FastAPI) on Render

Render runs Python web services and gives a public URL. The free tier sleeps after inactivity, so the first request after a while can take 30 to 60 seconds. Mention this during the demo.

### 1. Create a Render account

Go to https://render.com and sign up with GitHub. This links your repositories.

### 2. Create a Web Service

1. Click **New +**, then **Web Service**.
2. Select the `agriassist` repository and click **Connect**.
3. Fill in the settings:

| Setting | Value |
|---|---|
| Name | `agriassist-api` |
| Region | Closest to you |
| Branch | `main` |
| Root Directory | `backend` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | Free |

### 3. Add environment variables

In the service's **Environment** tab, add:

| Key | Value |
|---|---|
| `LLM_PROVIDER` | `openai` (or `gemini`) |
| `LLM_API_KEY` | Your key (paste it here, never in the code) |
| `LLM_MODEL` | Optional, for example `gpt-4o-mini` |
| `CORS_ORIGINS` | Your frontend URL, for example `https://agriassist.netlify.app` (add it after Part D) |
| `MIN_CONFIDENCE` | `0.10` |

Set `CORS_ORIGINS` after you have the frontend URL, then redeploy. Until then you can temporarily use `*`, but restrict it before sharing widely.

### 4. Deploy and get the live URL

Click **Create Web Service**. When the build finishes, Render shows a URL such as `https://agriassist-api.onrender.com`. Test it:

- `https://agriassist-api.onrender.com/api/health` should return JSON with `"status": "ok"`.
- `https://agriassist-api.onrender.com/api/llm-check` should return `"ok": true` if the key works.

---

## Part D: Deploy the frontend

### Option 1: Netlify (drag and drop, simplest)

1. Set the backend URL first. Edit `frontend/config.js`:

   ```js
   window.AGRIASSIST_API_BASE = "https://agriassist-api.onrender.com";
   ```

2. Commit and push the change (Part B, step 10).
3. Go to https://app.netlify.com, sign up, and click **Add new site**, then **Import an existing project**, then GitHub.
4. Select `agriassist`. Set **Base directory** to `frontend` and leave the build command empty. Set **Publish directory** to `frontend` (or `.` relative to the base directory).
5. Click **Deploy**. Netlify gives you a URL such as `https://agriassist.netlify.app`.
6. Go back to Render, set `CORS_ORIGINS` to that URL, and redeploy the backend.

### Option 2: Render Static Site

1. In Render, click **New +**, then **Static Site**, and select the repository.
2. **Root Directory:** `frontend`. **Build Command:** leave empty. **Publish Directory:** `.`
3. Deploy, then update `CORS_ORIGINS` as above.

### Option 3: GitHub Pages

GitHub Pages serves only the frontend and must read from the repository root or a `docs/` folder.

1. Copy the contents of `frontend/` into a folder named `docs/` at the repository root, and commit.
2. In the repository, go to **Settings**, then **Pages**. Set **Source** to "Deploy from a branch", branch `main`, folder `/docs`, and save.
3. After a minute, the site is at `https://your-username.github.io/agriassist/`.
4. Keep `frontend/config.js` (or `docs/config.js`) pointing to the Render backend URL.
5. Set `CORS_ORIGINS` on Render to `https://your-username.github.io`.

---

## Part E: Test the deployed application

Work through this checklist with the live link:

1. Open the frontend URL. The top bar should say "Online - AI model: openai" (or "No AI model").
2. Ask: "How do I control early blight on tomato leaves?" Expect an answer with a numbered source.
3. Expand **Sources**. Each source should show a file name, page and snippet.
4. Ask: "What is the capital of France?" Expect the escalation message.
5. Ask: "My son swallowed pesticide." Expect the emergency message.
6. Upload a small PDF. Expect a green confirmation and the file in the list.
7. Open the page on a phone. Check that the layout fits the screen and nothing scrolls sideways.
8. If the first request is slow, wait 30 to 60 seconds. This is the free-tier wake-up.

If something fails, check the Render logs (**Logs** tab) and the browser console (F12).

---

## Part F: Common problems

| Symptom | Likely cause and fix |
|---|---|
| Page says "Offline" | Backend URL in `config.js` is wrong, or Render service is asleep. Open the `/api/health` URL directly. |
| Browser console shows CORS error | Add the exact frontend URL (with `https://`, no trailing slash) to `CORS_ORIGINS` and redeploy. |
| `"ok": false` on `/api/llm-check` | Check `LLM_API_KEY` and `LLM_PROVIDER` on Render. |
| Build fails on Render | Check that Root Directory is `backend` and that `requirements.txt` is in that folder. |
| Uploaded files disappear | Free hosting has temporary disk. Add important documents to `backend/data/docs/` and push. |
| Git says `rejected` on push | Run `git pull --rebase origin main`, then `git push`. |

---

## Part G: Before you submit

- [ ] Repository is public and contains the README.
- [ ] `backend/.env` is **not** in the repository (check the GitHub page).
- [ ] Live frontend link works on a phone and on a laptop.
- [ ] README and report state which parts were tested and which need a real AI key.
- [ ] Sample knowledge base replaced or clearly labelled as sample.

---

## Version 3 notes

- Set `AUTH_SECRET` (long random string), `DATAGOV_API_KEY` (optional), `LLM_API_KEY` (optional), and `CORS_ORIGINS` (your frontend URL) as environment variables on the backend host. Never commit `backend/.env`.
- The frontend has a light/dark toggle; no extra configuration is needed.
- Free hosting may reset the SQLite database (`DB_PATH`) and uploaded files on restart. Use a paid disk or an external database for real use.
