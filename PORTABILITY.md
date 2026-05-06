# Side-Brain Portability: Multi-Machine Setup

This guide and the accompanying `setup.sh` allow you to replicate the **Humane Side-Brain** environment on a new machine.

## Prerequisites
- **Node.js** (v20+)
- **Claude Code** installed and authenticated.
- **MCP Servers**: Ensure `mcp-server-memory-keeper` is available.

---

## 1. Clone the Core
Run this from your desired parent directory:
```bash
# Get the clone script (or clone manually)
curl -O https://raw.githubusercontent.com/snackdriven/operator-core-mini/main/clone-core.sh
bash clone-core.sh
```

## 2. Fast Setup (The One-Liner)
Run this from the same directory to initialize the environment:
```bash
bash operator-core-mini/setup.sh
```

## 2. What this configures:
1.  **Dependencies:** Installs `tsx` globally/locally to run the ingestion engines.
2.  **Symlinks:** Links the `mcp.json` into the local `.claude/` directory so Claude can see the Memory-Keeper tools.
3.  **Active Surface:** Initializes the `scratch-pad` structure (Backpack, Doctrine, Dailies).
4.  **Skills:** Sets up the `.claude/skills` directory so the Librarian and Session scripts are active.

## 3. Manual Verification Steps
After running the script:
1.  **Check MCP:** Run `claude mcp list` and verify `memory-keeper` is active.
2.  **Test Manifest:** Run `npx tsx scratch-pad/scripts/manifest-writer.ts` to ensure it can scan your folders.
3.  **Bootstrap Backpack:** If you have an existing `backpack.json`, copy it into the `scratch-pad/` root.

## 4. Maintenance
To keep machines in sync:
- **Git:** Commit your `scratch-pad` changes (or use a private repo).
- **SQLite:** Periodically sync the `~/mcp-data/memory-keeper/context.db` via the `claude-memory-snapshot` tool.
