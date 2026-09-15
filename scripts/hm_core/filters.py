# -*- coding: utf-8 -*-
"""カーソル座標のブレを抑えるフィルタ。"""

import math


class OneEuroFilter:
    """One Euro Filter。

    低速時は強く平滑化して手ブレを消し、素早く動かしたときは
    追従性を優先する（遅延を感じさせない）適応型ローパスフィルタ。
    """

    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        """カットオフ周波数とサンプリング間隔から平滑化係数を求める。"""
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self):
        """内部状態を初期化する（トラッキングが途切れたとき用）。"""
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    def __call__(self, x, t):
        """時刻t[秒]の観測値xを平滑化して返す。"""
        if self._x_prev is None:
            self._x_prev = x
            self._t_prev = t
            return x

        dt = t - self._t_prev
        if dt <= 0.0:
            dt = 1e-3
        self._t_prev = t

        # 速度成分を推定して、速い動きではカットオフを上げる
        dx = (x - self._x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        return x_hat


class Point2DFilter:
    """2次元座標用のOne Euro Filterラッパー。"""

    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self._fx = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self._fy = OneEuroFilter(min_cutoff, beta, d_cutoff)

    def reset(self):
        self._fx.reset()
        self._fy.reset()

    def __call__(self, x, y, t):
        return self._fx(x, t), self._fy(y, t)
