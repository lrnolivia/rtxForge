"""The counter and bar position of a per-game step (Windows StepCount, 1.0 Beta 2).

The engine reports uncounted sub-steps (verifying a package, loading a model)
between counted ones; those keep the last count instead of flipping the bar
back to indeterminate or its position back to the start. A new verb starts
afresh.
"""


class StepCount:
    def __init__(self):
        self.verb = None
        self.last = None

    def next(self, verb, index, total, fraction=None):
        """(at, of, value) to show, or None while nothing has been counted yet."""
        if verb != self.verb:
            self.verb, self.last = verb, None
        if total and total > 0:
            value = max(0.0, min(1.0, fraction if fraction is not None else index / total))
            # The bar never moves backwards within one step.
            if self.last is not None and self.last[1] == total and value < self.last[2]:
                return self.last
            self.last = (min(index + 1, total), total, value)
        return self.last

    def reset(self):
        self.verb = self.last = None
