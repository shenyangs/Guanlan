# -*- coding: utf-8 -*-
"""Tests for Guanlan core class."""

import pytest

from guanlan.config import Config
from guanlan.core import Guanlan


@pytest.fixture
def eyes(tmp_path):
    config = Config(config_path=tmp_path / "config.yaml")
    return Guanlan(config=config)


class TestGuanlan:
    def test_init(self, eyes):
        assert eyes.config is not None

    def test_doctor(self, eyes):
        results = eyes.doctor()
        assert isinstance(results, dict)
        assert "web" in results
        assert "github" in results

    def test_doctor_report(self, eyes):
        report = eyes.doctor_report()
        assert isinstance(report, str)
        assert "观澜 / Guanlan" in report
