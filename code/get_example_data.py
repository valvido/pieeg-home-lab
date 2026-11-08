"""
Download PiEEG's published example recordings and convert them to this repo's
CSV + JSON format, so every script (spectrum.py, the missions) works on them.

    python get_example_data.py            # all datasets
    python get_example_data.py artifacts  # just one

Writes to  recordings/example_<name>.csv  and  .json

Recorded by PiEEG with their hardware at 250 Hz, values in microvolts.
Source: https://github.com/pieeg-club/PiEEG-8 (Datasets and 1.GUI/dataset).
The files are downloaded from PiEEG's repository, not stored in this one.
"""

import argparse
import json
import os
import ssl
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

RAW = "https://raw.githubusercontent.com/pieeg-club/PiEEG-8/main/"
FS = 250

DATASETS = {
    "dry": {
        "path": "Datasets/dataset.xlsx",
        "description": "8 channels, dry Ag/AgCl electrodes without gel, positions on the 10-20 system, raw signal",
    },
    "artifacts": {
        "path": "1.GUI/dataset/output.xlsx",
        "description": "Chewing 4, 3, 2, 1 times and blinking 4, 3, 2, 1 times. Good for artifact detection",
    },
    "alpha": {
        "path": "1.GUI/dataset/output3.xlsx",
        "description": "Recording used by PiEEG's own alpha plotting example (1.GUI/dataset/2.Alpha_plot.py)",
    },
}


def ssl_context() -> ssl.SSLContext:
    """Certificates from certifi. Python from python.org on a Mac doesn't use the system
    certificates, and without this the download fails with CERTIFICATE_VERIFY_FAILED.
    SSL_CERT_FILE, if set, wins (for networks with their own certificate)."""
    cafile = os.environ.get("SSL_CERT_FILE")
    if not cafile:
        try:
            import certifi
            cafile = certifi.where()
        except ImportError:
            cafile = None
    return ssl.create_default_context(cafile=cafile)


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60, context=ssl_context()) as r:
        return r.read()


def convert(name: str, out: Path):
    import pandas as pd

    info = DATASETS[name]
    url = RAW + info["path"]
    print(f"Downloading {name} from {url}")
    df = pd.read_excel(BytesIO(fetch(url)))
    df = df.iloc[:, :8]
    df.columns = [f"ch{i}" for i in range(1, df.shape[1] + 1)]
    df.insert(0, "n", range(len(df)))
    df.insert(0, "t", [round(i / FS, 6) for i in range(len(df))])

    out.mkdir(exist_ok=True)
    csv_path = out / f"example_{name}.csv"
    df.to_csv(csv_path, index=False)
    meta = {
        "label": f"example_{name}",
        "description": info["description"],
        "source": url,
        "recorded_by": "PiEEG (example dataset)",
        "sample_rate_hz": FS,
        "n_samples": len(df),
        "n_channels": df.shape[1] - 2,
        "units": "microvolts",
        "time_column": "seconds from start (the original files have no timestamps)",
        "electrodes": "not documented per channel in the source",
        "subject": "PiEEG example subject",
    }
    csv_path.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    print(f"  saved {len(df)} samples ({len(df)/FS:.0f} s) to {csv_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("names", nargs="*", help=f"any of: {', '.join(DATASETS)} (default: all)")
    p.add_argument("--out", default="recordings")
    a = p.parse_args()
    unknown = [n for n in a.names if n not in DATASETS]
    if unknown:
        p.error(f"unknown dataset {unknown}, choose from {list(DATASETS)}")
    failed = []
    for name in a.names or DATASETS:
        try:
            convert(name, Path(a.out))
        except Exception as e:
            print(f"  could not get {name}: {e}", file=sys.stderr)
            failed.append(name)
    if failed:
        sys.exit(f"Failed: {', '.join(failed)}. Check the internet connection, then run it again.")


if __name__ == "__main__":
    main()
