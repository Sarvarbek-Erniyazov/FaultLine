# Deploy runbook (for later; nothing here has been run)

This runbook covers hosting the Lesson 11 API on Railway and the static page on Vercel. **None of it has been done.** No image has been pushed, no service created and no login made.

**Before anything is hosted,** the project README's sentence "Nothing in this repository is a deployed system" becomes false. The author needs to change that wording first; this runbook does not change it.

## 0. Build and check the image locally

On this machine the Docker CLI is called by full path. Docker's `bin` folder is put on PATH for the build only, so that the `desktop` credential helper next to `docker.exe` can be found.

```bash
DOCKER_BIN="/c/Users/sharg/AppData/Local/Programs/DockerDesktop/resources/bin"
DOCKER="$DOCKER_BIN/docker.exe"
"$DOCKER" version                                   # Client and Server must both answer
PATH="$DOCKER_BIN:$PATH" "$DOCKER" build -f deployment/Dockerfile -t faultline-l11 \
    --build-arg GIT_SHA=$(git rev-parse HEAD) .
"$DOCKER" run -d --name faultline-l11 -p 8000:8000 faultline-l11
curl localhost:8000/health                          # model_loaded: true, SHA-256s, git SHA
"$DOCKER" stop faultline-l11 && "$DOCKER" rm faultline-l11
```

The image is 1.89 GB (CPU torch). It runs as a non-root user, listens on `$PORT` (default 8000) and has a HEALTHCHECK on `/health`.

## 1. How `model.pt` reaches the image

`checkpoints/model.pt` (42.2 MB, sha256 `3d45e42c…9881d`) is **gitignored**, and the repository's pre-commit hook blocks anything under `checkpoints/`. A Railway build from the Git repository will therefore not have it. Three ways to supply it, in order of preference:

1. **Build locally and deploy the image (recommended).** Build as in step 0. Push to a registry Railway can pull from, then point the Railway service at that image. `model.pt` is inside the image, and the git SHA is baked in as `FAULTLINE_GIT_SHA`. This needs a registry login, which the author does themselves.
2. **Fetch it at build time.** Upload `model.pt` to private storage and add a build step that downloads it with a token held as a Railway build secret, then checks its SHA-256 before `COPY`. That is a new Dockerfile; the current one expects the file in the context.
3. **Git LFS.** Not recommended: it would put a model file under version control against the repository's own rule.

Whichever route is used, `/health` reports the loaded model's SHA-256. Compare it with `3d45e42c3a7ef9819ba9fc3a705f603665ec5515f225b78005d44b15b1f9881d`.

## 2. Railway (the API)

- **Service:** from the image in step 1. Railway injects `PORT`, which the image honours.
- **Health check path:** `/health`. It returns 503 until the model has loaded, so allow a start period of about a minute.
- **Variables:**
  - `ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app`, the page's exact origin, comma-separated if there are several. Do not use `*`.
  - `FAULTLINE_GIT_SHA` is already baked in by the build argument; set it only to override.
  - `FAULTLINE_MODEL`, `FAULTLINE_TOKENIZERS` and `FAULTLINE_BUNDLE` can stay at the image defaults.
- **Resources:** CPU only. One worker is enough for a demo, since the app serialises model calls behind a lock. Memory use in the container was not measured; start with at least 1 GB and watch it.
- **Not provided:** authentication and rate limiting. The endpoints are open. For anything beyond a short demo, put the service behind Railway's private networking or add an auth layer first.

## 3. Vercel (the page)

- **Project:** import the repository with no framework, no build command, and output directory `ui`. The page is one static file.
- **API address:** the page calls `http://localhost:8000` unless the URL carries `?api=`. Either share the link as `https://<your-vercel-app>.vercel.app/?api=https://<your-railway-app>.up.railway.app`, or change the `DEFAULT_API` constant in `ui/index.html` in a later commit.
- **CORS:** the Railway `ALLOWED_ORIGINS` must list the Vercel origin exactly, including `https://` and without a trailing slash.

## 4. After hosting

1. Open `/health` and check `model_loaded`, the model's SHA-256 and the git SHA.
2. Open the page and score one bundle window. The headline must read "as evaluated in the record" and match `lesson11/demo/parity.json` for that window.
3. Have the author update the README sentence and add a monitoring plan. Latency is logged per request, but nothing collects or alerts on it yet.
