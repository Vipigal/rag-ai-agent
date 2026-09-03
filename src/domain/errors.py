class DomainError(Exception):
    pass


class UnreadableDocument(DomainError):
    def __init__(self, filename: str, reason: str) -> None:
        super().__init__(f"'{filename}' could not be read as a PDF: {reason}")
        self.filename = filename
        self.reason = reason


class ToolRoundsExhausted(DomainError):
    def __init__(self, rounds: int) -> None:
        super().__init__(
            f"the model kept requesting tools after {rounds} round(s) instead of replying"
        )
        self.rounds = rounds
