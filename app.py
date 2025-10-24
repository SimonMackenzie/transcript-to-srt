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

def frames_from_timedelta(td, fps):
    total_seconds = td.total_seconds()
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    frames = round((total_seconds - int(total_seconds)) * fps)
    if frames >= fps:
        frames = int(fps - 1)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"

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
                   export_avid=False,
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
        lines = wrap_text_to_lines(seg["text"], max_chars_per_line)
        grouped = [lines[i:i+max_lines_per_caption] for i in range(0, len(lines), max_lines_per_caption)]
        n_parts = len(grouped)
        part_duration = seg["duration_s"] / n_parts if n_parts > 0 else seg["duration_s"]
        for p_idx, group_lines in enumerate(grouped):
            part_start = seg["start_s"] + p_idx * part_duration
            part_end = seg["start_s"] + (p_idx + 1) * part_duration - (1.0 / fps)
            if part_end <= part_start:
                part_end = part_start + max(0.001, part_duration)
            start_dt_adj = datetime(1900,1,1) + drop_frame_adjust(part_start, fps)
            end_dt_adj = datetime(1900,1,1) + drop_frame_adjust(part_end, fps)
            text_block = "\n".join(group_lines)
            srt_entries.append({
                "start_dt": start_dt_adj,
                "end_dt": end_dt_adj,
                "text": text_block
            })

    if export_avid:
        avid_lines = [
            "@ This file written with the Avid Caption plugin, version 1",
            "",
            "<begin subtitles>"
        ]
        for e in srt_entries:
            start_fc = frames_from_timedelta(e["start_dt"] - datetime(1900,1,1), fps)
            end_fc = frames_from_timedelta(e["end_dt"] - datetime(1900,1,1), fps)
            text_clean = e["text"].replace("\n", " ")
            avid_lines.append(f"{start_fc} {end_fc} {text_clean}")
        avid_lines.append("")
        avid_lines.append("<end subtitles>")
        avid_text = "\n".join(avid_lines)
        preview = "\n".join(avid_lines[2:7]) + ("\n...\n" if len(avid_lines) > 7 else "")
        file_name_out = file_name.rsplit(".",1)[0] + "_avid.txt"
        return avid_text, preview, file_name_out, fps

    else:
        srt_lines = []
        for idx, e in enumerate(srt_entries, start=1):
            srt_lines.append(f"{idx}\n{fmt_srt(e['start_dt'])} --> {fmt_srt(e['end_dt'])}\n{e['text']}\n")
        srt_text = "\n".join(srt_lines)
        preview = "\n".join(srt_lines[:5]) + ("\n...\n" if len(srt_lines) > 5 else "")
        srt_file_name = file_name.rsplit(".", 1)[0] + "_converted.srt"
        return srt_text, preview, srt_file_name, fps

# -----------------------
# Streamlit UI
# -----------------------
st.set_page_config(page_title="TXT to SRT Converter", layout="wide")
st.title("TXT to SRT Converter")

st.markdown("""
Upload your plain-text transcript file (.txt) with lines like:

[13:48:11.12] Join the Rebellion?! Are you
kidding! How?

[13:48:13.02] Quiet down will ya! You got a mouth
bigger than a meteor crater!

Transcript converter will then automatically create the captions end timecode for you using the next start timecode − 1 frame.

A caption splits whenever text exceeds max characters or lines per caption, and each split shares the original duration equally.
""")

# -----------------------
# Sidebar
# -----------------------
st.sidebar.header("Settings / Export Options")

max_chars = st.sidebar.slider("Max characters per line", 20, 80, 42)
max_lines = st.sidebar.slider("Max lines per caption", 1, 4, 2)
caption_len_default = st.sidebar.slider("Default caption length (s)", 1, 10, 3)
export_avid = st.sidebar.checkbox("Export for Avid Media Composer")

# Spacer to push footer to bottom
st.sidebar.markdown("<br><br><br><br><br><br>", unsafe_allow_html=True)

# Footer at bottom of sidebar
st.sidebar.markdown(
    '<div style="text-align: center;">Created by film editor <a href="https://www.simonmackenzie.tv/" style="text-decoration: underline;" target="_blank">Simon Mackenzie</a></div>',
    unsafe_allow_html=True
)

# -----------------------
# File upload & conversion
# -----------------------
uploaded_file = st.file_uploader("Upload transcript file", type=["txt", "srt", "log"])

if uploaded_file:
    st.write(f"**Detected frame rate (from filename):** {detect_framerate(uploaded_file.name)} fps")
    if st.button("Convert"):
        try:
            output_text, preview, file_name_out, fps = convert_to_srt(
                uploaded_file.read(),
                uploaded_file.name,
                default_last_duration=caption_len_default,
                max_chars_per_line=max_chars,
                max_lines_per_caption=max_lines,
                export_avid=export_avid
            )

            st.subheader("🔍 Preview (first 5 lines):")
            st.code(preview, language="")

            st.download_button(
                label="⬇️ Download",
                data=output_text,
                file_name=file_name_out,
                mime="text/plain"
            )

            st.success(f"File generated: {file_name_out} — {len(output_text.splitlines())} total lines.")
        except Exception as e:
            st.error(f"Conversion error: {e}")

