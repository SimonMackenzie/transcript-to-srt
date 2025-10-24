import streamlit as st
from datetime import datetime, timedelta
import re

# -----------------------
# Helper functions
# -----------------------
def drop_frame_adjust(time_in_seconds, fps):
    if fps not in [29.97, 59.94]:
        return timedelta(seconds=time_in_seconds)

    total_frames = round(time_in_seconds * fps)
    drop_frames = 2 if fps == 29.97 else 4
    frames_per_10_minutes = round(fps * 60 * 10)
    frames_per_minute = round(fps * 60)

    d = total_frames // frames_per_10_minutes
    m = total_frames % frames_per_10_minutes
    dropped = drop_frames * (9 * d + max(0, (m - drop_frames) // (frames_per_minute - drop_frames)))
    adjusted_frames = total_frames - dropped
    return timedelta(seconds=adjusted_frames / fps)

def detect_framerate(file_name):
    name = file_name.lower()
    for val in ["29.97", "30", "25", "24"]:
        if val in name:
            return float(val)
    return 25.0

def parse_timecode(tc):
    return datetime.strptime(tc, "%H:%M:%S.%f")

def fmt_srt(dt):
    return dt.strftime("%H:%M:%S,%f")[:-3]

def wrap_text_to_lines(text, max_chars):
    words = text.split()
    if not words:
        return [""]
    lines = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= max_chars:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines

# -----------------------
# Main conversion
# -----------------------
def convert_to_srt(file_content_bytes, file_name,
                   default_last_duration=3,
                   max_chars_per_line=42,
                   max_lines_per_caption=2,
                   custom_suffix="_converted"):
    fps = detect_framerate(file_name)
    content = file_content_bytes.decode("utf-8")
    pattern = r"\[(\d{2}:\d{2}:\d{2}\.\d{2})\]\s*(.*)"
    parsed = []
    for line in content.splitlines():
        m = re.match(pattern, line)
        if m:
            parsed.append(m.groups())

    if not parsed:
        raise ValueError("No valid timecodes found. Use format: [HH:MM:SS.xx] Text")

    segments = []
    for i, (tc, text) in enumerate(parsed):
        start_dt = parse_timecode(tc)
        if i + 1 < len(parsed):
            next_dt = parse_timecode(parsed[i + 1][0])
            end_dt = next_dt - timedelta(seconds=1 / fps)
        else:
            end_dt = start_dt + timedelta(seconds=default_last_duration)
        start_seconds = start_dt.hour*3600 + start_dt.minute*60 + start_dt.second + start_dt.microsecond/1e6
        end_seconds = end_dt.hour*3600 + end_dt.minute*60 + end_dt.second + end_dt.microsecond/1e6
        duration = max(end_seconds - start_seconds, 0.001)
        segments.append({
            "start_s": start_seconds,
            "end_s": end_seconds,
            "duration_s": duration,
            "text": text.strip()
        })

    srt_entries = []
    for seg in segments:
        lin
