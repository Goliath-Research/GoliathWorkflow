"""Action execution primitives for workflow workers."""

from .base import CliAction, InProcessAction, build_action_from_catalog
from .detector import DETECTOR_ARGV_MAP, DetectorCliAction, merge_detector_step_override
from .dmp_select import DMP_SELECT_ARGV_MAP, DmpSelectCliAction
from .gene_select import GENE_SELECT_ARGV_MAP, GeneSelectCliAction

__all__ = [
    "CliAction",
    "DetectorCliAction",
    "DmpSelectCliAction",
    "GeneSelectCliAction",
    "DETECTOR_ARGV_MAP",
    "DMP_SELECT_ARGV_MAP",
    "GENE_SELECT_ARGV_MAP",
    "InProcessAction",
    "build_action_from_catalog",
    "merge_detector_step_override",
]
