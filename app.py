import streamlit as st
from datetime import datetime, timedelta
import re
import math

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
    # tc expected like "HH:MM:SS.xx" where .xx is centiseconds
    return datetime.strptime(tc, "%H:%M:%S.%f")

def fmt_srt(dt):
    return dt.strftime("%H:%M:%S,%f")[:-3]

def wrap_text_to_lines(text, max_chars):
    """
    Wrap text into lines with <= max_chars characters, preserving words.
    Returns a list of lines.
    """
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
            parsed.append(m.groups())  # (timecode, text)

    if not parsed:
        raise ValueError("No valid timecodes found. Use format: [HH:MM:SS.xx] Text")

    # Build original segments with numeric seconds for accurate splitting
    segments = []
    for i, (tc, text) in enumerate(parsed):
        start_dt = parse_timecode(tc)
        if i + 1 < len(parsed):
            next_dt = parse_timecode(parsed[i + 1][0])
            end_dt = next_dt - timedelta(seconds=1 / fps)
        else:
            end_dt = start_dt + timedelta(seconds=default_last_duration)
        # total seconds (float)
        start_seconds = start_dt.hour*3600 + start_dt.minute*60 + start_dt.second + start_dt.microsecond/1e6
        end_seconds = end_dt.hour*3600 + end_dt.minute*60 + end_dt.second + end_dt.microsecond/1e6
        # Ensure non-negative duration:
        duration = max(end_seconds - start_seconds, 0.001)
        segments.append({
            "start_s": start_seconds,
            "end_s": end_seconds,
            "duration_s": duration,
            "text": text.strip()
        })

    # Now create SRT entries taking wrapping & max lines into account
    srt_entries = []
    for seg in segments:
        lines = wrap_text_to_lines(seg["text"], max_chars_per_line)
        # group wrapped lines into caption blocks of max_lines_per_caption
        grouped = [lines[i:i+max_lines_per_caption] for i in range(0, len(lines), max_lines_per_caption)]
        n_parts = len(grouped)
        # Equal-split duration among parts:
        part_duration = seg["duration_s"] / n_parts if n_parts > 0 else seg["duration_s"]
        for p_idx, group_lines in enumerate(grouped):
            part_start = seg["start_s"] + p_idx * part_duration
            part_end = seg["start_s"] + (p_idx + 1) * part_duration - (1.0 / fps)  # subtract frame to avoid overlap
            if part_end <= part_start:
                part_end = part_start + max(0.001, part_duration)
            # Apply drop-frame adjustment and format
            start_dt_adj = datetime(1900,1,1) + drop_frame_adjust(part_start, fps)
            end_dt_adj = datetime(1900,1,1) + drop_frame_adjust(part_end, fps)
            text_block = "\n".join(group_lines)
            srt_entries.append({
                "start_dt": start_dt_adj,
                "end_dt": end_dt_adj,
                "text": text_block
            })

    # Generate SRT text
    srt_lines = []
    for idx, e in enumerate(srt_entries, start=1):
        srt_lines.append(f"{idx}\n{fmt_srt(e['start_dt'])} --> {fmt_srt(e['end_dt'])}\n{e['text']}\n")

    srt_text = "\n".join(srt_lines)
    preview = "\n".join(srt_lines[:5]) + ("\n...\n" if len(srt_lines) > 5 else "")
    srt_file_name = file_name.rsplit(".", 1)[0] + custom_suffix + ".srt"

    return srt_text, preview, srt_file_name, fps

# -----------------------
# Streamlit UI
# -----------------------
st.set_page_config(page_title="Transcript → SRT", layout="wide")
st.title("🎬 Transcript to SRT Converter")
st.write("Upload a transcript with timecodes like: `[HH:MM:SS.xx] Text`")

# Sidebar controls
st.sidebar.header("Settings")
max_chars = st.sidebar.slider("Max characters per line", 20, 80, 42, help="Wrap text to this many characters per line.")
max_lines = st.sidebar.slider("Max lines per caption", 1, 4, 2, help="Maximum subtitle lines per caption block (typical = 2).")
caption_len_default = st.sidebar.slider("Default caption length (s)", 1, 10, 3)
dark_mode = st.sidebar.checkbox("Dark mode", value=False)
st.sidebar.markdown("---")
st.sidebar.caption("When a caption splits into multiple blocks, duration is split equally across the parts.")

# Theme injection for dark mode (simple)
if dark_mode:
    st.markdown(
        """
        <style>
        :root { color-scheme: dark; }
        .stApp { background-color: #0e1117; color: #e6edf3; }
        .css-1v3fvcr { color: #e6edf3; } /* main text */
        .stButton>button, .stDownloadButton>button { background-color: #2563eb; color: white; }
        textarea, input, .stTextArea, .stTextInput { background-color: #0b1020; color: #e6edf3; }
        .stSidebar { background-color: #08101a; color: #e6edf3; }
        </style>
        """,
        unsafe_allow_html=True
    )
else:
    # Optional: clear custom styles by writing a blank style (playground may persist between runs)
    st.markdown("<style> .stApp { background-color: white; color: black; } </style>", unsafe_allow_html=True)

# File uploader and convert
uploaded_file = st.file_uploader("Upload transcript file", type=["txt", "srt", "log"])

if uploaded_file:
    st.write(f"**Detected frame rate (from filename):** {detect_framerate(uploaded_file.name)} fps")
    if st.button("Convert to SRT"):
        try:
            srt_text, preview, srt_file_name, fps = convert_to_srt(
                uploaded_file.read(),
                uploaded_file.name,
                default_last_duration=caption_len_default,
                max_chars_per_line=max_chars,
                max_lines_per_caption=max_lines
            )

            st.subheader("🔍 Preview (first 5 captions):")
            st.code(preview, language="")

            st.download_button(
                label="⬇️ Download SRT",
                data=srt_text,
                file_name=srt_file_name,
                mime="text/plain"
            )

            st.success(f"SRT generated: {srt_file_name} — {len(srt_text.splitlines())} total lines in file.")
        except Exception as e:
            st.error(f"Conversion error: {e}")
else:
    st.info("Upload a transcript to get started. Example format:\n\n[00:00:01.00] Hello there\n[00:00:03.00] This is a longer sentence that might wrap across lines.")

