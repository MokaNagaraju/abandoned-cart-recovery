"""
Reproducibility test: run the generator twice with the same seed
and assert that checksums match.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generator import AbandonedCartGenerator


def test_same_seed_same_checksums():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out1 = tmp / "run1"
        out2 = tmp / "run2"

        g1 = AbandonedCartGenerator(scale=0.01, seed=20261022)
        m1 = g1.run(out1)

        g2 = AbandonedCartGenerator(scale=0.01, seed=20261022)
        m2 = g2.run(out2)

        for name in m1["files"]:
            assert m1["files"][name]["checksum_sha256_16"] == m2["files"][name]["checksum_sha256_16"], \
                f"Checksum mismatch for {name}"
            assert m1["files"][name]["rows"] == m2["files"][name]["rows"]

        print("Reproducibility test PASSED")


if __name__ == "__main__":
    test_same_seed_same_checksums()
