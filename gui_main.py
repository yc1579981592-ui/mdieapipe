import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QPushButton, QComboBox, 
                               QFileDialog, QGroupBox, QGridLayout, QSlider, QTextEdit)
from PySide6.QtCore import Qt, Slot, QPointF
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QShortcut, QKeySequence
import math
from video_thread import VideoThread

class CalibrationLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.drawing = False
        self.start_pos_img = None
        self.end_pos_img = None
        self.calibrating = False
        self.video_px_per_m = 0.0
        self.video_w = 640
        
        # 极速缩放拖拽功能参数
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        self.panning = False
        self.pan_start = None
        self._cache_pixmap = None
        
        self.setMouseTracking(True)

    def setFrameData(self, pixmap):
        self._cache_pixmap = pixmap
        self.update()

    def _screen_to_image(self, screen_pos):
        if not self._cache_pixmap: return QPointF(0,0)
        base_x = (self.width() - self._cache_pixmap.width()) / 2.0
        base_y = (self.height() - self._cache_pixmap.height()) / 2.0
        ix = (screen_pos.x() - self.pan_offset.x() - base_x) / self.zoom_factor
        iy = (screen_pos.y() - self.pan_offset.y() - base_y) / self.zoom_factor
        return QPointF(ix, iy)
        
    def _image_to_screen(self, img_pos):
        if not self._cache_pixmap: return QPointF(0,0)
        base_x = (self.width() - self._cache_pixmap.width()) / 2.0
        base_y = (self.height() - self._cache_pixmap.height()) / 2.0
        sx = img_pos.x() * self.zoom_factor + base_x + self.pan_offset.x()
        sy = img_pos.y() * self.zoom_factor + base_y + self.pan_offset.y()
        return QPointF(sx, sy)

    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            delta = event.angleDelta().y()
            zoom_step = 1.15 if delta > 0 else 0.85
            
            # 以鼠标当前位置为缩放中心
            mouse_pos = event.position()
            
            new_zoom = self.zoom_factor * zoom_step
            if new_zoom < 1.0:
                new_zoom = 1.0
                self.pan_offset = QPointF(0.0, 0.0)
                
            # 补偿偏移公式保持聚焦点
            if new_zoom > 1.0:
                self.pan_offset = mouse_pos - (mouse_pos - self.pan_offset) * (new_zoom / self.zoom_factor)
                
            self.zoom_factor = new_zoom
            self.update()

    def mousePressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.button() == Qt.LeftButton:
            self.panning = True
            self.pan_start = event.position()
            self.setCursor(Qt.ClosedHandCursor)
        elif self.calibrating and event.button() == Qt.LeftButton:
            self.drawing = True
            self.start_pos_img = self._screen_to_image(event.position())
            self.end_pos_img = self.start_pos_img

    def mouseMoveEvent(self, event):
        if self.panning:
            delta = event.position() - self.pan_start
            self.pan_offset += delta
            self.pan_start = event.position()
            self.update()
        elif self.drawing:
            self.end_pos_img = self._screen_to_image(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if self.panning:
            self.panning = False
            self.setCursor(Qt.CrossCursor if self.calibrating else Qt.ArrowCursor)
        elif self.drawing and event.button() == Qt.LeftButton:
            self.drawing = False
            self.end_pos_img = self._screen_to_image(event.position())
            self.update()
            
            if self.start_pos_img and self._cache_pixmap:
                base_px_dist = math.sqrt((self.end_pos_img.x() - self.start_pos_img.x())**2 + (self.end_pos_img.y() - self.start_pos_img.y())**2)
                if base_px_dist > 5:
                    from PySide6.QtWidgets import QInputDialog
                    meters, ok = QInputDialog.getDouble(self, "设定现实标尺", "这段实地距离是多少(米)?", 1.22, 0.01, 100.0, 2)
                    if ok and meters > 0:
                        scale = self.video_w / self._cache_pixmap.width()
                        video_px_dist = base_px_dist * scale
                        self.video_px_per_m = video_px_dist / meters
            
            self.calibrating = False
            self.setCursor(Qt.ArrowCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(17, 17, 17))
        
        if self._cache_pixmap:
            base_x = (self.width() - self._cache_pixmap.width()) / 2.0
            base_y = (self.height() - self._cache_pixmap.height()) / 2.0
            
            painter.save()
            painter.translate(self.pan_offset.x() + base_x, self.pan_offset.y() + base_y)
            painter.scale(self.zoom_factor, self.zoom_factor)
            
            # 绘制底层视频高阶图像
            painter.drawPixmap(0, 0, self._cache_pixmap)
            
            # 依附于视频平面坐标系的标尺线 (抗锯齿缩放不移位)
            if (self.drawing or self.video_px_per_m > 0) and self.start_pos_img and self.end_pos_img:
                painter.setPen(QPen(Qt.yellow, 2, Qt.DashLine))
                painter.drawLine(self.start_pos_img, self.end_pos_img)
                
            painter.restore()
            
            # 文字固定绘制在屏幕上方浮雕
            if self.video_px_per_m > 0 and not self.drawing:
                c_img = QPointF((self.start_pos_img.x() + self.end_pos_img.x()) / 2, (self.start_pos_img.y() + self.end_pos_img.y()) / 2)
                c_scr = self._image_to_screen(c_img)
                painter.setPen(QPen(Qt.white))
                painter.drawText(c_scr, f"标尺设定: {self.video_px_per_m:.1f} 像素/米")
            elif self.calibrating and not self.drawing:
                painter.setPen(QPen(Qt.green))
                painter.drawText(20, 30, "测距模式：请在画面拖拽标尺线 (可按Ctrl+滚轮缩放)")

class JumpSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
            x = event.position().x()
            val = self.minimum() + (self.maximum() - self.minimum()) * x / self.width()
            val = max(self.minimum(), min(self.maximum(), val))
            self.setValue(int(val))
            self.sliderPressed.emit()
            self.sliderReleased.emit()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            event.accept()
            x = event.position().x()
            val = self.minimum() + (self.maximum() - self.minimum()) * x / self.width()
            val = max(self.minimum(), min(self.maximum(), val))
            self.setValue(int(val))
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
            self.sliderReleased.emit()
        else:
            super().mouseReleaseEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 运动技术分析软件")
        self.resize(1100, 800)
        
        # =========== 现代极简扁平暗色 UI (类似 Windows 11 Dark Mode 或 macOS) ===========
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QWidget { font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; color: #ffffff; }
            QLabel { font-size: 14px; }
            
            QPushButton { 
                background-color: #0078d4; 
                border: none; 
                padding: 8px 16px; 
                color: white; 
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #1084d8; }
            QPushButton:pressed { background-color: #005a9e; }
            
            QComboBox { 
                background-color: #333333; 
                color: white; 
                border: 1px solid #444; 
                padding: 6px; 
                border-radius: 5px;
                font-size: 14px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #333333; color: white; }
            
            QGroupBox { 
                border: 1px solid #3a3a3a; 
                margin-top: 15px; 
                border-radius: 6px;
                background-color: #252526;
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                left: 10px; 
                padding: 0 5px; 
                color: #aaaaaa; 
                font-size: 13px;
            }
            
            /* 进度条现代化样式 */
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #3e3e42;
                margin: 2px 0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                border: none;
                width: 14px;
                margin: -4px 0; 
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #1084d8;
            }
            QSlider::sub-page:horizontal {
                background: #0078d4;
                border-radius: 3px;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # ====== 顶部区域 ======
        top_layout = QHBoxLayout()
        
        # 左侧: 视频画面
        self.video_label = CalibrationLabel("画面准备中，请点击下方按钮打开摄像头或导入本地视频...")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #111111; border: 1px solid #333; border-radius: 8px;")
        self.video_label.setMinimumSize(640, 480) # 降低下限，确保程序可以缩小
        top_layout.addWidget(self.video_label, stretch=5)

        # 右侧: 角度数据面板
        angle_group = QGroupBox("实时骨骼关节角度")
        angle_group.setFixedWidth(220) # 强制限宽，不让它挤占屏幕
        self.angle_layout = QGridLayout(angle_group)
        self.angle_layout.setVerticalSpacing(10)
        self.angle_labels = {}
        
        targets = [
            "左肩", "右肩",
            "左肘", "右肘", 
            "左髋", "右髋", 
            "左膝", "右膝", 
            "左踝", "右踝"
        ]
        
        row = 0
        for t in targets:
            name_lbl = QLabel(t)
            name_lbl.setStyleSheet("color: #bbbbbb;")
            val_lbl = QLabel("---")
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: bold; min-width: 60px;")
            self.angle_layout.addWidget(name_lbl, row, 0)
            self.angle_layout.addWidget(val_lbl, row, 1)
            self.angle_labels[t] = val_lbl
            row += 1
            
        self.angle_layout.setRowStretch(row, 1)
        
        # 将右侧原有的angle_group放入一个垂直布局中，预留位置给下方的打点记录器
        right_layout = QVBoxLayout()
        right_layout.addWidget(angle_group)
        
        # 步频追踪打点面板
        timing_group = QGroupBox("步数测算打点 (快捷键: Z)")
        timing_group.setFixedWidth(220)
        timing_layout = QVBoxLayout(timing_group)
        self.timing_log = QTextEdit()
        self.timing_log.setReadOnly(True)
        self.timing_log.setStyleSheet("background-color: #111111; color: #00ffcc; font-size: 13px; border: 1px solid #444; border-radius: 4px;")
        self.btn_clear_log = QPushButton("清空记录")
        self.btn_clear_log.setStyleSheet("background-color: #444444; padding: 4px;")
        timing_layout.addWidget(self.timing_log)
        timing_layout.addWidget(self.btn_clear_log)
        
        right_layout.addWidget(timing_group)
        
        top_layout.addLayout(right_layout)
        main_layout.addLayout(top_layout)
        
        # ====== 中部区域: 进度控制条 ======
        self.slider_layout = QHBoxLayout()
        self.lbl_time_curr = QLabel("0")
        self.lbl_time_curr.setStyleSheet("color: #bbbbbb; font-size: 13px; min-width: 40px;")
        
        self.slider = JumpSlider(Qt.Horizontal)
        self.slider.setRange(0, 100) # Mock range initially
        self.slider.setStyleSheet("QSlider::handle:horizontal { background-color: #00a5ff; border-radius: 6px; width: 12px; } QSlider::groove:horizontal { height: 4px; background: #333; }")
        self.slider.setEnabled(False) 
        
        self.lbl_time_max = QLabel("0")
        self.lbl_time_max.setStyleSheet("color: #bbbbbb; font-size: 13px; min-width: 40px;")
        
        self.slider_layout.addWidget(self.lbl_time_curr)
        self.slider_layout.addWidget(self.slider)
        self.slider_layout.addWidget(self.lbl_time_max)
        main_layout.addLayout(self.slider_layout)

        # ====== 底部区域: 控制按钮 ======
        control_group = QGroupBox("操作控制")
        control_layout = QHBoxLayout(control_group)

        self.btn_cam = QPushButton("打开摄像头")
        self.btn_vid = QPushButton("导入本地视频...")
        self.btn_calib = QPushButton("画基准标尺")
        self.btn_calib.setStyleSheet("background-color: #107c10;")
        self.btn_play = QPushButton("暂停播放")
        self.btn_play.setStyleSheet("background-color: #d83b01;")
        self.btn_prev = QPushButton("上一帧")
        self.btn_next = QPushButton("下一帧")
        
        control_layout.addWidget(self.btn_cam)
        control_layout.addWidget(self.btn_vid)
        control_layout.addWidget(self.btn_calib)
        control_layout.addSpacing(30)
        control_layout.addWidget(self.btn_play)
        control_layout.addWidget(self.btn_prev)
        control_layout.addWidget(self.btn_next)
        control_layout.addSpacing(30)
        
        lbl_mode = QLabel("显示:")
        control_layout.addWidget(lbl_mode)
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["画面+骨架", "仅看骨架", "隐藏骨架"])
        control_layout.addWidget(self.combo_mode)
        
        control_layout.addSpacing(15)

        lbl_speed = QLabel("倍速:")
        control_layout.addWidget(lbl_speed)
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.5x", "1.0x", "1.5x", "2.0x", "4.0x"])
        self.combo_speed.setCurrentText("1.0x")
        control_layout.addWidget(self.combo_speed)
        control_layout.addStretch()

        main_layout.addWidget(control_group)

        # 确保所有按钮不抢占焦点，避免按空格键时触发了最后点击的按钮
        for btn in [self.btn_cam, self.btn_vid, self.btn_calib, self.btn_play, self.btn_prev, self.btn_next, self.btn_clear_log]:
            btn.setFocusPolicy(Qt.NoFocus)
        self.combo_speed.setFocusPolicy(Qt.NoFocus)
        self.combo_mode.setFocusPolicy(Qt.NoFocus)
        self.slider.setFocusPolicy(Qt.NoFocus)

        # State vars
        self.slider_dragging = False
        self.fps = 30.0
        self.last_step_frame = -1
        self.start_step_frame = -1
        self.step_count = 1
        self.latest_ankles_px = 0.0

        # SIGNAL ATTACHMENTS
        self.btn_cam.clicked.connect(self.on_cam)
        self.btn_vid.clicked.connect(self.on_vid)
        self.btn_calib.clicked.connect(self.on_calibrate)
        self.btn_play.clicked.connect(self.on_play_toggle)
        self.combo_speed.currentTextChanged.connect(self.on_speed_change)
        self.combo_mode.currentIndexChanged.connect(self.on_mode_change)

        self.slider.sliderPressed.connect(self.on_slider_pressed)
        self.slider.sliderReleased.connect(self.on_slider_released)
        self.slider.valueChanged.connect(self.on_slider_moved)
        self.btn_clear_log.clicked.connect(self.clear_timing_log)

        # Init Video Thread
        self.v_thread = VideoThread()

        # Global Hotkeys (Bulletproof Focus Independent)
        QShortcut(QKeySequence(Qt.Key_Space), self).activated.connect(self.on_play_toggle)
        QShortcut(QKeySequence(Qt.Key_Left), self).activated.connect(self.v_thread.step_backward)
        QShortcut(QKeySequence(Qt.Key_Right), self).activated.connect(self.v_thread.step_forward)
        QShortcut(QKeySequence(Qt.Key_Z), self).activated.connect(self.on_shortcut_z)
        
        self.v_thread.frame_ready.connect(self.update_frame)
        self.v_thread.angles_ready.connect(self.update_angles)
        self.v_thread.total_frames_ready.connect(self.on_total_frames)
        self.v_thread.current_frame_ready.connect(self.on_current_frame)
        self.v_thread.fps_ready.connect(self.on_fps_ready)
        self.v_thread.frame_size_ready.connect(self.on_frame_size)
        self.v_thread.ankles_dist_ready.connect(self.on_ankles_dist)
        
        self.btn_prev.clicked.connect(self.v_thread.step_backward)
        self.btn_next.clicked.connect(self.v_thread.step_forward)
        self.v_thread.start()

    def on_cam(self):
        self.slider.setEnabled(False)
        self.lbl_time_curr.setText("实时")
        self.lbl_time_max.setText("实时")
        self.v_thread.change_source(0)
        self.btn_play.setText("暂停播放")
        self.btn_play.setStyleSheet("background-color: #d83b01;")
        
    def on_vid(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择本地视频", "", "Video Files (*.mp4 *.avi *.mkv *.mov)")
        if file_path:
            self.v_thread.change_source(file_path)
            self.btn_play.setText("暂停播放")
            self.btn_play.setStyleSheet("background-color: #d83b01;")

    def on_calibrate(self):
        self.video_label.calibrating = True
        self.video_label.setCursor(Qt.CrossCursor)

    def on_play_toggle(self):
        playing = not self.v_thread.playing
        self.v_thread.set_playing(playing)
        if playing:
            self.btn_play.setText("暂停播放")
            self.btn_play.setStyleSheet("background-color: #d83b01;")
        else:
            self.btn_play.setText("恢复播放")
            self.btn_play.setStyleSheet("background-color: #107c10;")
        
    def on_speed_change(self, text):
        speed = float(text.replace('x', ''))
        self.v_thread.set_speed(speed)
        
    def on_mode_change(self, index):
        self.v_thread.set_display_mode(index)
        
    def on_slider_pressed(self):
        self.slider_dragging = True
        
    def on_slider_released(self):
        self.slider_dragging = False
        
        # 只要对进度条发生跳转查阅，均自动挂起暂停视频，以便用户细抠关键帧
        if self.v_thread.playing:
            self.on_play_toggle()
            
        self.v_thread.request_seek(self.slider.value())
        
    def on_slider_moved(self, value):
        if self.slider_dragging:
            # 实时拖拽更新（Live Scrubbing），后台自动丢弃CPU过载的请求
            self.lbl_time_curr.setText(f"{value}")
            self.v_thread.request_seek(value)

    @Slot(int)
    def on_total_frames(self, frames):
        if frames > 0:
            self.slider.setEnabled(True)
            self.slider.setMaximum(frames)
            self.lbl_time_max.setText(str(frames))
        else:
            self.slider.setEnabled(False)

    @Slot(int)
    def on_current_frame(self, frame):
        if not self.slider_dragging and self.slider.isEnabled():
            self.slider.blockSignals(True)
            self.slider.setValue(frame)
            self.slider.blockSignals(False)
            self.lbl_time_curr.setText(str(frame))

    @Slot(QImage)
    def update_frame(self, image: QImage):
        pixmap = QPixmap.fromImage(image)
        scaled_pixmap = pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video_label.setFrameData(scaled_pixmap)
        
    @Slot(dict)
    def update_angles(self, angles: dict):
        for k, v in angles.items():
            # Handle localized partial matching if dict keys have extra text
            for label_key in self.angle_labels.keys():
                if label_key in k:
                    self.angle_labels[label_key].setText(f"{v}°")

    @Slot(int, int)
    def on_frame_size(self, w, h):
        self.video_label.video_w = w

    @Slot(float)
    def on_ankles_dist(self, px):
        self.latest_ankles_px = px

    @Slot(float)
    def on_fps_ready(self, fps):
        self.fps = fps
        self.clear_timing_log()

    def clear_timing_log(self):
        self.timing_log.clear()
        self.last_step_frame = -1
        self.start_step_frame = -1
        self.step_count = 1

    def on_shortcut_z(self):
        frame = self.slider.value()
        time_sec = frame / self.fps
        
        stride_text = ""
        if self.video_label.video_px_per_m > 0 and self.latest_ankles_px > 0:
            stride_m = self.latest_ankles_px / self.video_label.video_px_per_m
            stride_text = f" | 步幅: {stride_m:.2f}m"
        
        if self.last_step_frame >= 0:
            delta_frame = frame - self.last_step_frame
            delta_sec = delta_frame / self.fps
            instant_cadence = 1.0 / delta_sec if delta_sec > 0 else 0.0
            
            # 计算从起点起的平均步频
            total_frames = frame - self.start_step_frame
            total_sec = total_frames / self.fps
            avg_cadence = self.step_count / total_sec if total_sec > 0 else 0.0
            
            cadence_text = f" | 步频: {instant_cadence:.2f} (均值: {avg_cadence:.2f}) Hz"
            log_text = f"第{self.step_count}步: +{delta_sec:.2f}s{cadence_text}{stride_text}"
            
            self.step_count += 1
            self.timing_log.append(log_text)
        else:
            self.step_count = 1
            self.start_step_frame = frame
            self.timing_log.append(f"==== 起点: {time_sec:.2f}s {stride_text} ====")
            
        self.last_step_frame = frame

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def closeEvent(self, event):
        self.v_thread.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
