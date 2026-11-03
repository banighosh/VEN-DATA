from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..analytics.common import DatasetFrame, get_frame
from ..db import get_db
from ..models import Dataset


def get_dataset(dataset_id: int, db: Session = Depends(get_db)) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found.")
    return ds


def get_ready_dataset(ds: Dataset = Depends(get_dataset)) -> Dataset:
    if ds.status != "ready":
        raise HTTPException(409, f"Dataset is not ready (status: {ds.status}).")
    return ds


def dataset_frame(ds: Dataset = Depends(get_ready_dataset), db: Session = Depends(get_db)) -> DatasetFrame:
    return get_frame(db, ds)
