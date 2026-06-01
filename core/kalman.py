import numpy as np


class KalmanTracker:
    _STATE_SIZE = 4

    def __init__(self, process_noise: float = 5.0, measurement_noise: float = 2.0, dt: float = 1.0):
        self._initialized = False
        self._coast_frames = 0
        self._dt = dt

        self._x = np.zeros((self._STATE_SIZE, 1), dtype=np.float64)
        self._P = np.eye(self._STATE_SIZE, dtype=np.float64) * 500.0

        self._F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=np.float64)

        self._H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=np.float64)

        q = process_noise ** 2
        self._Q = q * np.array([
            [dt ** 4 / 4, 0, dt ** 3 / 2, 0],
            [0, dt ** 4 / 4, 0, dt ** 3 / 2],
            [dt ** 3 / 2, 0, dt ** 2, 0],
            [0, dt ** 3 / 2, 0, dt ** 2],
        ], dtype=np.float64)

        r = measurement_noise ** 2
        self._R = np.array([[r, 0], [0, r]], dtype=np.float64)

        self._I = np.eye(self._STATE_SIZE, dtype=np.float64)

    def init_state(self, cx: float, cy: float) -> None:
        self._x[:] = 0.0
        self._x[0, 0] = cx
        self._x[1, 0] = cy
        self._P = np.eye(self._STATE_SIZE, dtype=np.float64) * 500.0
        self._initialized = True
        self._coast_frames = 0

    def predict(self) -> np.ndarray:
        self._x = self._F @ self._x
        self._P = self._F @ self._P @ self._F.T + self._Q
        self._coast_frames += 1
        return self._x[:2, 0].copy()

    def update(self, cx: float, cy: float) -> np.ndarray:
        x_pred = self._F @ self._x
        P_pred = self._F @ self._P @ self._F.T + self._Q

        z = np.array([[cx], [cy]], dtype=np.float64)
        y_innov = z - self._H @ x_pred
        S = self._H @ P_pred @ self._H.T + self._R
        K = P_pred @ self._H.T @ np.linalg.inv(S)

        self._x = x_pred + K @ y_innov
        I_KH = self._I - K @ self._H
        self._P = I_KH @ P_pred @ I_KH.T + K @ self._R @ K.T

        self._coast_frames = 0
        return self._x[:2, 0].copy()

    def is_initialized(self) -> bool:
        return self._initialized

    def reset(self) -> None:
        self._initialized = False
        self._coast_frames = 0
        self._x[:] = 0.0
        self._P = np.eye(self._STATE_SIZE, dtype=np.float64) * 500.0

    @property
    def coast_frames(self) -> int:
        return self._coast_frames
