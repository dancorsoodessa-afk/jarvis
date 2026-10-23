"""Basic webcam face-detection tool for JARVIS (snapshot analysis, not identity recognition)."""
from __future__ import annotations

import os


def face_check() -> str:
    """Capture a short webcam sample and report whether a face is visible."""
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError("Модуль обнаружения лица не установлен (opencv-python-headless).") from exc

    raw_device = os.environ.get("JARVIS_CAMERA_DEVICE", "0").strip()
    try:
        device = int(raw_device)
    except ValueError:
        device = raw_device

    camera = cv2.VideoCapture(device, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY)
    if not camera.isOpened():
        camera.release()
        raise RuntimeError(
            "Не удалось открыть веб-камеру. Проверьте разрешение камеры в Windows, "
            "закройте другие приложения, использующие камеру, или задайте JARVIS_CAMERA_DEVICE."
        )
    try:
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        ok, frame = False, None
        for _ in range(8):
            ok, frame = camera.read()
            if ok and frame is not None:
                break
        if not ok or frame is None:
            raise RuntimeError("Веб-камера открылась, но не вернула изображение.")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        detector = cv2.CascadeClassifier(cascade_path)
        if detector.empty():
            raise RuntimeError("Не удалось загрузить каскад распознавания лица.")
        faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        if len(faces):
            return f"Камера работает. Обнаружено лиц в кадре: {len(faces)}. Это обнаружение лица, не установление личности."
        return "Камера работает, кадр получен, но лицо не обнаружено. Посмотрите прямо в камеру, улучшите освещение и повторите."
    finally:
        camera.release()
