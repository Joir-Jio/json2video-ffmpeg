# assemble-video

> **FFmpeg-powered JSON-to-MP4 builder**  
> 给一份规范 JSON，一键输出带字幕、旁白、Avatar 叠加的成片。

---

## ✨ 特性
- **时间轴精确** – `start / end` 绝对位置 + 自动慢放补时  
- **字幕 / 旁白 / BGM** – SRT 合成、Narration 音轨、可选背景乐  
- **多 Avatar 覆盖** – 指定 `position` & `size`；支持按时间段显示/隐藏  
- **零外部依赖** – 仅用 FFmpeg + Python ≥3.9 + `requests`  
- **跨平台** – macOS / Linux / Windows 均测试通过

## 🚀 快速开始
```bash
# 安装
git clone https://github.com/Joir-Jio/json2video-ffmpeg.git
cd assemble-video
pip install -r requirements.txt 

# 运行
python assemble_video.py spec.json final.mp4
