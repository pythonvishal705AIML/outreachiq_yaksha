from abc import ABC, abstractmethod


class ProviderContract(ABC):
    source_name = "base"

    @abstractmethod
    def search_people(self, params: dict, session_id: str | None = None, account_id: str | None = None) -> dict:
        raise NotImplementedError
