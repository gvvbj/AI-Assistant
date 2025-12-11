import cv2
import base64
import os
import tempfile

def extract_frames_base64(video_path, max_frames=5):
    """
    从视频中均匀抽取关键帧，并转换为 Base64。
    max_frames: 限制提取的帧数，防止 Context 爆炸
    """
    if not os.path.exists(video_path):
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        return []

    # 计算采样间隔
    interval = max(1, total_frames // max_frames)
    
    base64_frames = []
    
    for i in range(0, total_frames, interval):
        if len(base64_frames) >= max_frames:
            break
            
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            continue
            
        # 将图片编码为 jpg
        # 降低一点质量以减少 Token 消耗 (quality=70)
        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        encoded_string = base64.b64encode(buffer).decode('utf-8')
        base64_frames.append(f"data:image/jpeg;base64,{encoded_string}")

    cap.release()
    return base64_frames

def is_video_file(file_path):
    if not file_path: return False
    ext = os.path.splitext(file_path)[1].lower()
    return ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']