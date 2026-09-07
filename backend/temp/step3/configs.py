"""Step 3 controls: entry/exit candidates and explicit stop switches."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
from app.features.signals.params import SignalParams


class ResearchParams(SignalParams):
    initial_enabled: bool = True
    channel_enabled: bool = True
    trailing_enabled: bool = True


ARCHITECTURES = {
    "channel": "Channel only",
    "channel_initial": "Channel + initial stop",
    "initial_trailing": "Initial + Chandelier",
    "all": "Channel + initial + Chandelier",
}
ENTRIES = [10, 20, 55, 200]
EXITS = [10, 20, 55]


def configurations():
    configs = []
    for architecture, label in ARCHITECTURES.items():
        for entry in ENTRIES:
            for exit_len in EXITS if architecture != "initial_trailing" else [20]:
                for initial in [2.0, 3.0] if architecture != "channel" else [2.0]:
                    for trailing in [3.0, 4.0] if architecture in ("all", "initial_trailing") else [3.0]:
                        p = ResearchParams(entry_len=entry, exit_len=exit_len,
                            atr_stop_mult=initial, chandelier_k=trailing,
                            initial_enabled=architecture != "channel",
                            channel_enabled=architecture != "initial_trailing",
                            trailing_enabled=architecture in ("all", "initial_trailing"))
                        key = f"{architecture}-e{entry}-x{exit_len}-i{initial:g}-t{trailing:g}"
                        configs.append({"id": key, "architecture": architecture, "label": label,
                            "entry": entry, "exit": exit_len if p.channel_enabled else None,
                            "initial": initial if p.initial_enabled else None,
                            "trailing": trailing if p.trailing_enabled else None, "params": p.model_dump()})
    assert len(configs) == 100
    return configs
