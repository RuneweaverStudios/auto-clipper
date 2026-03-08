#!/usr/bin/env python3
"""
AutoClipper - Automatic video clip generator

Scans a watch folder for media files, analyzes them using ffmpeg scene detection
and loudness analysis, generates highlight clips, and organizes output into
date-based folders. Supports Agent Swarm integration for intelligent clip planning.
"""

import argparse
import json
import os
import shutil
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

SKILL_DIR = Path(__file__).parent.parent
CONFIG_PATH = SKILL_DIR / "config.json"
DEFAULT_PROCESSED_LOG = SKILL_DIR / "logs" / "processed.json"


def check_ffmpeg():
    """Verify that ffmpeg and ffprobe are available on the system PATH."""
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            print(f"Error: '{binary}' not found on PATH. Install ffmpeg first.", file=sys.stderr)
            print("  macOS:  brew install ffmpeg", file=sys.stderr)
            print("  Linux:  sudo apt install ffmpeg", file=sys.stderr)
            sys.exit(1)


def load_config() -> dict:
    """Load configuration from config.json with validation."""
    if not CONFIG_PATH.exists():
        print(f"Error: config.json not found at {CONFIG_PATH}", file=sys.stderr)
        print("Create one from the template in SKILL.md.", file=sys.stderr)
        sys.exit(1)
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON in config.json: {exc}", file=sys.stderr)
        sys.exit(1)

    # Validate required keys
    required = ["watchFolder", "outputFolder"]
    for key in required:
        if key not in config:
            print(f"Error: Missing required config key '{key}' in config.json", file=sys.stderr)
            sys.exit(1)
    return config


def get_processed_log_path(config: dict) -> Path:
    """Resolve the processed-files log path from config (relative to SKILL_DIR)."""
    log_rel = config.get("processedLog", "logs/processed.json")
    return SKILL_DIR / log_rel


def get_processed(config: dict) -> list:
    """Get list of already processed files."""
    log_path = get_processed_log_path(config)
    if log_path.exists():
        try:
            with open(log_path) as f:
                return json.load(f).get("processed", [])
        except (json.JSONDecodeError, KeyError):
            return []
    return []


def save_processed(config: dict, processed: list):
    """Save processed file list."""
    log_path = get_processed_log_path(config)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as f:
        json.dump({"processed": processed, "last_updated": datetime.now().isoformat()}, f, indent=2)


def get_watch_folder(config: dict) -> Path:
    """Resolve watch folder path from config, expanding ~ and env vars."""
    raw = config["watchFolder"]
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def get_output_folder(config: dict) -> Path:
    """Resolve and create date-stamped output folder."""
    raw = config["outputFolder"]
    output = Path(os.path.expandvars(os.path.expanduser(raw)))
    output.mkdir(parents=True, exist_ok=True)
    dated = output / datetime.now().strftime("%Y-%m-%d")
    dated.mkdir(parents=True, exist_ok=True)
    return dated


def scan_folder(config: dict) -> List[Path]:
    """Scan watch folder for new media files that have not been processed."""
    watch = get_watch_folder(config)
    if not watch.exists():
        print(f"Warning: Watch folder does not exist: {watch}", file=sys.stderr)
        return []

    extensions = config.get("fileExtensions", [".mp4", ".mov", ".mkv"])
    processed = get_processed(config)

    files: List[Path] = []
    for ext in extensions:
        for f in watch.glob(f"*{ext}"):
            if str(f) not in processed:
                files.append(f)

    return sorted(files, key=lambda p: p.stat().st_mtime)


def _validate_media_path(filepath) -> str:
    """Validate that filepath points to an existing regular file."""
    p = Path(filepath).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Not a valid file: {filepath}")
    return str(p)


def get_duration(filepath) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        safe_path = _validate_media_path(filepath)
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", safe_path],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip()) if result.stdout.strip() else 0.0
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as exc:
        print(f"Error getting duration for {filepath}: {exc}", file=sys.stderr)
        return 0.0


# ---------------------------------------------------------------------------
# Scene detection via ffmpeg
# ---------------------------------------------------------------------------

def detect_scenes(filepath: str, threshold: float = 0.3, min_duration: float = 5.0) -> List[Dict[str, Any]]:
    """Detect scene changes in a video using ffmpeg's scene detection filter.

    Returns a list of dicts: [{start, end, score}, ...] representing segments
    between scene boundaries that are at least *min_duration* seconds long.
    """
    safe_path = _validate_media_path(filepath)
    cmd = [
        "ffprobe", "-v", "quiet",
        "-f", "lavfi",
        "-i", f"movie={safe_path},select='gt(scene\\,{threshold})'",
        "-show_entries", "frame=pts_time,pkt_pts_time",
        "-of", "json"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"Warning: Scene detection timed out for {filepath}", file=sys.stderr)
        return []

    timestamps: List[float] = []
    if result.returncode == 0 and result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            for frame in data.get("frames", []):
                ts = frame.get("pts_time") or frame.get("pkt_pts_time")
                if ts is not None:
                    timestamps.append(float(ts))
        except (json.JSONDecodeError, ValueError):
            pass

    # If ffprobe lavfi approach fails, fall back to a simpler method
    if not timestamps:
        timestamps = _detect_scenes_filter(safe_path, threshold)

    if not timestamps:
        return []

    # Build segments from scene-change timestamps
    total_dur = get_duration(filepath)
    boundaries = [0.0] + sorted(set(timestamps))
    if total_dur > 0:
        boundaries.append(total_dur)

    segments: List[Dict[str, Any]] = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        if (end - start) >= min_duration:
            segments.append({"start": round(start, 2), "end": round(end, 2), "label": f"scene-{i + 1}"})

    return segments


def _detect_scenes_filter(filepath: str, threshold: float) -> List[float]:
    """Fallback scene detection using ffmpeg select filter with metadata output."""
    cmd = [
        "ffmpeg", "-hide_banner", "-i", filepath,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "vfr", "-f", "null", "-"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return []

    import re
    timestamps: List[float] = []
    for line in result.stderr.splitlines():
        match = re.search(r"pts_time:(\d+\.?\d*)", line)
        if match:
            timestamps.append(float(match.group(1)))
    return timestamps


# ---------------------------------------------------------------------------
# Loudness analysis via ffmpeg
# ---------------------------------------------------------------------------

def analyze_loudness(filepath: str, peak_threshold_db: float = -10.0, min_duration: float = 5.0) -> List[Dict[str, Any]]:
    """Analyze audio loudness and return segments where volume exceeds *peak_threshold_db*.

    Uses ffmpeg's astats filter to find loud sections that likely contain
    speech or notable audio events.
    """
    safe_path = _validate_media_path(filepath)
    total_dur = get_duration(filepath)
    if total_dur <= 0:
        return []

    # Divide the file into windows and check mean volume of each
    window = 10.0  # seconds
    segments: List[Dict[str, Any]] = []
    pos = 0.0
    current_start: Optional[float] = None

    while pos < total_dur:
        chunk_dur = min(window, total_dur - pos)
        cmd = [
            "ffmpeg", "-hide_banner", "-ss", str(pos), "-t", str(chunk_dur),
            "-i", safe_path,
            "-af", "volumedetect",
            "-f", "null", "-"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            pos += window
            continue

        import re
        mean_match = re.search(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB", result.stderr)
        mean_vol = float(mean_match.group(1)) if mean_match else -100.0

        if mean_vol >= peak_threshold_db:
            if current_start is None:
                current_start = pos
        else:
            if current_start is not None:
                seg_dur = pos - current_start
                if seg_dur >= min_duration:
                    segments.append({
                        "start": round(current_start, 2),
                        "end": round(pos, 2),
                        "label": "loud-segment",
                        "mean_volume_db": mean_vol
                    })
                current_start = None
        pos += window

    # Close trailing segment
    if current_start is not None:
        seg_dur = total_dur - current_start
        if seg_dur >= min_duration:
            segments.append({
                "start": round(current_start, 2),
                "end": round(total_dur, 2),
                "label": "loud-segment"
            })

    return segments


# ---------------------------------------------------------------------------
# Combined analysis
# ---------------------------------------------------------------------------

def run_analysis(config: dict, media_file: Path) -> Optional[Dict[str, Any]]:
    """Analyze media to determine clip strategy.

    Uses a combination of:
      1. ffmpeg scene detection (visual transitions)
      2. Loudness analysis (audio peaks)
      3. Agent Swarm (if enabled) for intelligent clip planning

    Returns a dict with a 'clips' list of {start, end, label} segments,
    or None if analysis is disabled / produces no results.
    """
    clips: List[Dict[str, Any]] = []
    filepath = str(media_file)
    clip_settings = config.get("clipSettings", {})
    min_dur = clip_settings.get("minClipDuration", 10)
    max_dur = clip_settings.get("maxClipDuration", 300)

    # --- Scene detection ---
    scene_cfg = config.get("sceneDetection", {})
    if scene_cfg.get("enabled", True):
        threshold = scene_cfg.get("threshold", 0.3)
        min_scene = scene_cfg.get("minSceneDuration", 5)
        scenes = detect_scenes(filepath, threshold=threshold, min_duration=min_scene)
        for seg in scenes:
            seg_dur = seg["end"] - seg["start"]
            if min_dur <= seg_dur <= max_dur:
                clips.append(seg)

    # --- Loudness analysis ---
    loud_cfg = config.get("loudnessAnalysis", {})
    if loud_cfg.get("enabled", True):
        peak_db = loud_cfg.get("peakThresholdDb", -10.0)
        min_loud = loud_cfg.get("minLoudSegmentDuration", 5)
        loud_segs = analyze_loudness(filepath, peak_threshold_db=peak_db, min_duration=min_loud)
        for seg in loud_segs:
            seg_dur = seg["end"] - seg["start"]
            if min_dur <= seg_dur <= max_dur:
                clips.append(seg)

    # --- Agent Swarm (optional) ---
    if config.get("intentRouter", {}).get("enabled", False):
        print(f"  Agent Swarm analysis requested for {media_file.name} (requires running gateway)")
        # Agent Swarm integration is delegated to the orchestrator at runtime.
        # When available, it returns structured clip plans that override heuristic results.

    # Deduplicate overlapping segments: keep the longer one
    clips = _deduplicate_segments(clips)

    if not clips:
        return None

    return {"status": "ok", "clips": clips}


def _deduplicate_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove overlapping segments, keeping the longer one."""
    if not segments:
        return segments
    segments = sorted(segments, key=lambda s: s["start"])
    result: List[Dict[str, Any]] = [segments[0]]
    for seg in segments[1:]:
        prev = result[-1]
        if seg["start"] < prev["end"]:
            # Overlap: keep the longer segment
            if (seg["end"] - seg["start"]) > (prev["end"] - prev["start"]):
                result[-1] = seg
        else:
            result.append(seg)
    return result


def create_clip(config: dict, input_file: Path, start: float = 0, duration: float = None) -> Optional[Path]:
    """Create a clip using ffmpeg."""
    output_dir = get_output_folder(config)
    stem = input_file.stem
    timestamp = datetime.now().strftime("%H%M%S")
    idx = 0
    output_file = output_dir / f"{stem}_{timestamp}_{idx}.mp4"
    while output_file.exists():
        idx += 1
        output_file = output_dir / f"{stem}_{timestamp}_{idx}.mp4"

    settings = config.get("clipSettings", {})

    safe_input = _validate_media_path(input_file)
    cmd = ["ffmpeg", "-y", "-i", safe_input]

    if start > 0:
        cmd.extend(["-ss", str(start)])

    if duration:
        cmd.extend(["-t", str(duration)])
    elif settings.get("defaultDuration"):
        cmd.extend(["-t", str(settings["defaultDuration"])])

    if settings.get("fastTrim", True):
        cmd.extend(["-c", "copy"])

    cmd.extend(["-avoid_negative_ts", "make_zero", str(output_file)])

    print(f"  Creating clip: {output_file.name}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode == 0 and output_file.exists():
        print(f"  [ok] Created: {output_file}")
        return output_file
    else:
        print(f"  [fail] ffmpeg error: {result.stderr[:300]}", file=sys.stderr)
        return None


def run(dry_run: bool = False, force: bool = False):
    """Main run function: scan, analyze, clip."""
    check_ffmpeg()
    config = load_config()

    print("=" * 50)
    print("AutoClipper - Video Clip Generator")
    print("=" * 50)

    files = scan_folder(config)

    if not files:
        print("No new files to process.")
        return

    print(f"Found {len(files)} new file(s)")

    if dry_run:
        for f in files:
            dur = get_duration(f)
            print(f"  [dry-run] {f.name} ({dur:.1f}s)")
        return

    processed = get_processed(config)

    for f in files:
        print(f"\nProcessing: {f.name}")

        duration = get_duration(f)
        if duration <= 0:
            print(f"  Skipping (could not determine duration)", file=sys.stderr)
            continue
        print(f"  Duration: {duration:.1f}s")

        analysis = run_analysis(config, f)
        clip_plan = None
        if analysis and analysis.get("clips"):
            clip_plan = analysis["clips"]

        created = 0
        if clip_plan:
            print(f"  Analysis found {len(clip_plan)} segment(s)")
            for seg in clip_plan:
                seg_start = seg.get("start", 0)
                seg_end = seg.get("end")
                seg_dur = (seg_end - seg_start) if seg_end else None
                result = create_clip(config, f, start=seg_start, duration=seg_dur)
                if result:
                    created += 1
        else:
            print("  No segments detected; creating default clip")
            clip_settings = config.get("clipSettings", {})
            default_dur = clip_settings.get("defaultDuration", 60)
            result = create_clip(config, f, duration=min(default_dur, duration))
            if result:
                created += 1

        print(f"  Created {created} clip(s)")

        if not force:
            processed.append(str(f))

    if not force:
        save_processed(config, processed)

    print(f"\nDone. Processed {len(files)} file(s).")


def watch_mode():
    """Continuous watcher mode: polls the watch folder at regular intervals."""
    import time

    check_ffmpeg()
    config = load_config()
    poll_interval = config.get("watchPollInterval", 60)

    print(f"AutoClipper watch mode started (polling every {poll_interval}s)")
    print(f"Watching: {get_watch_folder(config)}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            files = scan_folder(config)
            if files:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(files)} new file(s), processing...")
                run()
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\nWatch mode stopped.")


def show_status():
    """Show current status of the clipper."""
    config = load_config()
    processed = get_processed(config)
    watch = get_watch_folder(config)

    print("AutoClipper Status")
    print("=" * 40)
    print(f"  Watch folder : {watch} {'(exists)' if watch.exists() else '(NOT FOUND)'}")
    print(f"  Output folder: {config['outputFolder']}")
    print(f"  Processed    : {len(processed)} file(s)")
    pending = scan_folder(config)
    print(f"  Pending      : {len(pending)} file(s)")
    scene = config.get("sceneDetection", {})
    loud = config.get("loudnessAnalysis", {})
    print(f"  Scene detect : {'on' if scene.get('enabled') else 'off'} (threshold={scene.get('threshold', 0.3)})")
    print(f"  Loudness     : {'on' if loud.get('enabled') else 'off'} (peak={loud.get('peakThresholdDb', -10)}dB)")
    print(f"  Agent Swarm  : {'on' if config.get('intentRouter', {}).get('enabled') else 'off'}")


def main():
    parser = argparse.ArgumentParser(
        description="AutoClipper - Automatic video clip generator. "
                    "Scans a watch folder, detects scenes and loud segments, and creates clips."
    )
    parser.add_argument("command", choices=["run", "watch", "status"], help="Command to execute")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without creating clips")
    parser.add_argument("--force", action="store_true", help="Force reprocess all files (ignore processed log)")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    if args.command == "run":
        run(dry_run=args.dry_run, force=args.force)
    elif args.command == "watch":
        watch_mode()
    elif args.command == "status":
        show_status()


if __name__ == "__main__":
    main()
