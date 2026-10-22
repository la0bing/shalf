import numpy as np
import pandas as pd

from shalf.monitoring import PSIDriftDetector


def test_psi_detects_shift():
    rng = np.random.default_rng(0)
    ref = pd.Series(rng.normal(0, 1, 5000))
    detector = PSIDriftDetector()
    assert detector.score(ref, pd.Series(rng.normal(0, 1, 5000))) < 0.05
    assert detector.score(ref, pd.Series(rng.normal(1.5, 1, 5000))) > 0.5
