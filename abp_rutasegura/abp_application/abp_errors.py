from __future__ import annotations


class abpUserFacingError(Exception):
    @property
    def abp_message(self) -> str:
        return str(self)


class abpOperationCancelled(Exception):
    pass
