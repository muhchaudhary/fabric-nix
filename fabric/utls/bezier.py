kMaxNewtonIterations = 4
kBezierEpsilon = 1e-7
CUBIC_BEZIER_SPLINE_SAMPLES = 11

# https://github.com/WebKit/WebKit/blob/main/Source/WebCore/platform/graphics/UnitBezier.h
# https://chromium.googlesource.com/chromium/src/+/master/ui/gfx/geometry/cubic_bezier.cc

class CubicBezier:
    def __init__(self, p1x: float, p1y: float, p2x: float, p2y: float):
        self._cx = 3.0 * p1x
        self._bx = 3.0 * (p2x - p1x) - self._cx
        self._ax = 1.0 - self._cx - self._bx

        self._cy = 3.0 * p1y
        self._by = 3.0 * (p2y - p1y) - self._cy
        self._ay = 1.0 - self._cy - self._by

        if p1x > 0:
            self._startGradient = p1y / p1x
        elif not p1y and p2x > 0:
            self._startGradient = p2y / p2x
        elif not p1y and not p2y:
            self._startGradient = 1
        else:
            self._startGradient = 0

        if p2x < 1:
            self._endGradient = (p2y - 1) / (p2x - 1)
        elif p2y == 1 and p1x < 1:
            self._endGradient = (p1y - 1) / (p1x - 1)
        elif p2y == 1 and p1y == 1:
            self._endGradient = 1
        else:
            self._endGradient = 0

        deltaT = 1.0 / (CUBIC_BEZIER_SPLINE_SAMPLES - 1)
        self._splineSamples = [0] * CUBIC_BEZIER_SPLINE_SAMPLES
        for i in range(CUBIC_BEZIER_SPLINE_SAMPLES):
            self._splineSamples[i] = self.sampleCurveX(i * deltaT)

    def sampleCurveX(self, t: float):
        return ((self._ax * t + self._bx) * t + self._cx) * t

    def sampleCurveY(self, t: float):
        return ((self._ay * t + self._by) * t + self._cy) * t

    def sampleCurveDerivativeX(self, t: float):
        return (3.0 * self._ax * t + 2.0 * self._bx) * t + self._cx

    def solveCurveX(self, x: float, epsilon: float):
        t0: float = 0.0
        t1: float = 0.0
        t2: float = x
        x2: float = 0.0
        d2: float = 0.0

        deltaT = 1.0 / (CUBIC_BEZIER_SPLINE_SAMPLES - 1)
        for i in range(1, CUBIC_BEZIER_SPLINE_SAMPLES):
            if x < self._splineSamples[i]:
                t1 = deltaT * i
                t0 = t1 - deltaT
                t2 = t0 + (t1 - t0) * (x - self._splineSamples[i - 1]) / (
                    self._splineSamples[i] - self._splineSamples[i - 1]
                )
                break

        # newtons method
        newtonEpsilon = min(kBezierEpsilon, epsilon)
        for i in range(kMaxNewtonIterations):
            x2 = self.sampleCurveX(t2) - x
            if abs(x2) < newtonEpsilon:
                return t2
            d2 = self.sampleCurveDerivativeX(t2)
            if abs(d2) < kBezierEpsilon:
                break
            t2 = t2 - x2 / d2

        if abs(x2) < epsilon:
            return t2
        # bisection method
        while t0 < t1:
            x2 = self.sampleCurveX(t2)
            if abs(x2 - x) < epsilon:
                return t2
            if x > x2:
                t0 = t2
            else:
                t1 = t2
            t2 = (t1 + t0) * 0.5

        # failure
        return t2

    def solve(self, x: float, epsilon: float = kBezierEpsilon):
        if x < 0:
            return 0 + self._startGradient * x
        if x > 1:
            return 1.0 + self._endGradient * (x - 1.0)
        return self.sampleCurveY(self.solveCurveX(x, epsilon))
