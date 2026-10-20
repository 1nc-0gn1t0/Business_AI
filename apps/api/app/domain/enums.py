from enum import StrEnum


class DataOrigin(StrEnum):
    OPEN_DATA = "open_data"
    LICENSED = "licensed"
    MODELLED = "modelled"
    SYNTHETIC = "synthetic"
    USER_INPUT = "user_input"
    BANK_INTERNAL = "bank_internal"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    NOT_APPLICABLE = "not_applicable"


class Funding(StrEnum):
    OWN_FUNDS = "own_funds"
    LOAN = "loan"
    MIXED = "mixed"
    UNDECIDED = "undecided"


class ConfirmationState(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
