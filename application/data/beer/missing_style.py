from dataclasses import dataclass


@dataclass
class MissingStyle:
    style_name: str
    is_main_missing: bool
    is_rowdy_missing: bool
