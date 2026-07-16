import builtins
import importlib
import sys

import pytest

from tools.optional_dependencies import OptionalDependencyError, require_opencv


def test_slider_util_imports_without_opencv(monkeypatch):
    real_import = builtins.__import__

    def import_without_opencv(name, *args, **kwargs):
        if name == "cv2":
            raise AssertionError("slider_util imported cv2 eagerly")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_opencv)
    sys.modules.pop("tools.slider_util", None)
    module = importlib.import_module("tools.slider_util")
    assert callable(module.get_tracks)


def test_missing_opencv_error_is_feature_scoped_and_actionable(monkeypatch):
    require_opencv.cache_clear()

    def missing(name):
        assert name == "cv2"
        raise ModuleNotFoundError("No module named cv2")

    monkeypatch.setattr(importlib, "import_module", missing)
    with pytest.raises(OptionalDependencyError, match="uv sync --extra opencv"):
        require_opencv()
    require_opencv.cache_clear()
