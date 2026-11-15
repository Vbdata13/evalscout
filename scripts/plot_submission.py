"""Render the verified local human-label results recorded in the report."""
from pathlib import Path
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[1] / "benchmark/figures"
NAMES = ["GPT-6 Astra", "GPT-6.1 Sol", "GPT-6.1 Terra"]


def plot(title, values, denominator, filename):
    fig, ax = plt.subplots(figsize=(6.5, 2.4), layout="constrained")
    bars = ax.barh(NAMES, values, color=["#355d86", "#23777b", "#7a668b"])
    ax.invert_yaxis()
    ax.set_xlim(0, denominator + 0.75)
    ax.set_xticks(range(denominator + 1))
    ax.bar_label(bars, labels=[f"{value}/{denominator}" for value in values], padding=5)
    ax.set_title(title, loc="left")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.savefig(OUT / filename, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    plot("Local discovery · verified human-note matches", [3, 2, 2], 8, "discovery.png")
    plot("Local held-out evaluation · exact incident matches", [0, 1, 0], 5, "unseen.png")
