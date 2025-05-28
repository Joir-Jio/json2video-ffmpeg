#!/usr/bin/env python3
"""
assemble_video.py  ·  Build a final MP4 from JSON spec (slow-motion fill)

2025-05-30
----------
* src < target 时，用 setpts 放慢而不是 stream_loop。
* 字幕路径 Windows-safe (C\:/… + quotes)。
* 仅 \"audios\" 决定最终声音；无则静音。
"""

from __future__ import annotations
import json, subprocess, tempfile, uuid, shutil
from pathlib import Path
from typing import Dict, List, Any
import requests


# ── helpers ──────────────────────────────────────────────────
def run(cmd: List[str | Path]) -> None:
    cmd = [str(c) for c in cmd]
    print("🛠️", " ".join(cmd))
    subprocess.run(cmd, check=True)

def download(url: str, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    print("⬇️", url.split("?")[0], "→", dst.name)
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dst, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
    return dst

def probe_duration(path: Path) -> float:
    """Return media duration (seconds, float)."""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            text=True
        )
        return float(out.strip())
    except Exception:
        return 0.0

def make_segment(src: Path, dst: Path, target: float) -> Path:
    dur = probe_duration(src)
    if dur == 0:
        raise RuntimeError(f"Cannot probe {src}")

    if dur >= target - 0.01:       # 裁剪
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-ss", "0", "-i", src,  # 用 decode 方式更精准
             "-t", f"{target}",
             "-vf", "scale=1920:1080,fps=30",  # 统一规格
             "-reset_timestamps", "1",
             "-an",                           # 主流程不用源音
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             dst])
    else:                          # 慢放
        ratio = target / dur
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-i", src,
             "-vf", f"setpts={ratio}*PTS,scale=1920:1080,fps=30",
             "-reset_timestamps", "1",
             "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             dst])
    return dst


def ts(sec: float) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s-int(s))*1000):03d}"

def make_srt(subs: List[Dict[str, Any]], dst: Path) -> Path:
    out, n = [], 1
    for b in subs:
        st = float(b.get("start", 0))
        ed = float(b.get("end", st + 2))
        text = str(b.get("text") or b.get("tetx") or
                   b.get("content") or b.get("subtitle") or "")
        out += [str(n), f"{ts(st)} --> {ts(ed)}", text, ""]
        n += 1
    dst.write_text("\n".join(out), encoding="utf-8")
    return dst

def probe_vid_dur(path: Path) -> float:
    """Quick helper for avatar (re-uses probe_duration)."""
    return probe_duration(path)


# ── main assemble ───────────────────────────────────────────
def assemble(spec: Dict[str, Any], output: Path) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="assemble_"))
    print("⚙️", tmp)

    try:
        # 1️⃣  main video segments
        stitched_main = tmp / "main.mp4"
        segs: List[tuple[float, Path]] = []
        for i, v in enumerate(spec["videos"], 1):
            raw = download(v["file"], tmp / f"v_raw_{i}.mp4")
            seg = make_segment(raw, tmp / f"v_seg_{i}.mp4",
                               v["end"] - v["start"])
            segs.append((v["start"], seg))
        segs.sort(key=lambda x: x[0])
        concat_txt = tmp / "concat_v.txt"
        concat_txt.write_text("".join(
            f"file '{p.as_posix()}'\n" for _, p in segs), encoding="utf-8")
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", concat_txt,
             "-c", "copy", stitched_main])

        # 2️⃣  narration audio
        narr = None
        if spec.get("audios"):
            a_parts = []
            for i, a in enumerate(spec["audios"], 1):
                raw = download(a["file"], tmp / f"a_raw_{i}.mp3")
                a_parts.append(raw)  # 不裁剪，假设与时间轴等长
            if a_parts:
                txt = tmp / "concat_a.txt"
                txt.write_text("".join(
                    f"file '{p.as_posix()}'\n" for p in a_parts), encoding="utf-8")
                narr = tmp / "narr.mp3"
                run(["ffmpeg", "-y", "-loglevel", "error",
                     "-f", "concat", "-safe", "0", "-i", txt,
                     "-c", "copy", narr])

        # 3️⃣  subtitles
        srt = None
        if spec.get("subtitles"):
            srt = make_srt(spec["subtitles"], tmp / "subs.srt")

        # 4️⃣  ffmpeg inputs
        inputs = ["-i", stitched_main]      # 0
        filter_parts = []
        last = "0:v"

        # avatars
        for idx, av in enumerate(spec.get("avatars", []), 1):
            av_path = download(av["file"], tmp / f"av_{uuid.uuid4().hex}.mp4")
            inputs += ["-i", av_path]       # 1,2,...
            dur = probe_vid_dur(av_path)
            start = av.get("start", 0)
            end   = av.get("end", start + dur)
            scale = f"scale=iw*{av['size'][0]}:ih*{av['size'][1]}"
            posx  = f"main_w*{av['position'][0]}"
            posy  = f"main_h*{av['position'][1]}"
            enable = f":enable='between(t,{start},{end})'"
            filter_parts.append(
                f"[{idx}:v]{scale}[s{idx}];"
                f"[{last}][s{idx}]overlay={posx}:{posy}{enable}[v{idx}]")
            last = f"v{idx}"

        # subtitles
        if srt:
            srt_path = srt.as_posix().replace(":/", "\\:/")
            filter_parts.append(
                f"[{last}]subtitles='{srt_path}'[vout]")
            last = "vout"

        # audio
        if narr:
            inputs += ["-i", narr]   # 最后一个输入
            map_audio = [str(len(inputs)//2 - 1) + ":a"]  # index of narr
        else:
            map_audio = []

        filter_complex = ";".join(filter_parts) if filter_parts else None

        # 5️⃣  build final cmd
        cmd = ["ffmpeg", "-y", *inputs]
        if filter_complex:
            cmd += ["-filter_complex", filter_complex]
            cmd += ["-map", f"[{last}]"]
        else:
            cmd += ["-map", "0:v"]
        if map_audio:
            cmd += ["-map", map_audio[0], "-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-an"]

        res = spec["output"]["resolution"]
        fps = spec["output"]["fps"]
        cmd += ["-s", f"{res[0]}x{res[1]}", "-r", str(fps),
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                output]

        run(cmd)
        print("✅ saved →", output.resolve())

    finally:
        print("🗑️  temp dir ", tmp)
        # shutil.rmtree(tmp)  # 调试完再打开


# ── CLI ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", help="spec JSON")
    ap.add_argument("out", help="output MP4")
    args = ap.parse_args()
    assemble(json.loads(Path(args.spec).read_text(encoding="utf-8")),
             Path(args.out))
