# -*- coding: utf-8 -*-
"""HTML and page-read helper ownership marker for the read subsystem."""

from guanlan.web import _impl as _compat

_call_read_direct = _compat._call_read_direct
_read_direct = _compat._read_direct
_read_wechat_article = _compat._read_wechat_article
_read_with_jina = _compat._read_with_jina

__all__ = ["_call_read_direct", "_read_direct", "_read_wechat_article", "_read_with_jina"]
