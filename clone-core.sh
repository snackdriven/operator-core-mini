#!/bin/bash
# REPO CLONE MANIFEST: The Humane Side-Brain Core
# Run this from your desired workspace root.

GITHUB_USER="snackdriven"

echo "🧠 Cloning Side-Brain Core Repositories..."

# 1. The Doctrine (Substrate & Schemas)
git clone "https://github.com/$GITHUB_USER/operator-core-mini.git"

# 2. The RAM (Active Workspace & Tooling)
git clone "https://github.com/$GITHUB_USER/scratch-pad.git"

# 3. The Archive (Memory-Keeper Snapshots)
git clone "https://github.com/$GITHUB_USER/claude-memory-snapshot.git"

echo ""
echo "✅ Core repos cloned."
echo "👉 Next: run 'bash operator-core-mini/setup.sh' to initialize."
