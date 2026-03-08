---
name: auto-clipper
displayName: AutoClipper
description: Automatically scans a watch folder for media files, analyzes them using ffmpeg scene detection and loudness analysis, generates highlight clips, and organizes output. Supports cron-based scheduling and Agent Swarm integration.
version: 1.1.0
---

# AutoClipper

Automatic video clip and highlight generator for OpenClaw. Monitors a folder for new media files, detects interesting segments using scene detection and loudness analysis, creates clips with ffmpeg, and organizes output into date-stamped folders.

## Purpose

AutoClipper enables OpenClaw agents to automatically:

- **Monitor a watch folder** for new media files (videos, screen recordings, camera clips)
- **Analyze media** using ffmpeg scene detection and audio loudness analysis
- **Generate clips** from detected highlights (scene changes, loud/speech segments)
- **Organize output** into date-based folders with configurable naming
- **Schedule runs** via cron for fully automated workflows
- **Delegate analysis** to Agent Swarm for intelligent clip planning (optional)

## Use Cases

- **Screen recording highlights**: Auto-clip key moments from Loom/OBS recordings
- **Meeting recaps**: Extract segments with speech activity from meeting recordings
- **Content creation**: Batch-process raw footage into short clips
- **Security camera clips**: Pull scene-change segments from camera feeds
- **Gaming highlights**: Auto-clip action moments based on audio peaks

## Architecture

```
Watch Folder (configurable)
       |
       v
Media Scanner (filter by extension, skip processed)
       |
       v
Analysis Engine
  +-- Scene Detection (ffmpeg select filter, threshold-based)
  +-- Loudness Analysis (ffmpeg volumedetect, peak dB threshold)
  +-- Agent Swarm (optional, for AI-driven clip planning)
       |
       v
Clip Engine (ffmpeg trim / transcode)
       |
       v
Output Organizer (date-based folders, deduplication)
```

## Configuration (config.json)

All paths support `~` (home directory) and `$ENV_VAR` expansion.

```json
{
  "watchFolder": "~/Downloads/Recordings",
  "outputFolder": "~/Videos/Clips",
  "fileExtensions": [".mp4", ".mov", ".mkv", ".avi", ".webm"],
  "processedLog": "logs/processed.json",
  "watchPollInterval": 60,
  "clipSettings": {
    "defaultDuration": 60,
    "minClipDuration": 10,
    "maxClipDuration": 300,
    "outputCodec": "h264",
    "outputFormat": "mp4",
    "fastTrim": true
  },
  "sceneDetection": {
    "enabled": true,
    "threshold": 0.3,
    "minSceneDuration": 5
  },
  "loudnessAnalysis": {
    "enabled": true,
    "peakThresholdDb": -10.0,
    "minLoudSegmentDuration": 5
  },
  "intentRouter": {
    "enabled": false,
    "model": "openrouter/minimax/minimax-m2.5"
  },
  "cron": {
    "schedule": "0 * * * *",
    "enabled": false
  },
  "notifications": {
    "enabled": false,
    "channel": "discord"
  }
}
```

### Configuration Keys

| Key | Type | Description |
|-----|------|-------------|
| `watchFolder` | string | Directory to monitor for new media files |
| `outputFolder` | string | Base directory for generated clips |
| `fileExtensions` | string[] | File extensions to process |
| `processedLog` | string | Path (relative to skill dir) for tracking processed files |
| `watchPollInterval` | int | Seconds between polls in watch mode |
| `clipSettings.defaultDuration` | int | Default clip length in seconds |
| `clipSettings.minClipDuration` | int | Minimum segment length to clip |
| `clipSettings.maxClipDuration` | int | Maximum segment length to clip |
| `clipSettings.fastTrim` | bool | Use `-c copy` for fast trimming (no re-encode) |
| `sceneDetection.enabled` | bool | Enable ffmpeg scene detection |
| `sceneDetection.threshold` | float | Scene change sensitivity (0.0-1.0, lower = more sensitive) |
| `loudnessAnalysis.enabled` | bool | Enable audio loudness analysis |
| `loudnessAnalysis.peakThresholdDb` | float | Volume threshold in dB (e.g., -10.0) |
| `intentRouter.enabled` | bool | Enable Agent Swarm for AI-driven analysis |

## CLI Usage

```bash
# Run once (scan, analyze, and create clips)
python3 scripts/auto_clipper.py run

# Dry run (show what would be processed without creating clips)
python3 scripts/auto_clipper.py run --dry-run

# Force reprocess all files (ignore processed log)
python3 scripts/auto_clipper.py run --force

# Start continuous watcher mode
python3 scripts/auto_clipper.py watch

# Show current status
python3 scripts/auto_clipper.py status
```

## Cron Setup

```bash
# Add to crontab (crontab -e)
# Run every hour
0 * * * * /path/to/auto-clipper/scripts/run.sh

# Run daily at 9 AM
0 9 * * * /path/to/auto-clipper/scripts/run.sh
```

The `run.sh` launcher handles lock files to prevent overlapping runs and verifies ffmpeg is available.

## Dependencies

| Tool | Purpose | Required |
|------|---------|----------|
| **ffmpeg** | Video trimming, transcoding, scene detection, loudness analysis | Yes |
| **ffprobe** | Media metadata extraction (duration, codec info) | Yes |
| **Python 3.8+** | Runtime | Yes |
| **Agent Swarm** | AI-driven clip planning (via OpenClaw gateway) | Optional |

## Analysis Methods

### Scene Detection

Uses ffmpeg's `select` filter with a configurable threshold to detect visual scene changes. Segments between scene boundaries that meet the minimum duration are selected as clip candidates.

### Loudness Analysis

Uses ffmpeg's `volumedetect` filter to scan audio in windows, identifying segments where mean volume exceeds a configurable dB threshold. This catches speech, music, and action moments.

### Agent Swarm Integration

When `intentRouter.enabled` is `true`, AutoClipper delegates analysis to Agent Swarm via the OpenClaw gateway. The AI model returns structured clip plans with timestamps and descriptions.

## Directory Structure

```
auto-clipper/
├── SKILL.md              # Skill specification
├── _meta.json            # Skill metadata
├── config.json           # Configuration
├── README.md             # Quick-start guide
├── requirements.txt      # Python dependencies
├── .gitignore            # Git ignore rules
├── scripts/
│   ├── auto_clipper.py   # Main entry point (scan, analyze, clip)
│   └── run.sh            # Cron launcher with lock file support
└── logs/
    └── processed.json    # Tracks processed files (auto-generated)
```

## Implementation Status

### Phase 1: Core (Complete)
- [x] Folder scanner with extension filtering
- [x] Basic ffmpeg trim operation
- [x] Processed file tracking
- [x] CLI entry point with run/watch/status commands
- [x] Config-driven paths (no hardcoded values)

### Phase 2: Intelligence (Complete)
- [x] Scene detection via ffmpeg select filter
- [x] Loudness analysis via ffmpeg volumedetect
- [x] Metadata extraction with ffprobe
- [x] Segment deduplication and overlap resolution
- [x] Agent Swarm integration stub (delegates to gateway when enabled)

### Phase 3: Automation (Complete)
- [x] Cron launcher script with lock file
- [x] Continuous watcher mode with configurable poll interval
- [x] Output organization in date-based folders
- [x] ffmpeg binary check at startup

### Phase 4: Advanced (TODO)
- [ ] Multi-clip compilation (stitch segments into single video)
- [ ] Overlay/watermark support
- [ ] Notification system (Discord, WhatsApp)
- [ ] Custom clip templates

## Keywords

video, clip, highlight, trim, ffmpeg, scene detection, loudness, audio analysis,
automation, cron, watch folder, media processing, screen recording
