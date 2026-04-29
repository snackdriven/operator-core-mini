import os
import sys
import time
import datetime
import subprocess
import logging
from pathlib import Path

# Use schedule if available, fallback to basic loop if not
try:
    import schedule
except ImportError:
    print("The 'schedule' package is missing. Please run: pip install schedule")
    sys.exit(1)

# Configure logging
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "weaver.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("weaver")

def get_scratch_pad_dir():
    """Resolve the location of the scratch-pad directory."""
    env_dir = os.environ.get("SCRATCH_PAD_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)
        
    # Fallbacks for Mac and Windows based on known patterns
    home = Path.home()
    possible_paths = [
        home / "Desktop" / "personal" / "scratch-pad",
        home / "workspace" / "scratch-pad",
        Path(__file__).parent.parent.parent / "scratch-pad", # side-by-side
    ]
    
    for p in possible_paths:
        if p.exists() and (p / "scripts" / "daily-summary.ts").exists():
            return p
            
    return None

def trigger_eod_wrapup():
    """Trigger the daily-summary.ts script if today's summary doesn't exist."""
    logger.info("Executing scheduled job: EOD Wrap-up")
    
    scratch_pad = get_scratch_pad_dir()
    if not scratch_pad:
        logger.error("Could not locate scratch-pad directory. Set SCRATCH_PAD_DIR.")
        return

    # Check if today's daily-summary.md already exists
    today_str = datetime.date.today().isoformat()
    daily_dir = scratch_pad / "dailies" / today_str
    summary_file = daily_dir / "daily-summary.md"
    
    if summary_file.exists():
        # Another machine (or a manual run) already did it!
        logger.info(f"Summary for {today_str} already exists. Skipping run to prevent duplicates.")
        return
        
    # We need to run it!
    logger.info(f"No summary found for {today_str}. Running daily-summary.ts...")
    
    # Ensure dailies folder exists
    daily_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Run the node script using npx
        cmd = [
            "npx" if os.name != 'nt' else "npx.cmd", 
            "tsx", 
            "scripts/daily-summary.ts", 
            "--output", 
            f"dailies/{today_str}/daily-summary.md"
        ]
        
        result = subprocess.run(
            cmd,
            cwd=str(scratch_pad),
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Successfully generated EOD summary.")
        logger.debug(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to generate summary. Exit code {e.returncode}")
        logger.error(f"STDOUT: {e.stdout}")
        logger.error(f"STDERR: {e.stderr}")
    except Exception as e:
        logger.exception("Unexpected error running daily-summary.ts")

def main():
    logger.info("Starting Weaver Daemon...")
    
    # Run every day at 23:59
    schedule.every().day.at("23:59").do(trigger_eod_wrapup)
    
    logger.info("Schedule configured:")
    for job in schedule.get_jobs():
        logger.info(f" - {job}")
        
    logger.info("Entering wait loop. Press Ctrl+C to exit.")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Weaver Daemon stopped by user.")

if __name__ == "__main__":
    main()
