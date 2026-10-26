"""Public, path-free failures shared by API and job supervision."""


class Problem(Exception):
    def __init__(self, status: int, code: str, message: str, **details):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


class ConversionError(Exception):
    pass
