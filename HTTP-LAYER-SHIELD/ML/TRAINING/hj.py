"""
Dataset Generator for Bot Detection (IsolationForest)
------------------------------------------------------
Creates 4750 fake user sessions: 3750 human + 1000 bot
Saves all output files in the same folder as this script.

Run:
    python generate_dataset.py
"""

import numpy as np
import pandas as pd
import os

np.random.seed(42)

# This makes sure output files are saved next to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# These are the 8 behaviors we track for each session
FEATURES = [
    'click_count',            # how many times user clicked
    'avg_click_interval',     # average time (ms) between clicks
    'click_interval_variance',# how much the click timing varies
    'click_interval_entropy', # randomness in click timing
    'mouse_velocity_variance',# how smoothly the mouse moves
    'max_element_click_rate', # fastest clicks on a single element
    'scroll_events',          # how many times user scrolled
    'keystroke_count',        # how many keys were pressed
]


# ──────────────────────────────────────────
# HUMAN PERSONAS (3 types, 1250 each = 3750)
# ──────────────────────────────────────────

def gen_casual_browser(n):
    # Relaxed user — reads pages, scrolls, clicks occasionally
    return pd.DataFrame({
        'click_count':             np.random.poisson(5, n),
        'avg_click_interval':      np.random.normal(1200, 300, n),
        'click_interval_variance': np.random.normal(200000, 70000, n),
        'click_interval_entropy':  np.random.normal(3.0, 0.4, n),
        'mouse_velocity_variance': np.random.normal(0.55, 0.18, n),
        'max_element_click_rate':  np.random.uniform(0.1, 1.5, n),
        'scroll_events':           np.random.poisson(10, n),
        'keystroke_count':         np.random.poisson(8, n),
        'persona': 'casual_browser',
        'label':   'human',
    })

def gen_power_user(n):
    # Fast, focused user — clicks quickly but still acts naturally
    return pd.DataFrame({
        'click_count':             np.random.poisson(18, n),
        'avg_click_interval':      np.random.normal(500, 150, n),
        'click_interval_variance': np.random.normal(120000, 40000, n),
        'click_interval_entropy':  np.random.normal(2.6, 0.4, n),
        'mouse_velocity_variance': np.random.normal(0.85, 0.25, n),
        'max_element_click_rate':  np.random.uniform(1.0, 4.0, n),
        'scroll_events':           np.random.poisson(4, n),
        'keystroke_count':         np.random.poisson(45, n),
        'persona': 'power_user',
        'label':   'human',
    })

def gen_mobile_user(n):
    # Mobile user — taps instead of clicks, no real mouse movement
    return pd.DataFrame({
        'click_count':             np.random.poisson(7, n),
        'avg_click_interval':      np.random.normal(1000, 350, n),
        'click_interval_variance': np.random.normal(160000, 55000, n),
        'click_interval_entropy':  np.random.normal(2.4, 0.5, n),
        'mouse_velocity_variance': np.random.normal(0.05, 0.03, n),  # very low — touch screen
        'max_element_click_rate':  np.random.uniform(0.1, 2.0, n),
        'scroll_events':           np.random.poisson(3, n),
        'keystroke_count':         np.random.poisson(12, n),
        'persona': 'mobile_user',
        'label':   'human',
    })


# ──────────────────────────────────────────
# BOT TYPES (4 types, 250 each = 1000)
# ──────────────────────────────────────────

def gen_http_flooder(n):
    # Sends hundreds of requests with no mouse or keyboard activity
    return pd.DataFrame({
        'click_count':             np.random.randint(100, 300, n),
        'avg_click_interval':      np.random.normal(30, 3, n),
        'click_interval_variance': np.random.normal(8, 2, n),
        'click_interval_entropy':  np.random.normal(0.02, 0.01, n),
        'mouse_velocity_variance': np.zeros(n),       # no mouse
        'max_element_click_rate':  np.random.uniform(20, 60, n),
        'scroll_events':           np.zeros(n),        # no scrolling
        'keystroke_count':         np.zeros(n),        # no typing
        'persona': 'http_flooder',
        'label':   'bot',
    })

def gen_slow_bot(n):
    # Pretends to be human by copying average timing — but clicks like a clock (no variation)
    return pd.DataFrame({
        'click_count':             np.random.poisson(8, n),
        'avg_click_interval':      np.random.normal(950, 15, n),    # looks human
        'click_interval_variance': np.random.normal(150, 10, n),    # but way too consistent
        'click_interval_entropy':  np.random.normal(0.12, 0.04, n),
        'mouse_velocity_variance': np.zeros(n),
        'max_element_click_rate':  np.random.uniform(0.8, 1.3, n),
        'scroll_events':           np.zeros(n),
        'keystroke_count':         np.zeros(n),
        'persona': 'slow_bot',
        'label':   'bot',
    })

def gen_headless_browser(n):
    # Uses a real browser (like Puppeteer) but moves mouse in perfectly straight lines
    return pd.DataFrame({
        'click_count':             np.random.poisson(11, n),
        'avg_click_interval':      np.random.normal(280, 12, n),
        'click_interval_variance': np.random.normal(420, 30, n),
        'click_interval_entropy':  np.random.normal(0.65, 0.08, n),
        'mouse_velocity_variance': np.random.normal(0.008, 0.002, n),  # too smooth to be human
        'max_element_click_rate':  np.random.uniform(2.5, 6.0, n),
        'scroll_events':           np.random.poisson(1, n),
        'keystroke_count':         np.zeros(n),
        'persona': 'headless_browser',
        'label':   'bot',
    })

def gen_credential_stuffer(n):
    # Tries to log in automatically — pastes credentials instantly, no natural typing
    return pd.DataFrame({
        'click_count':             np.random.poisson(4, n),
        'avg_click_interval':      np.random.normal(1100, 8, n),
        'click_interval_variance': np.random.normal(40, 5, n),
        'click_interval_entropy':  np.random.normal(0.08, 0.03, n),
        'mouse_velocity_variance': np.random.normal(0.015, 0.004, n),
        'max_element_click_rate':  np.random.uniform(0.4, 1.0, n),
        'scroll_events':           np.zeros(n),
        'keystroke_count':         np.random.normal(38, 1.5, n),  # always the same count
        'persona': 'credential_stuffer',
        'label':   'bot',
    })


# ──────────────────────────────────────────
# BUILD & SAVE
# ──────────────────────────────────────────

def build_dataset():
    humans = pd.concat([
        gen_casual_browser(1250),
        gen_power_user(1250),
        gen_mobile_user(1250),
    ], ignore_index=True)

    bots = pd.concat([
        gen_http_flooder(250),
        gen_slow_bot(250),
        gen_headless_browser(250),
        gen_credential_stuffer(250),
    ], ignore_index=True)

    df = pd.concat([humans, bots], ignore_index=True)
    df[FEATURES] = df[FEATURES].clip(lower=0)           # no negative values
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)  # shuffle
    return df


def print_summary(df):
    lines = ["=" * 60, "DATASET SUMMARY", "=" * 60]
    lines.append(f"Total sessions   : {len(df)}")
    lines.append(f"Human sessions   : {(df['label'] == 'human').sum()}")
    lines.append(f"Bot sessions     : {(df['label'] == 'bot').sum()}")
    lines.append("\nBreakdown by persona:")
    for persona, count in df['persona'].value_counts().items():
        lines.append(f"  {persona:<25} {count}")
    lines.append("\nFeature statistics (human vs bot):")
    lines.append("-" * 60)
    for feat in FEATURES:
        h = df[df['label'] == 'human'][feat]
        b = df[df['label'] == 'bot'][feat]
        lines.append(f"{feat}")
        lines.append(f"  human: mean={h.mean():.1f}  std={h.std():.1f}  min={h.min():.1f}  max={h.max():.1f}")
        lines.append(f"  bot  : mean={b.mean():.1f}  std={b.std():.1f}  min={b.min():.1f}  max={b.max():.1f}")
    lines.append("=" * 60)
    summary = "\n".join(lines)
    print(summary)
    return summary


if __name__ == "__main__":
    print("Generating 4750 sessions...")
    df = build_dataset()

    # Save all files in the same folder as this script
    training_path = os.path.join(SCRIPT_DIR, 'training_data.csv')
    human_path    = os.path.join(SCRIPT_DIR, 'human_only.csv')
    summary_path  = os.path.join(SCRIPT_DIR, 'summary.txt')

    df.to_csv(training_path, index=False)
    print(f"Saved: {training_path}  ({len(df)} rows)")

    human_df = df[df['label'] == 'human'][FEATURES]
    human_df.to_csv(human_path, index=False)
    print(f"Saved: {human_path}  ({len(human_df)} rows)")

    summary = print_summary(df)
    with open(summary_path, 'w') as f:
        f.write(summary)
    print(f"Saved: {summary_path}")