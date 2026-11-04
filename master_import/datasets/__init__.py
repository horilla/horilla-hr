"""The datasets that can be imported. Add one here to put it on the page."""

from .asset_allocation import AssetAllocationDataset
from .assets import AssetsDataset
from .assigned_leave import AssignedLeaveDataset
from .candidates import CandidatesDataset
from .employees import EmployeesDataset

DATASETS = {
    "employees": EmployeesDataset(),
    "candidates": CandidatesDataset(),
    "assigned_leave": AssignedLeaveDataset(),
    "assets": AssetsDataset(),
    "asset_allocation": AssetAllocationDataset(),
}


def get_dataset(key):
    return DATASETS.get(key)


def default_dataset():
    return next(d for d in DATASETS.values() if d.available)
