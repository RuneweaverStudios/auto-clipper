# AutoClipper

Automatic video clip and highlight generator for OpenClaw. Scans a watch folder for media files, analyzes them using ffmpeg scene detection and loudness analysis, and creates clips organized into date-based output folders.

## Quick Start

```bash
# 1. Install ffmpeg (required)
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Ubuntu/Debian

# 2. Edit config.json to set your watch and output folders
#    watchFolder  -> where your videos live
#    outputFolder -> where clips are saved

# 3. Run once
python3 scripts/auto_clipper.py run

# 4. Or start continuous watcher
python3 scripts/auto_clipper.py watch
```

## Requirements

- **ffmpeg** and **ffprobe** on your PATH
- **Python 3.8+**
- **OpenClaw** with Agent Swarm skill (optional, for AI-driven clip planning)

## Usage

```bash
# Scan watch folder and create clips from detected highlights
python3 scripts/auto_clipper.py run

# Preview what would be processed (no clips created)
python3 scripts/auto_clipper.py run --dry-run

# Reprocess everything, ignoring the processed log
python3 scripts/auto_clipper.py run --force

# Continuous watch mode (polls every N seconds, configurable)
python3 scripts/auto_clipper.py watch

# Check status (watch folder, pending files, analysis settings)
python3 scripts/auto_clipper.py status
```

## Configuration

Edit `config.json` to customize behavior. All paths support `~` and `$ENV_VAR` expansion.

| Setting | Default | Description |
|---------|---------|-------------|
| `watchFolder` | `~/Downloads/Recordings` | Directory to monitor |
| `outputFolder` | `~/Videos/Clips` | Where clips are saved |
| `sceneDetection.threshold` | `0.3` | Scene change sensitivity (0-1) |
| `loudnessAnalysis.peakThresholdDb` | `-10.0` | Audio peak threshold in dB |
| `clipSettings.defaultDuration` | `60` | Fallback clip length in seconds |
| `clipSettings.fastTrim` | `true` | Use stream copy (fast, no re-encode) |

## Analysis Methods

AutoClipper uses two analysis methods to find interesting segments:

1. **Scene Detection** -- ffmpeg's `select` filter detects visual transitions (cuts, fades). Segments between scene boundaries are clip candidates.

2. **Loudness Analysis** -- ffmpeg's `volumedetect` identifies audio peaks (speech, music, action). Segments above the dB threshold become clip candidates.

Both methods can be toggled independently in `config.json`. When Agent Swarm is enabled, AI-driven analysis supplements or overrides the heuristic results.

## Cron Scheduling

```bash
# Add to crontab for hourly runs
0 * * * * /path/to/auto-clipper/scripts/run.sh
```

The launcher script uses a lock file to prevent overlapping runs and checks for ffmpeg at startup.

## How It Works

1. Scans the watch folder for supported media files (`.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`)
2. Skips files already in the processed log
3. Runs scene detection and loudness analysis on each file
4. Creates clips for detected segments using ffmpeg
5. Saves clips to a date-stamped output folder
6. Records processed files to avoid reprocessing

See `SKILL.md` for full architecture details and configuration reference.
