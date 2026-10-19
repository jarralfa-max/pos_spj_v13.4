"""Live scale state. No cart data, database connection or Qt dependency."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock

from backend.domain.device_management.policies.scale_stability_policy import evaluate_stability
from backend.domain.device_management.value_objects.stability_policy import StabilityPolicy
from backend.domain.device_management.value_objects.weight_reading import WeightReading as DeviceReading
from backend.domain.device_management.enums import WeightUnit
from backend.domain.inventory.value_objects.catch_weight import WeightReading


@dataclass(frozen=True)
class LiveScaleState:
    status: str = "DISCONNECTED"
    reading: WeightReading | None = None
    last_valid: WeightReading | None = None
    message: str = "Báscula no conectada"

    @property
    def text(self):
        if self.reading is None:
            return f"Báscula: {self.message}"
        suffix = "estable" if self.status == "STABLE" else "inestable"
        return f"Báscula: {self.reading.net:.3f} {self.reading.unit.lower()} · {suffix}"


class ScaleReadingService:
    def __init__(self, gateway=None, *, policy=None, stale_seconds=Decimal("3")):
        self.gateway = gateway
        self.policy = policy or StabilityPolicy.create()
        self.stale_seconds = stale_seconds
        self._history = []
        self._state = LiveScaleState()
        self._lock = Lock()
        self._generation = 0

    def poll(self):
        with self._lock:
            generation = self._generation
        if self.gateway is None:
            return self.invalidate("DISCONNECTED", "sin configurar")
        try:
            reading = self.gateway.read()
            at = datetime.fromisoformat(reading.captured_at)
            age = Decimal(str((datetime.now(timezone.utc) - at).total_seconds()))
            if age < 0 or age > self.stale_seconds:
                return self.invalidate("STALE", "lectura vencida")
            if not reading.net.is_finite():
                raise ValueError("Non finite weight")
            sample = DeviceReading.create(value=reading.net, unit=WeightUnit(reading.unit.upper()),
                                          stable=reading.stable, at=at)
            with self._lock:
                if generation != self._generation:
                    return self._state
                if self._history and self._history[-1].unit != sample.unit:
                    self._history.clear()
                self._history.append(sample)
                self._history = self._history[-self.policy.required_stable_readings:]
                stable = evaluate_stability(self._history, self.policy) is not None
                self._state = LiveScaleState("STABLE" if stable else "UNSTABLE", reading, reading, "")
                return self._state
        except TimeoutError:
            return self.invalidate("STALE", "sin lectura vigente")
        except Exception:
            return self.invalidate("ERROR", "revisar conexión")

    def invalidate(self, status, message):
        with self._lock:
            self._generation += 1
            self._history.clear()
            self._state = LiveScaleState(status, None, self._state.last_valid, message)
            return self._state

    def current(self):
        with self._lock:
            state = self._state
        if state.reading:
            try:
                at = datetime.fromisoformat(state.reading.captured_at)
                age = Decimal(str((datetime.now(timezone.utc) - at).total_seconds()))
                valid = 0 <= age <= self.stale_seconds and state.reading.net.is_finite()
            except (ValueError, TypeError):
                valid = False
            if not valid:
                return self.invalidate("STALE", "lectura vencida")
        return state

    def accepted_weight(self, *, unit):
        state = self.current()
        if state.status != "STABLE" or state.reading is None or not state.reading.stable:
            raise ValueError("Se necesita una lectura estable y vigente")
        reading = state.reading
        # Device units are explicit. Never treat grams or pounds as kilograms.
        factors = {"KG": Decimal("1"), "G": Decimal("0.001"),
                   "LB": Decimal("0.45359237"), "OZ": Decimal("0.028349523125")}
        target = unit.upper()
        if target not in factors or reading.unit.upper() not in factors:
            raise ValueError("Unidad de peso no compatible")
        return reading.net * factors[reading.unit.upper()] / factors[target]

    @classmethod
    def validate_capture(cls, state, *, quantity, unit, stale_seconds=Decimal("3")):
        verifier = cls(stale_seconds=stale_seconds)
        if not isinstance(state, LiveScaleState):
            raise ValueError("Falta una lectura de báscula validada")
        verifier._state = state
        accepted = verifier.accepted_weight(unit=unit)
        if accepted <= 0 or accepted != quantity:
            raise ValueError("La cantidad no coincide con la lectura vigente")
