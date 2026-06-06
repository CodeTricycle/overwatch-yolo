import math
import random


class Humanizer:
    def __init__(
        self,
        max_speed: float = 12.0,
        reaction_dist: float = 80.0,
        alpha: float = 0.55,
        jitter: float = 0.4,
    ):
        self._max_speed = float(max_speed)
        self._reaction_dist = max(1e-3, float(reaction_dist))
        self._alpha = min(1.0, max(0.0, float(alpha)))
        self._jitter = max(0.0, float(jitter))
        self._prev_x = 0.0
        self._prev_y = 0.0

    def set_max_speed(self, v: float) -> None:
        self._max_speed = float(v)

    def set_reaction_dist(self, v: float) -> None:
        self._reaction_dist = max(1e-3, float(v))

    def set_alpha(self, v: float) -> None:
        self._alpha = min(1.0, max(0.0, float(v)))

    def set_jitter(self, v: float) -> None:
        self._jitter = max(0.0, float(v))

    def reset(self) -> None:
        self._prev_x = 0.0
        self._prev_y = 0.0

    def shape(self, mx: float, my: float) -> tuple[float, float]:
        dist = math.hypot(mx, my)
        if dist < 1e-6:
            self._prev_x *= 1.0 - self._alpha
            self._prev_y *= 1.0 - self._alpha
            return self._prev_x, self._prev_y

        speed = self._max_speed * (1.0 - math.exp(-dist / self._reaction_dist))
        target_x = (mx / dist) * speed
        target_y = (my / dist) * speed

        out_x = self._alpha * target_x + (1.0 - self._alpha) * self._prev_x
        out_y = self._alpha * target_y + (1.0 - self._alpha) * self._prev_y

        if self._jitter > 0.0:
            out_x += random.gauss(0.0, self._jitter)
            out_y += random.gauss(0.0, self._jitter)

        self._prev_x = out_x
        self._prev_y = out_y
        return out_x, out_y
