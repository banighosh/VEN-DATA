import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trustlayer.models import Message, Terms  # noqa: E402
from trustlayer.world import World  # noqa: E402


def make_message(w: World, sender: str, neg_id: str, kind: str, seq: int, terms=None, text="", ref=None,
                 key_of: str = None, tag: str = "t") -> Message:
    """Build a message signed by `key_of` (defaults to the sender's own key)."""
    unsigned = Message(f"{neg_id}:{seq}:{sender}:{tag}", neg_id, sender, kind, seq, terms, text, ref, "2026-11-04T09:00:00+00:00")
    return Message(**{**unsigned.__dict__, "signature": w.keys[key_of or sender].sign(unsigned.signing_payload())})


def fx_terms(price="30", notional="500000") -> Terms:
    return Terms("fx_forward", "USD/INR", "USD", notional, price, 90)
