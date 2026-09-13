# DevOps Learning Log — dice-roller (end-to-end)

**Date:** 2026-09-14
**Repo:** dice-roller
**Purpose:** A casino dice-roller app built from scratch to practice the *complete* enterprise DevOps workflow — code → containerize → git branch/PR → CI → multi-environment deploy → (next) GitOps. This doc captures both the steps and the concepts.

---

## The app

A tiny Flask API + web UI that rolls two dice with craps rules.

- `/` — a casino-styled HTML page (green felt, gold button) that calls `/roll` and shows the dice.
- `/roll` — returns JSON: `die1`, `die2`, `total`, `outcome` (Snake eyes / Natural win / Craps / Point).
- `/health` — health check used by OpenShift.
- Listens on port 8000; run in the container with gunicorn.

Files: `app.py`, `requirements.txt` (flask, gunicorn), `Dockerfile`, `templates/index.html`.

---

## Part 1 — Build & run the container (local)

```bash
docker build -t dice-roller .        # recipe (Dockerfile) -> image
docker run -p 8000:8000 dice-roller  # image -> running container; Mac 8000 -> container 8000
curl http://localhost:8000/          # or open in a browser
```

Concept: **image vs container** — the image is the built package; the container is it running. Rebuild after any code change (images are **immutable** — never edit, always rebuild).

---

## Part 2 — Git: the branch + Pull Request workflow

**Why:** on a team you never edit `main` directly. You branch, change, and open a Pull Request so the change is reviewed before merging. This is the universal enterprise workflow.

The flow we did:

```
git init / commit / push              # get the repo onto GitHub (main)
git checkout -b feature/casino-ui     # create + switch to a branch (isolated line of work)
# ...edit files (the casino UI)...
git add . && git commit -m "..."      # snapshot on the branch
git push -u origin feature/casino-ui  # publish the BRANCH (not main)
# On GitHub: open a Pull Request (base: main  <-  compare: feature/casino-ui)
#            review the diff (Files changed), then Merge pull request
git checkout main && git pull          # sync local main with the merged change
```

Key ideas:
- A **branch** is a private copy of the code; `main` stays untouched until merge.
- A **Pull Request (PR)** = "please review my branch and merge it into main." It shows the diff and is the review gate. In a team a *different* person reviews; CI checks also run on the PR.
- **Committed != pushed**; **pushed to a branch != on main.** The default GitHub view shows `main`, so a branch's changes only appear there after merge.
- Merging a PR = the change officially lands in `main`.

---

## Part 3 — CI (Continuous Integration) with GitHub Actions

**Why:** so you never build/push images by hand. Every push to `main` auto-builds the image and pushes it to the registry.

Workflow file: `.github/workflows/build-push.yml` (must live in `.github/workflows/` at the **repo root** — GitHub only runs workflows from there).

What it does, on `push` to `main`:
1. **Checkout** the code onto a fresh GitHub-hosted runner.
2. **Log in to GHCR** using the built-in `secrets.GITHUB_TOKEN` (no Personal Access Token needed).
3. **Build & push** the image, tagged `latest` and the commit SHA (`ghcr.io/sawneil/dice-roller:<tag>`).

```yaml
on:
  push:
    branches: [ main ]
jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ghcr.io/sawneil/dice-roller:latest
            ghcr.io/sawneil/dice-roller:${{ github.sha }}
```

Gotcha we hit: the workflow file was first created nested under `templates/.github/...`. GitHub ignored it. Fixed by `git mv` to the repo-root `.github/workflows/`. **Workflow location matters.**

Result: pushing code now automatically produces a fresh, SHA-tagged image in GHCR — the left half of the pipeline, fully automated. The registry is swappable: GHCR here, could be ACR (Azure) or ECR (AWS) — only the login + image name change.

---

## Part 4 — Multi-environment deploy with Kustomize (dev / staging / prod)

**Principle: build once, promote by config.** One image is deployed to every environment; only *configuration* differs per environment. Guarantees dev == staging == prod (same image, never rebuilt).

Structure:

```
k8s/
├── base/                     # shared YAML, written once
│   ├── app.yaml              # Deployment + Service + Route (pins the ONE image)
│   └── kustomization.yaml    # lists app.yaml
└── overlays/
    ├── dev/kustomization.yaml       # namespace: dice-dev
    ├── staging/kustomization.yaml   # namespace: dice-staging
    └── prod/kustomization.yaml      # namespace: dice-prod + replicas: 2
```

How **Kustomize** works: `base/` holds the real objects; each `overlay` says "start from base, change only these few things" (namespace, and prod's replica count). No duplication, no drift.

How it relates to **OpenShift/CRC**:

```
base + overlay  --(oc apply -k; Kustomize merges on your laptop)-->  final YAML  -->  OpenShift (CRC) creates Pod/Service/Route in that namespace
```

- **OpenShift** runs the containers; **CRC** is local OpenShift on the Mac.
- `oc apply -k <overlay>` runs Kustomize first, then applies the merged YAML to the cluster.
- Each overlay's `namespace` sends the objects to the right project.

Commands (to run next session):

```bash
oc kustomize k8s/overlays/dev      # preview the merged YAML (no apply)
oc new-project dice-dev
oc new-project dice-staging
oc new-project dice-prod
oc apply -k k8s/overlays/dev
oc apply -k k8s/overlays/staging
oc apply -k k8s/overlays/prod
oc get pods -n dice-dev            # dev/staging = 1 pod, prod = 2 pods
oc get route dice-roller -n dice-dev   # the public URL
```

Prerequisite: the `dice-roller` GHCR package must be **Public** (or use an image pull secret), else the cluster can't pull it (`ImagePullBackOff`).

---

## Concept glossary (quick reference)

- **DevOps** — the practice/culture of automating code → build → deploy; devs + ops together.
- **GitOps** — a DevOps technique: git is the source of truth; a tool (Flux/Argo) makes the cluster match the git repo automatically.
- **Git** — the version-control tool (runs on your laptop).
- **GitHub** — a hosted platform for git (code) repositories + PRs/reviews. (GitLab, Bitbucket, Azure DevOps = same idea.)
- **Repository** — a storage box: a *code repo* (on GitHub) or an *image repo* (in a registry).
- **Container registry** — warehouse for container images. **GHCR** (GitHub), **ACR** (Azure), **ECR** (AWS), Docker Hub, Quay.
- **Docker** — one tool that builds/runs containers. Not the only one: Podman, Buildah, Kaniko build; containerd, CRI-O run (OpenShift uses CRI-O). All produce/run the same **OCI** standard image, so the tool is swappable. Read the pipeline box as "containerize," not "Docker specifically."
- **Image vs container** — image = built package (recipe → frozen meal); container = it running (the meal being eaten).
- **Immutable infrastructure** — never patch a running thing; rebuild a new image and replace it.
- **CI vs CD** — CI builds/tests/scans the code and produces an image; CD deploys that image.
- **Build once, promote by config** — one image to dev → staging → prod; only config changes; never rebuild per environment.

---

## Where we paused & next steps

**Paused at:** Kustomize files created locally (not committed to git, not deployed yet).

**Next session:**
1. Commit + push the `k8s/` files to GitHub.
2. Run the Part-4 commands: preview → create 3 projects → `oc apply -k` each overlay → verify pods → open the Routes (casino UI live in dev/staging/prod).
3. **GitOps finale:** install **Flux** on CRC, point it at this repo's `k8s/overlays/`, and let it auto-deploy — so a git commit deploys, with no manual `oc apply`.

Remember: `crc start` to bring the cluster up, then `eval $(crc oc-env)` and `oc login -u developer -p developer https://api.crc.testing:6443`.
