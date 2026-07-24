# -*- coding: utf-8 -*-
"""Search result types for the Guanlan web subsystem.

The dataclass identities remain in the compatibility runtime for this release.
This is the sole split-owner exception allowed to import those types directly;
new business logic must use this module rather than importing legacy runtime.
"""

from guanlan.web._legacy_web_impl import NetworkBackendError, SearchResult, SearchResults

__all__ = ["NetworkBackendError", "SearchResult", "SearchResults"]
