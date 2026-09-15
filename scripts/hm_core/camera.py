# -*- coding: utf-8 -*-
"""カメラ取得を別スレッドで回し、検出処理と重ねて遅延を減らす。"""

import threading

import cv2


class CameraStream:
    """常に最新フレームだけを保持するカメラリーダー。"""

    def __init__(self, index=0, width=640, height=480, fps=30):
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError(f"カメラを開けませんでした: index={index}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except cv2.error:
            pass

        self._frame = None
        self._frame_id = 0
        self._failures = 0
        self._stopped = False
        self._cond = threading.Condition()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    @property
    def size(self):
        return (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    def _loop(self):
        while not self._stopped:
            ok, frame = self.cap.read()
            with self._cond:
                if ok:
                    self._frame = frame
                    self._frame_id += 1
                    self._failures = 0
                else:
                    self._failures += 1
                self._cond.notify_all()
            if not ok and self._failures > 30:
                # 取得不能が続く場合はスレッドを終える（本体側で検知する）
                break

    def read(self, last_id=0, timeout=1.0):
        """前回と異なる新しいフレームを返す。(frame_id, frame) または (last_id, None)。"""
        with self._cond:
            if self._frame_id == last_id:
                self._cond.wait(timeout)
            if self._frame_id == last_id or self._frame is None:
                return last_id, None
            return self._frame_id, self._frame

    @property
    def failures(self):
        return self._failures

    def release(self):
        self._stopped = True
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.cap.release()
