#!/usr/bin/env python3
import time
import signal
import threading
import logging
from queue import Queue, Empty
from dataclasses import dataclass
import cv2
import requests
from picamera2 import Picamera2

@dataclass
class Config:
    api_key: str
    project: str
    version: str
    resize_dim: tuple[int, int] = (128, 96)
    conf_threshold: float = 0.3
    mask_conf_threshold: float = 0.7
    frame_skip: int = 10
    infer_interval: float = 0.1
    request_timeout: int = 10
    hold_time: float = 3.0
    headless: bool = False  # Certifique-se de que está definido como False para mostrar o vídeo

class MaskAccessSystem:
    MASK_LABELS = {"face-mask"}
    FACE_LABELS = {"face", "balaclava", "mask", "face covering"}

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.picam = None  # Inicializa como None para garantir que stop/close sejam seguros
        self.url = f"https://detect.roboflow.com/{cfg.project}/{cfg.version}?api_key={cfg.api_key}"
        self.predictions: list[dict] = []
        self.last_infer = 0.0
        self.last_state = None
        self.mask_start = None
        self.access_granted = False
        self.running = True
        self.queue = Queue(maxsize=1)
        self.session = requests.Session()
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        self.log = logging.getLogger("MaskAccessSystem")

    def start(self):
        while self.running:
            try:
                self._init_camera()
                self._process_frames()
            except RuntimeError as e:
                print(f"[Erro] Falha ao iniciar a câmera: {e}")
            finally:
                self._cleanup()
            break


    def _init_camera(self):
        from picamera2 import Picamera2
        self.picam = Picamera2()
        size = tuple(dim * 4 for dim in self.cfg.resize_dim)
        cfg_cam = self.picam.create_still_configuration(main={"size": size})
        self.picam.configure(cfg_cam)
        self.picam.start()
        time.sleep(1)

    def _process_frames(self):
        if not self.cfg.headless:
            cv2.namedWindow("Detecção Máscara", cv2.WINDOW_NORMAL)
            print("[INFO] Janela de vídeo aberta")


        thread = threading.Thread(target=self._infer_loop, daemon=True)
        thread.start()

        frame_idx = 0
        while self.running:
            frame = self._capture()
            if frame is None:
                continue
            frame_idx += 1
            if frame_idx % self.cfg.frame_skip == 0:
                self._enqueue(frame)
            self._update_access()

            if not self.cfg.headless:
                self._display(frame)

        thread.join(timeout=1)
        self._cleanup()

    def _capture(self):
        try:
            img = self.picam.capture_array()
            frame = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            return frame
        except Exception:
            return None

    def _enqueue(self, frame):
        now = time.time()
        if self.queue.empty() and (now - self.last_infer) > self.cfg.infer_interval:
            self.queue.put(frame.copy())

    def _infer_loop(self):
        while self.running:
            try:
                frame = self.queue.get(timeout=0.1)
            except Empty:
                continue
            self._infer(frame)

    def _infer(self, frame):
        small = cv2.resize(frame, self.cfg.resize_dim)
        ok, buf = cv2.imencode(".jpg", small)
        if not ok:
            return
        try:
            resp = self.session.post(
                self.url,
                files={"file": ("img.jpg", buf.tobytes(), "image/jpeg")},
                timeout=self.cfg.request_timeout
            )
            resp.raise_for_status()
            data = resp.json().get("predictions", [])
            self._adjust(data, frame.shape[:2])
            self.last_infer = time.time()
        except Exception as e:
            self.log.debug(f"Inferência falhou: {e}")

    def _adjust(self, preds, dims):
        h, w = dims
        sx = w / self.cfg.resize_dim[0]
        sy = h / self.cfg.resize_dim[1]
        adjusted = []
        for p in preds:
            cls = p.get("class", p.get("name", "")).lower()
            try:
                x = p["x"] * sx - p["width"] * sx / 2
                y = p["y"] * sy - p["height"] * sy / 2
                w_box = p["width"] * sx
                h_box = p["height"] * sy
                conf = p["confidence"]
            except KeyError:
                continue
            adjusted.append({
                "x": x, "y": y, "w": w_box, "h": h_box,
                "conf": conf, "class": cls
            })
        self.predictions = adjusted

    def _update_access(self):
        preds = self.predictions
        now = time.time()
        has_mask = any(
            p["class"] in self.MASK_LABELS and p["conf"] >= self.cfg.mask_conf_threshold
            for p in preds
        )
        has_face = any(
            p["class"] in self.FACE_LABELS and p["conf"] >= self.cfg.conf_threshold
            for p in preds
        )
        if has_mask:
            if self.mask_start is None:
                self.mask_start = now
            elif now - self.mask_start >= self.cfg.hold_time:
                self._change_state("liberado", "Acesso liberado")
                self.access_granted = True
        elif has_face:
            self.mask_start = None
            self._change_state("negado", "Acesso negado: necessário máscara")
            self.access_granted = False
        else:
            self.mask_start = None
            self._change_state(None)

    def _change_state(self, new_state, msg=None):
        if new_state != self.last_state:
            if msg:
                self.log.info(msg)
            self.last_state = new_state

    def _display(self, frame):
        for p in self.predictions:
            if p["conf"] < self.cfg.conf_threshold:
                continue
            x1, y1 = int(p["x"]), int(p["y"])
            x2, y2 = int(p["x"] + p["w"]), int(p["y"] + p["h"])
            clr = (0, 255, 0) if p["class"] in self.MASK_LABELS else (0, 0, 255)

            # Desenha o retângulo
            cv2.rectangle(frame, (x1, y1), (x2, y2), clr, 2)

            # Monta texto com classe e porcentagem
            label = f"{p['class']} ({p['conf']*100:.1f}%)"
            cv2.putText(frame, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, clr, 1, cv2.LINE_AA)

        cv2.imshow("Detecção Máscara", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            self.running = False


    def _cleanup(self):
        if not self.cfg.headless:
            try:
                cv2.destroyAllWindows()
                cv2.waitKey(1)  # força liberação da janela do OpenCV
            except Exception as e:
                print(f"[Erro] Falha ao fechar janela OpenCV: {e}")
        try:
            if self.picam:
                self.picam.stop()
                self.picam.close()
                self.picam = None
                print("Camera closed successfully.")
        except Exception as e:
            print(f"[Erro] Falha ao encerrar câmera: {e}")