"""Decision gate separating a model score from publication permission."""
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Decision:
    """The auditable outcome of a prediction publication decision."""
    publish: bool
    reason: str

def decide(confidence: float, threshold: float, lineup_verified: bool, minutes_to_kickoff: float) -> Decision:
    """Approve only a timely, sufficiently supported locked forecast."""
    if not 0 <= minutes_to_kickoff <= 15:
        return Decision(False, "Tahmin kilit penceresi dışında.")
    if confidence < threshold:
        return Decision(False, "Veri ve model güveni yayın eşiğinin altında.")
    if not lineup_verified and minutes_to_kickoff > 0:
        return Decision(True, "İlk 11 doğrulanmadan, güven cezasıyla yayınlandı.")
    return Decision(True, "Tahmin yayın eşiğini karşıladı.")
