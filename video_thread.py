import cv2
import time
import mediapipe as mp
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
from angle_calculator import calculate_angle

mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose
ANGLE_TARGETS = {
    "左肘": (11, 13, 15), "右肘": (12, 14, 16),
    "左肩": (23, 11, 13), "右肩": (24, 12, 14),
    "左髋": (11, 23, 25), "右髋": (12, 24, 26),
    "左膝": (23, 25, 27), "右膝": (24, 26, 28),
    "左踝": (25, 27, 31), "右踝": (26, 28, 32)
}

class VideoThread(QThread):
    frame_ready = Signal(QImage)
    angles_ready = Signal(dict)
    total_frames_ready = Signal(int)
    current_frame_ready = Signal(int)
    fps_ready = Signal(float)
    frame_size_ready = Signal(int, int)
    ankles_dist_ready = Signal(float)
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.playing = True
        self.source = 0  # Default to camera
        self.speed = 1.0
        self.step = 0 
        self.seek_frame = -1
        self._cap_needs_reset = False
        self.display_mode = 0 # 0:混合, 1:仅骨骼, 2:隐藏骨骼
        
        # 针对 120fps 上一帧卡顿的极速缓存系统
        self.frame_cache = [] # 存储 tuples: (frame_idx, frame_bgr)
        self.max_cache_size = 90
        self.cache_cursor_idx = -1 

    def set_display_mode(self, mode: int):
        self.display_mode = mode

    def change_source(self, src):
        self.source = src
        self._cap_needs_reset = True
        
    def set_playing(self, state: bool):
        self.playing = state
        
    def set_speed(self, speed: float):
        self.speed = speed

    def step_forward(self):
        self.step = 1
        
    def step_backward(self):
        self.step = -1
        
    def request_seek(self, frame_num):
        # Allow GUI slider to request precise seek
        self.seek_frame = frame_num
        self.step = 1 # Force process one frame exactly to preview slider pos
        
    def stop(self):
        self.running = False
        self.wait()

    def run(self):
        cap = cv2.VideoCapture(self.source)

        with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
            while self.running:
                if self._cap_needs_reset:
                    cap.release()
                    cap = cv2.VideoCapture(self.source)
                    self._cap_needs_reset = False
                    self.playing = True
                    
                    # If this is a video file, emit total frames count initially
                    if isinstance(self.source, str) and cap.isOpened():
                        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        if fps <= 0: fps = 30.0
                        self.total_frames_ready.emit(total_frames)
                        self.fps_ready.emit(fps)
                    else:
                        self.total_frames_ready.emit(0)
                        self.fps_ready.emit(30.0)

                if not cap.isOpened():
                    time.sleep(0.1)
                    continue

                # Handle seek request logic asynchronously 
                if self.seek_frame >= 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, self.seek_frame)
                    self.seek_frame = -1
                    self.frame_cache.clear()
                    self.cache_cursor_idx = -1
                    
                if not self.playing and self.step == 0:
                    time.sleep(0.01)
                    continue

                frame_loaded = None
                frame_idx = -1
                start_t = time.time()

                # Step Backward logic via Cache to prevent massive OpenCV lagging on 120fps
                if self.step == -1:
                    if self.cache_cursor_idx == -1:
                        self.cache_cursor_idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
                        
                    target_idx = self.cache_cursor_idx - 1
                    # Search target in cache
                    for f_idx, f_bgr in self.frame_cache:
                        if f_idx == target_idx:
                            frame_loaded = f_bgr.copy()
                            frame_idx = f_idx
                            self.cache_cursor_idx = f_idx
                            break
                            
                    if frame_loaded is None:
                        # Cache Miss, hard reset hardware FFMPEG pointer
                        if target_idx >= 0:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
                        self.frame_cache.clear()
                        self.cache_cursor_idx = -1
                    self.step = 0

                # Step Forward logic via Cache
                elif self.step == 1:
                    if self.cache_cursor_idx != -1 and len(self.frame_cache) > 0 and self.cache_cursor_idx < self.frame_cache[-1][0]:
                        target_idx = self.cache_cursor_idx + 1
                        for f_idx, f_bgr in self.frame_cache:
                            if f_idx == target_idx:
                                frame_loaded = f_bgr.copy()
                                frame_idx = f_idx
                                self.cache_cursor_idx = f_idx
                                break
                    self.step = 0
                    
                # Hardware Resync on resuming Play if we were browsing cache
                if self.playing and self.cache_cursor_idx != -1:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, self.cache_cursor_idx + 1)
                    self.cache_cursor_idx = -1
                    self.frame_cache.clear()

                # If not fetched from memory cache, read physical frame naturally
                if frame_loaded is None:
                    ret, frame = cap.read()
                    if not ret:
                        if isinstance(self.source, int):
                            time.sleep(0.01)
                            continue
                        else:
                            self.playing = False
                            cap.set(cv2.CAP_PROP_POS_FRAMES, cap.get(cv2.CAP_PROP_POS_FRAMES) - 1)
                            continue
                            
                    frame_loaded = frame
                    frame_idx = cap.get(cv2.CAP_PROP_POS_FRAMES) - 1
                    
                    # Update rolling cache
                    self.frame_cache.append((frame_idx, frame_loaded.copy()))
                    if len(self.frame_cache) > self.max_cache_size:
                        self.frame_cache.pop(0)
                        
                frame = frame_loaded
                
                # Emit current frame to sync UI timeline slider occasionally!
                if isinstance(self.source, str):
                    self.current_frame_ready.emit(int(frame_idx))
                
                if isinstance(self.source, int):
                    frame = cv2.flip(frame, 1)

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_rgb.flags.writeable = False
                results = pose.process(frame_rgb)
                frame_rgb.flags.writeable = True

                # 无论是否检测到人体，都要先取得画面尺寸，供坐标换算与 QWidget 渲染使用
                h, w, c = frame.shape

                angles_dict = {}
                
                # 如果是仅骨骼模式，不管有没有检测到人，先把背景涂黑
                if self.display_mode == 1:
                    frame.fill(17) # RGB #111111 接近黑色

                if results.pose_landmarks:
                    landmarks = results.pose_landmarks.landmark
                    
                    # 计算角度数据，因为无论画不画骨架，右侧面板都需要数字
                    for label, (p1_idx, p2_idx, p3_idx) in ANGLE_TARGETS.items():
                        try:
                            p1 = [landmarks[p1_idx].x, landmarks[p1_idx].y]
                            p2 = [landmarks[p2_idx].x, landmarks[p2_idx].y]
                            p3 = [landmarks[p3_idx].x, landmarks[p3_idx].y]
                            ang = calculate_angle(p1, p2, p3)
                            angles_dict[label] = round(ang, 1) 
                            
                            # 只有在非隐藏骨骼模式(模式0和1)才在画面上渲染角度标尺
                            if self.display_mode != 2:
                                cv_pos = (int(p2[0]*w), int(p2[1]*h))
                                cv2.putText(frame, str(int(ang)), cv_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)
                        except:
                            pass
                            
                    # 同理，非隐藏模式才画骨架线条
                    if self.display_mode != 2:
                        bone_spec = mp_drawing.DrawingSpec(color=(220, 220, 220), thickness=2, circle_radius=1) 
                        joint_spec = mp_drawing.DrawingSpec(color=(0, 165, 255), thickness=4, circle_radius=4)
                        mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS, joint_spec, bone_spec)
                        
                    # 为外部提供步幅测量：测算脚踝(27/28)距离，转成原视频物理像素以备换算
                    try:
                        import math
                        l_ankle = results.pose_landmarks.landmark[27]
                        r_ankle = results.pose_landmarks.landmark[28]
                        px_dx = (l_ankle.x - r_ankle.x) * w
                        px_dy = (l_ankle.y - r_ankle.y) * h
                        self.ankles_dist_ready.emit(math.sqrt(px_dx**2 + px_dy**2))
                    except:
                        pass
                        
                # 无论是否有骨架，都要对外输出真实视频比例尺寸防缩放变形
                if h > 0 and w > 0:
                    self.frame_size_ready.emit(w, h)
                
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                bytes_per_line = ch * w
                qt_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                
                self.frame_ready.emit(qt_img)
                self.angles_ready.emit(angles_dict)
                
                process_time = time.time() - start_t
                if isinstance(self.source, str):
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    if fps <= 0: fps = 30
                    target_delay = 1.0 / (fps * self.speed)
                else:
                    target_delay = 1.0 / 30.0 
                
                # 恢复极致平滑的自旋锁：保障60fps不超速，120帧不丢帧 (允许因AI计算极限变为自然流畅的慢动作)
                sleep_time = target_delay - process_time
                if sleep_time > 0 and self.playing:
                    if sleep_time > 0.016: 
                        time.sleep(sleep_time - 0.015)
                    while time.time() - start_t < target_delay:
                        pass
                
        cap.release()
