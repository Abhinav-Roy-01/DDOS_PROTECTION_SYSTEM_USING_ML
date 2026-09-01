import numpy as np
import pandas as pd

np.random.seed(42)
Features=[
    'click_count',
    'avg_click_interval'
    'click_interval_variance',
    'click_interval_entropy',
    'mouse_velocity_variance',
    'max_element_click_rate',
    'scroll_events',
    'keystroke_count',
]

def gen_casual_browser(n):
    # reads pages,scrollls and clicks ocassionally.
    return pd.DataFrame({ 
        'click_count':      np.random.poisson(5,n),
        'avg_click_interval':      np.random.normal(1200,300,n),
        'click_interval_variance':  np.random.normal(200000,70000,n),
        'click_interval_entropy':   np.random.normal(3.0,0.4,n),
        'mouse_velocity_variance':  np.random.normal(0.55,0.18,n),
        'max_element_click_rate':   np.random.uniform(0.1,1,5,n),
        'scroll_events':            np.random.poisson(10,n),
        'keystroke_count':          np.random.poisson(8,n),
        'persona':                  'casual_browser',
        'label':                    'human',
    })

def gen_power_user(n):
    # Fast, purposeful interactions — high click rate but natural variance.
    return pd.DataFrame({
        'click_count':             np.random.poisson(18, n),
        'avg_click_interval':      np.random.normal(500, 150, n),
        'click_interval_variance': np.random.normal(120000, 40000, n),
        'click_interval_entropy':  np.random.normal(2.6, 0.4, n),
        'mouse_velocity_variance': np.random.normal(0.85, 0.25, n),
        'max_element_click_rate':  np.random.uniform(1.0, 4.0, n),
        'scroll_events':           np.random.poisson(4, n),
        'keystroke_count':         np.random.poisson(45, n),
        'persona':                 'power_user',
        'label':                   'human',
    })

def gen_mobile_user(n):
    # Mobile: fewer scroll events, tap-style clicks, no mouse velocity.
    return pd.DataFrame({
        'click_count':             np.random.poisson(7, n),
        'avg_click_interval':      np.random.normal(1000, 350, n),
        'click_interval_variance': np.random.normal(160000, 55000, n),
        'click_interval_entropy':  np.random.normal(2.4, 0.5, n),
        'mouse_velocity_variance': np.random.normal(0.05, 0.03, n),
        'max_element_click_rate':  np.random.uniform(0.1, 2.0, n),
        'scroll_events':           np.random.poisson(3, n),
        'keystroke_count':         np.random.poisson(12, n),
        'persona':                 'mobile_user',
        'label':                   'human',
    })




def gen_http_flooder(n):
    # Raw HTTP flood — no browser context at all.
    return pd.DataFrame({
        'click_count':             np.random.randint(100, 300, n),
        'avg_click_interval':      np.random.normal(30, 3, n),
        'click_interval_variance': np.random.normal(8, 2, n),
        'click_interval_entropy':  np.random.normal(0.02, 0.01, n),
        'mouse_velocity_variance': np.zeros(n),
        'max_element_click_rate':  np.random.uniform(20, 60, n),
        'scroll_events':           np.zeros(n),
        'keystroke_count':         np.zeros(n),
        'persona':                 'http_flooder',
        'label':                   'bot',
    })

def gen_slow_bot(n):
    # Timing-mimicry bot — metronomic, near-zero variance.
    return pd.DataFrame({
        'click_count':             np.random.poisson(8, n),
        'avg_click_interval':      np.random.normal(950, 15, n),
        'click_interval_variance': np.random.normal(150, 10, n),
        'click_interval_entropy':  np.random.normal(0.12, 0.04, n),
        'mouse_velocity_variance': np.zeros(n),
        'max_element_click_rate':  np.random.uniform(0.8, 1.3, n),
        'scroll_events':           np.zeros(n),
        'keystroke_count':         np.zeros(n),
        'persona':                 'slow_bot',
        'label':                   'bot',
    })

def gen_headless_browser(n):
    # Puppeteer/Playwright bot — straight-line mouse, no jitter.
    return pd.DataFrame({
        'click_count':             np.random.poisson(11, n),
        'avg_click_interval':      np.random.normal(280, 12, n),
        'click_interval_variance': np.random.normal(420, 30, n),
        'click_interval_entropy':  np.random.normal(0.65, 0.08, n),
        'mouse_velocity_variance': np.random.normal(0.008, 0.002, n),
        'max_element_click_rate':  np.random.uniform(2.5, 6.0, n),
        'scroll_events':           np.random.poisson(1, n),
        'keystroke_count':         np.zeros(n),
        'persona':                 'headless_browser',
        'label':                   'bot',
    })

def gen_credential_stuffer(n):
    # Automated form submitter — bulk-pasted keystrokes, no variance.
    return pd.DataFrame({
        'click_count':             np.random.poisson(4, n),
        'avg_click_interval':      np.random.normal(1100, 8, n),
        'click_interval_variance': np.random.normal(40, 5, n),
        'click_interval_entropy':  np.random.normal(0.08, 0.03, n),
        'mouse_velocity_variance': np.random.normal(0.015, 0.004, n),
        'max_element_click_rate':  np.random.uniform(0.4, 1.0, n),
        'scroll_events':           np.zeros(n),
        'keystroke_count':         np.random.normal(38, 1.5, n),
        'persona':                 'credential_stuffer',
        'label':                   'bot',
    })



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
    df[Features] = df[Features].clip(lower=0)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    return df


def print_summary(df):
    lines = []
    lines.append("=" * 60)
    lines.append("DATASET SUMMARY")
    lines.append("=" * 60)
    lines.append(f"Total sessions   : {len(df)}")
    lines.append(f"Human sessions   : {(df['label'] == 'human').sum()}")
    lines.append(f"Bot sessions     : {(df['label'] == 'bot').sum()}")
    lines.append("")
    lines.append("Breakdown by persona:")
    for persona, count in df['persona'].value_counts().items():
        lines.append(f"  {persona:<25} {count}")
    lines.append("")
    lines.append("Feature statistics (human vs bot):")
    lines.append("-" * 60)
    for feat in Features:
        h = df[df['label'] == 'human'][feat]
        b = df[df['label'] == 'bot'][feat]
        lines.append(f"{feat}")
        lines.append(f"  human: mean={h.mean():.1f}  std={h.std():.1f}  "
                     f"min={h.min():.1f}  max={h.max():.1f}")
        lines.append(f"  bot  : mean={b.mean():.1f}  std={b.std():.1f}  "
                     f"min={b.min():.1f}  max={b.max():.1f}")
    lines.append("=" * 60)
    summary = "\n".join(lines)
    print(summary)
    return summary


if __name__ == "_main_":
    print("Generating 4750 sessions...")
    df = build_dataset()

    df.to_csv('training_data.csv', index=False)
    print(f"Saved: training_data.csv  ({len(df)} rows)")

    human_df = df[df['label'] == 'human'][Features]
    human_df.to_csv('human_only.csv', index=False)
    print(f"Saved: human_only.csv  ({len(human_df)} rows)")

    summary = print_summary(df)
    with open('summary.txt', 'w') as f:
        f.write(summary)
    print("Saved: summary.txt")