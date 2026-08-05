"""Adapter exposing Inventory's canonical post/reverse use cases to Losses."""


class LossesInventoryGateway:
    def __init__(self, connection, post_use_case, reverse_use_case,
                 quarantine_use_case=None, release_quarantine_use_case=None,
                 dispose_quarantine_use_case=None, temperature_use_case=None) -> None:
        self._connection = connection
        self._post = post_use_case
        self._reverse = reverse_use_case
        self._quarantine = quarantine_use_case
        self._release_quarantine = release_quarantine_use_case
        self._dispose_quarantine = dispose_quarantine_use_case
        self._temperature = temperature_use_case

    def post(self, movement, **kwargs):
        return self._post.execute(self._connection, movement, **kwargs)

    def reverse(self, **kwargs):
        return self._reverse.execute(self._connection, **kwargs)

    def quarantine(self, **kwargs):
        return self._quarantine.execute(self._connection, **kwargs)

    def release_quarantine(self, **kwargs):
        return self._release_quarantine.execute(self._connection, **kwargs)

    def dispose_quarantine(self, **kwargs):
        return self._dispose_quarantine.execute(self._connection, **kwargs)

    def record_temperature(self, **kwargs):
        return self._temperature.execute(self._connection, **kwargs)
