from dataclasses import dataclass


@dataclass(frozen=True)
class AncestryPerson:
    person_id: str
    full_name: str
    generation: str = ""
    sex: str = ""
    birth_date: str = ""
    birth_place: str = ""
    death_date: str = ""
    death_place: str = ""
    source_count: int = 0
    source_titles: str = ""

    @property
    def gedcom_id(self) -> str:
        return self.person_id

    @property
    def given_name(self) -> str:
        parts = self.full_name.split()
        return " ".join(parts[:-1]) if len(parts) > 1 else self.full_name

    @property
    def surname(self) -> str:
        parts = self.full_name.split()
        return parts[-1] if parts else ""

