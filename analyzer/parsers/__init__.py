"""Parsers for kernel, Proton, and VKD3D-Proton diagnostic logs."""

from .kernel import parse_kernel_log
from .proton import parse_proton_log
from .vkd3d import extract_breadcrumb_report, parse_descriptor_qa_faults, parse_vkd3d_log

__all__ = [
    "extract_breadcrumb_report",
    "parse_kernel_log",
    "parse_descriptor_qa_faults",
    "parse_proton_log",
    "parse_vkd3d_log",
]
