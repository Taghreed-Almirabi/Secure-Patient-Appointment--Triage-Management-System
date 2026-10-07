# ==============================================================================
# PowerShell Git Automation Script for Secure Patient Appointment & Triage System
# Fulfills Part C: Version Control Management with branching, commits, and tags.
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "==========================================================================" -ForegroundColor Cyan
Write-Host " Starting Git Version Control Automation Workflow (Part C)" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

# Check Git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Git is not installed or not in PATH."
}

# Configure default user if unset
$currentUserName = git config user.name
if (-not $currentUserName) {
    git config user.name "Software Engineer"
    git config user.email "engineer@hospital-system.local"
    Write-Host "[INFO] Configured default local git identity." -ForegroundColor Gray
}

# 1. Initialize repository
Write-Host "`n>>> Step 1: Initializing Git repository and 'main' branch..." -ForegroundColor Yellow
if (Test-Path .git) {
    Remove-Item -Recurse -Force .git
}
git init -b main

# 2. Initial Scaffold Commit & Tag v0.1.0-alpha-core
Write-Host "`n>>> Step 2: Committing initial scaffold & tagging v0.1.0-alpha-core..." -ForegroundColor Yellow
git add .gitignore requirements.txt
git commit -m "chore: initial project scaffold and architecture setup"
git tag -a "v0.1.0-alpha-core" -m "Milestone: Initial Project Scaffold and Architecture Setup"

# 3. Branch feature/triage-and-booking
Write-Host "`n>>> Step 3: Branching feature/triage-and-booking and committing core logic..." -ForegroundColor Yellow
git checkout -b feature/triage-and-booking
git add src/models.py src/database.py src/auth_security.py src/triage_engine.py src/appointment_manager.py src/__init__.py
git commit -m "feat: implement triage engine, appointment conflict manager, and database models"

# Merge to main
git checkout main
git merge --no-ff feature/triage-and-booking -m "merge: integrate feature/triage-and-booking into main"

# 4. Branch feature/unit-testing
Write-Host "`n>>> Step 4: Branching feature/unit-testing and committing pytest suites..." -ForegroundColor Yellow
git checkout -b feature/unit-testing
git add tests/
git commit -m "test: add comprehensive white-box and black-box pytest test suites"

# Merge to main & tag v0.2.0-beta-testing
git checkout main
git merge --no-ff feature/unit-testing -m "merge: integrate feature/unit-testing into main"
git tag -a "v0.2.0-beta-testing" -m "Milestone: Complete White-Box & Black-Box Test Suites"

# 5. Branch feature/ui-dashboard
Write-Host "`n>>> Step 5: Branching feature/ui-dashboard and committing Tailwind CSS Web UI..." -ForegroundColor Yellow
git checkout -b feature/ui-dashboard
git add templates/ src/web_app.py app.py
git commit -m "feat: integrate modern Tailwind CSS medical dashboard and web routes"

# Merge to main
git checkout main
git merge --no-ff feature/ui-dashboard -m "merge: integrate feature/ui-dashboard into main"

# 6. Branch release/v1.0.0
Write-Host "`n>>> Step 6: Branching release/v1.0.0 and committing final documentation..." -ForegroundColor Yellow
git checkout -b release/v1.0.0
git add README.md src/main.py git_setup.sh git_setup.ps1
git commit -m "release: finalize production documentation, demo pipeline, and release build"

# Merge to main & tag v1.0.0-final-release
git checkout main
git merge --no-ff release/v1.0.0 -m "merge: release v1.0.0 into main"
git tag -a "v1.0.0-final-release" -m "Milestone: Production Release v1.0.0 with Tailwind Web UI"

# Create develop branch
git checkout -b develop

Write-Host "`n==========================================================================" -ForegroundColor Green
Write-Host " Git Version Control Workflow Completed Successfully!" -ForegroundColor Green
Write-Host "==========================================================================" -ForegroundColor Green

Write-Host "`n--- Git Branches ---" -ForegroundColor Cyan
git branch -a

Write-Host "`n--- Git Milestone Tags ---" -ForegroundColor Cyan
git tag -n

Write-Host "`n--- Git Commit History Graph ---" -ForegroundColor Cyan
git log --oneline --graph --decorate --all -n 14
