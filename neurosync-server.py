import threading
import queue
import cv2
import numpy as np
import time
from time import sleep
from streamlink import Streamlink
import socket

STREAM = "vedal987"
QUALITY = "best"
X_START = 1790
X_END = 1830
Y_START = 820
Y_END = 880
UPDATE_INTERVAL = 0.5
DOWNSAMPLE_MAX = 100
VERBOSE = True

ESP32_IP = "192.168.4.1"
ESP32_PORT = 8765
TCP_RETRY_INTERVAL = 5
print("server active")

def connect_tcp():
    while True:
        try:
            s = socket.socket()
            s.connect((ESP32_IP, ESP32_PORT))
            s_file = s.makefile("w")
            print("lamp connected")
            return s, s_file
        except Exception as e:
            sleep(TCP_RETRY_INTERVAL)

s, s_file = connect_tcp()

class NeuroLamp:
    def __init__(self):
        self.twitch_username = STREAM
        self.quality = QUALITY
        self.x_start = X_START
        self.x_end = X_END
        self.y_start = Y_START
        self.y_end = Y_END
        self.update_interval = UPDATE_INTERVAL
        self.downsample_max = DOWNSAMPLE_MAX
        self.verbose = VERBOSE
        self.last_color = np.array([0, 0, 0])
        self.frame_q = queue.Queue(maxsize=1)
        self._reader_thread = None
        self._running = False
        self.cap = None
        self.stream_url = self.get_twitch_stream_url()

    def get_twitch_stream_url(self):
        session = Streamlink()
        url = f"https://www.twitch.tv/videos/2664545415"
        try:
            streams = session.streams(url)
            if not streams:
                if self.verbose:
                    print("vedal987 is not live or internet is disconnected")
                return None
            stream_obj = streams.get(self.quality) or streams.get("best")
            if stream_obj is None:
                if self.verbose:
                    print("quality error")
                return None
            if hasattr(stream_obj, "to_url"):
                return stream_obj.to_url()
            else:
                return getattr(stream_obj, "url", None)
        except Exception as e:
            if self.verbose:
                print("cant get stream url", e)
            return None

    def _reader(self):
        while self._running and self.cap is not None:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                sleep(0.01)
                continue
            try:
                self.frame_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self.frame_q.put_nowait(frame)
            except queue.Full:
                pass

    def _clamp_roi(self, frame):
        h, w = frame.shape[:2]
        x0 = max(0, min(w, int(self.x_start)))
        x1 = max(0, min(w, int(self.x_end)))
        y0 = max(0, min(h, int(self.y_start)))
        y1 = max(0, min(h, int(self.y_end)))
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        return x0, x1, y0, y1

    def get_important_pixels(self, frame):
        x0, x1, y0, y1 = self._clamp_roi(frame)
        roi = frame[y0:y1, x0:x1]
        cv2.imwrite("lamp.png", roi)

        if roi.size == 0:
            h, w = frame.shape[:2]
            cx, cy = w // 2, h // 2
            roi = frame[max(0, cy-10):min(h, cy+10), max(0, cx-10):min(w, cx+10)]
        h, w = roi.shape[:2]
        max_dim = max(h, w)
        if max_dim > self.downsample_max:
            scale = self.downsample_max / float(max_dim)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            roi_proc = cv2.resize(roi, (new_w, new_h), interpolation=cv2.INTER_AREA)
        else:
            roi_proc = roi
        roi_reshaped = roi_proc.reshape(-1, 3)
        quant_div = 5
        rounded_colors = (np.round(roi_reshaped / quant_div) * quant_div).astype(np.int32)
        try:
            data = np.ascontiguousarray(rounded_colors)
            dtype = np.dtype((np.void, data.dtype.itemsize * data.shape[1]))
            b = data.view(dtype)
            unique_b, indices, counts = np.unique(b, return_index=True, return_counts=True)
            unique_colors = data[indices]
        except Exception:
            unique_colors, counts = np.unique(rounded_colors, axis=0, return_counts=True)
        most_idx = np.argmax(counts)
        most_occurring_color_bgr = unique_colors[most_idx]
        return [int(v) for v in most_occurring_color_bgr[::-1]], (np.linalg.norm([int(v) for v in most_occurring_color_bgr[::-1]]) / np.linalg.norm([255, 255, 255])) * 100
        

    def update_lamp(self, brightness, rgb):
        if brightness < 0:
            brightness = 0
        if brightness > 100:
            brightness = 100
        if any([c < 0 or c > 255 for c in rgb]):
            grey = int(max(0, min(255, (brightness / 100.0) * 255)))
            rgb = [grey, grey, grey]

        print(f"{rgb}", end="\r")
        self.last_color = np.array(rgb, dtype=int)

        global s, s_file
        if s:
            try:
                s_file.write(f"{rgb[0]},{rgb[1]},{rgb[2]}\n")
                s_file.flush()
            except Exception as e:
                print("lamp send failed, retrying", e)
                s.close()
                s, s_file = connect_tcp()

    def run(self):
        if not self.stream_url:
            if self.verbose:
                print("no stream url")
            return
        backend = cv2.CAP_FFMPEG if hasattr(cv2, "CAP_FFMPEG") else 0
        self.cap = cv2.VideoCapture(self.stream_url, backend)
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        if not self.cap.isOpened():
            if self.verbose:
                print("cant open capture")
            return
        self._running = True
        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()
        try:
            while self._running:
                try:
                    frame = self.frame_q.get(timeout=1.0)
                except queue.Empty:
                    continue
                color, brightness = self.get_important_pixels(frame)
                try:
                    brightness = float(brightness)
                except Exception:
                    brightness = 0.0
                if not isinstance(color, (list, tuple, np.ndarray)):
                    color = list(self.last_color)
                self.update_lamp(brightness, color)
                if self.update_interval:
                    sleep(self.update_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            if self._reader_thread:
                self._reader_thread.join(timeout=1.0)
            if self.cap:
                self.cap.release()

if __name__ == "__main__":
    lamp = NeuroLamp()
    lamp.run()
