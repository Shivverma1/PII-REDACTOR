"""Detector package: importing it registers every built-in detector."""

from . import address, names, structured
from .base import Detector, all_detectors, register

structured.register_all()
address.register_all()
names.register_all()

__all__ = ["Detector", "all_detectors", "register"]
