"""Input helper functions shared by Streamlit and scripts."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd


def read_uploaded_dataframe(uploaded_file) -> pd.DataFrame:
    """Read a Streamlit uploaded CSV or Parquet file.

    Parameters
    ----------
    uploaded_file:
        Streamlit UploadedFile object.

    Returns
    -------
    pandas.DataFrame
        Uploaded dataframe.
    """

    suffix = Path(uploaded_file.name).suffix.lower()
    data = uploaded_file.read()
    if suffix == ".parquet":
        return pd.read_parquet(io.BytesIO(data))
    return pd.read_csv(io.BytesIO(data))
