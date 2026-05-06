#!/bin/bash
# Humane Side-Brain Setup Script
# Replicates the deterministic AI environment on a new machine.

set -euo pipefail

echo "🧠 Starting Side-Brain Setup..."

# 1. Check for Node/NPM
if ! command -v npm &> /dev/null; then
    echo "❌ Error: npm is not installed. Please install Node.js first."
    exit 1
fi

# 2. Install tsx (required for the ingestion engines)
echo "📦 Installing tsx..."
npm install -g tsx || npm install --save-dev tsx

# 3. Initialize Directory Structure
echo "📂 Initializing scratch-pad..."
mkdir -p scratch-pad/dailies
mkdir -p scratch-pad/scripts
mkdir -p scratch-pad/.claude/skills

# 4. Configure Claude MCP
echo "📡 Configuring MCP Symlinks..."
# Local .claude config for this workspace
mkdir -p .claude
if [ -f "operator-core-mini/mcp.json" ]; then
    ln -sf "$(pwd)/operator-core-mini/mcp.json" ".claude/mcp.json"
    echo "✅ Linked operator-core-mini/mcp.json to .claude/mcp.json"
else
    echo "⚠️ Warning: mcp.json not found in operator-core-mini. Please create it."
fi

# 5. Bootstrap Backpack
if [ ! -f "scratch-pad/backpack.json" ]; then
    echo "{ \"last_updated\": \"$(date +%Y-%m-%d)\" }" > scratch-pad/backpack.json
    echo "✅ Created fresh backpack.json"
fi

# 6. Success
echo ""
echo "✨ Setup Complete!"
echo "-------------------------------------------------------"
echo "1. Run 'claude mcp list' to verify memory-keeper is active."
echo "2. Run 'npx tsx scratch-pad/scripts/manifest-writer.ts' to test ingestion."
echo "3. Refer to operator-core-mini/PORTABILITY.md for deep-dive info."
echo "-------------------------------------------------------"
