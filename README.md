# assemble-video
就是仿照剪映小助手导出的json来制作视频
> **FFmpeg-powered JSON-to-MP4 builder**  
> 给一份规范 JSON，一键输出带字幕、旁白、Avatar 叠加的成片。


## 🚀 快速开始
```bash
# 安装
git clone https://github.com/Joir-Jio/json2video-ffmpeg.git
cd assemble-video
pip install -r requirements.txt 

# 运行
python assemble_video.py spec.json final.mp4
