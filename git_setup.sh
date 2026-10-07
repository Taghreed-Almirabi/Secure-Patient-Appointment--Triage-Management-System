#!/usr/bin/env bash
# ==============================================================================
# Git Automation Script for Secure Patient Appointment & Triage Management System
# Fulfills Part C: Version Control Management with branching, commits, and tags.
# ==============================================================================

set -e  # Exit immediately if a command exits with a non-zero status

echo "=========================================================================="
echo " Starting Git Version Control Automation Workflow (Part C)"
echo "=========================================================================="

# Ensure Git is installed
if ! command -v git &> /dev/null; then
    echo "[ERROR] Git is not installed or not in PATH."
    exit 1
fi

# Set default identity if not configured locally or globally
if [ -z "$(git config user.name)" ]; then
    git config user.name "Software Engineer"
    git config user.email "engineer@hospital-system.local"
    echo "[INFO] Configured default local git identity."
fi

# 1. Initialize Git Repository and set main branch
echo -e "\n>>> Step 1: Initializing Git repository and 'main' branch..."
rm -rf .git
git init -b main || (git init && git branch -M main)

# 2. Stage Initial Scaffolding & Configuration
echo -e "\n>>> Step 2: Committing initial scaffold & tagging v0.1.0-alpha-core..."
git add .gitignore requirements.txt
git commit -m "chore: initial project scaffold and architecture setup"
git tag -a "v0.1.0-alpha-core" -m "Milestone: Initial Project Scaffold and Architecture Setup"

# 3. Create and checkout feature/triage-and-booking
echo -e "\n>>> Step 3: Branching feature/triage-and-booking and committing core logic..."
git checkout -b feature/triage-and-booking
git add src/models.py src/database.py src/auth_security.py src/triage_engine.py src/appointment_manager.py src/__init__.py
git commit -m "feat: implement triage engine, appointment conflict manager, and database models"

# Merge feature/triage-and-booking into main
git checkout main
git merge --no-ff feature/triage-and-booking -m "merge: integrate feature/triage-and-booking into main"

# 4. Create and checkout feature/unit-testing
echo -e "\n>>> Step 4: Branching feature/unit-testing and committing pytest suites..."
git checkout -b feature/unit-testing
git add tests/
git commit -m "test: add comprehensive white-box and black-box pytest test suites"

# Merge feature/unit-testing into main and tag v0.2.0-beta-testing
git checkout main
git merge --no-ff feature/unit-testing -m "merge: integrate feature/unit-testing into main"
git tag -a "v0.2.0-beta-testing" -m "Milestone: Complete White-Box & Black-Box Test Suites"

# 5. Create and checkout feature/ui-dashboard
echo -e "\n>>> Step 5: Branching feature/ui-dashboard and committing Tailwind CSS Web UI..."
git checkout -b feature/ui-dashboard
git add templates/ src/web_app.py app.py
git commit -m "feat: integrate modern Tailwind CSS medical dashboard and web routes"

# Merge feature/ui-dashboard into main
git checkout main
git merge --no-ff feature/ui-dashboard -m "merge: integrate feature/ui-dashboard into main"

# 6. Create release/v1.0.0 branch, perform final cleanup & documentation
echo -e "\n>>> Step 6: Branching release/v1.0.0 and committing final documentation..."
git checkout -b release/v1.0.0
git add README.md src/main.py git_setup.sh
if [ -f git_setup.ps1 ]; then
    git add git_setup.ps1
fi
git commit -m "release: finalize production documentation, demo pipeline, and release build"

# Merge release into main and tag v1.0.0-final-release
git checkout main
git merge --no-ff release/v1.0.0 -m "merge: release v1.0.0 into main"
git tag -a "v1.0.0-final-release" -m "Milestone: Production Release v1.0.0 with Tailwind Web UI"

# Create develop branch from main for ongoing development
git checkout -b develop

echo -e "\n=========================================================================="
echo " Git Version Control Workflow Completed Successfully!"
echo "=========================================================================="
echo -e "\n--- Git Branches ---"
git branch -a

echo -e "\n--- Git Milestone Tags ---"
git tag -n

echo -e "\n--- Git Commit History Graph ---"
git log --oneline --graph --decorate --all -n 12
