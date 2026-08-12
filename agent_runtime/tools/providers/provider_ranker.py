class ProviderRanker:
    def dedupe_people(self, rows: list[dict]) -> list[dict]:
        seen = set()
        output = []
        for row in rows or []:
            key = row.get("id") or row.get("email") or row.get("linkedin_url")
            if not key:
                output.append(row)
                continue
            if key in seen:
                continue
            seen.add(key)
            output.append(row)
        return output
