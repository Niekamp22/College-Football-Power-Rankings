import unittest

import numpy as np

from margin_challenger import fit_huber_ridge, predict


class MarginChallengerTest(unittest.TestCase):
    def test_huber_ridge_learns_a_stable_residual_signal(self) -> None:
        x = np.arange(20, dtype=float).reshape(-1, 1)
        target = 1.5 + (2.0 * x[:, 0])

        model = fit_huber_ridge(x, target, alpha=0.01)
        predictions = predict(x, model)

        self.assertLess(float(np.mean(np.abs(predictions - target))), 0.01)


if __name__ == "__main__":
    unittest.main()
