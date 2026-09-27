import cv2
import mediapipe as mp
import time
from angle_calculator import calculate_angle

# 初始化 MediaPipe Pose 模型
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

# 定义我们要监测的角度点 (前-中-后，中间是顶点)
ANGLE_TARGETS = {
    # 肘部: 肩-肘-腕
    "L_Elbow": (11, 13, 15),
    "R_Elbow": (12, 14, 16),
    # 肩部: 髋-肩-肘
    "L_Shoulder": (23, 11, 13),
    "R_Shoulder": (24, 12, 14),
    # 髋部: 肩-髋-膝
    "L_Hip": (11, 23, 25),
    "R_Hip": (12, 24, 26),
    # 膝部: 髋-膝-踝
    "L_Knee": (23, 25, 27),
    "R_Knee": (24, 26, 28),
    # 踝部: 膝-踝-脚尖
    "L_Ankle": (25, 27, 31),
    "R_Ankle": (26, 28, 32)
}

def main():
    # 打开本地摄像头
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("无法打开摄像头，请检查摄像头是否连接。")
        return

    # 设置较低的分辨率以换取极低延迟 (KISS原则)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    pTime = 0

    with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # 使用摄像头时进行镜像反转，体验更好
            frame = cv2.flip(frame, 1)

            # MediaPipe 需使用 RGB，而 OpenCV 读取是 BGR
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb.flags.writeable = False # 提高处理性能
            
            # AI 姿态估计推理
            results = pose.process(frame_rgb)
            
            frame_rgb.flags.writeable = True
            
            # 获取画面长宽，用于坐标换算
            h, w, c = frame.shape

            if results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark
                
                # 绘制骨骼连线
                mp_drawing.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2), # 关节点颜色
                    mp_drawing.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2)  # 连线颜色
                )
                
                # 计算并渲染角度
                for label, (p1_idx, p2_idx, p3_idx) in ANGLE_TARGETS.items():
                    try:
                        # 坐标 x, y (归一化值，范围0-1)
                        p1 = [landmarks[p1_idx].x, landmarks[p1_idx].y]
                        p2 = [landmarks[p2_idx].x, landmarks[p2_idx].y] # 顶点
                        p3 = [landmarks[p3_idx].x, landmarks[p3_idx].y]
                        
                        angle = calculate_angle(p1, p2, p3)
                        
                        # 转换顶点坐标供OpenCV绘制
                        cv_pos = (int(p2[0]*w), int(p2[1]*h))
                        
                        # 在关节点绘制角度数字
                        cv2.putText(frame, str(int(angle)), 
                                    cv_pos, 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2, cv2.LINE_AA)
                    except Exception as e:
                        # 如有关节点没被检测到，跳过
                        pass

            # 计算 FPS 以监控性能与延迟
            cTime = time.time()
            fps = 1 / (cTime - pTime) if (cTime - pTime) > 0 else 0
            pTime = cTime
            cv2.putText(frame, f'FPS: {int(fps)}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)

            # 显示结果
            cv2.imshow('AI Motion Capture (Press Q to exit)', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
