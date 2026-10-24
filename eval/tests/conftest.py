"""Eval tests run offline: they import the eval scripts directly, nothing reaches Google."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
