"""Small deterministic drum synthesizer; all voices are generated at runtime."""

from __future__ import annotations

import hashlib

import numpy as np
from scipy.signal import butter, sosfilt

_LEGACY_FACTORY_NAMES = (
    "kick_boom",
    "808",
    "snare_crack",
    "clap",
    "hat_closed",
    "hat_open",
    "rim",
    "perc",
)

_LEGACY_DURATIONS = {
    "kick_boom": 0.48,
    "808": 1.25,
    "snare_crack": 0.28,
    "clap": 0.34,
    "hat_closed": 0.12,
    "hat_open": 0.62,
    "rim": 0.16,
    "perc": 0.24,
}


_FILTER_ENVELOPES = {
    "kick": (0.68, 0.012),
    "snare": (0.72, 0.018),
    "clap": (0.78, 0.02),
    "hat_closed": (0.94, 0.005),
    "hat_open": (0.75, 0.06),
    "perc": (0.62, 0.012),
    "808": (0.86, 0.03),
}
_TRANSIENTS = {
    "kick": (1000, 10000, 0.10, 0.006),
    "snare": (1400, 15000, 0.10, 0.005),
    "clap": (1800, 15500, 0.09, 0.005),
    "hat_closed": (5200, 15500, 0.12, 0.003),
    "hat_open": (4000, 15000, 0.08, 0.005),
    "perc": (1400, 13000, 0.10, 0.004),
    "808": (180, 6500, 0.035, 0.007),
}


def _recipe(family, duration, start_hz, end_hz, sweep, decay, tone, partials, noise, *,
            hold=0.0, attack=0.001, saturation=1.0, filter_envelope=None, transient=None,
            tone_scale=1.0, noise_scale=1.0, color_ratio=1.0, time_scale=1.0,
            sweep_shape="exponential", click_attack=0.0, global_attack=0.0):
    """Build one explicit oscillator, filter, transient, and envelope recipe."""
    return {
        "family": family,
        "duration": duration,
        "start_hz": start_hz,
        "end_hz": end_hz,
        "sweep": sweep,
        "sweep_shape": sweep_shape,
        "decay": decay,
        "tone": tone,
        "partials": tuple(partials),
        "noise": tuple(noise),
        "hold": hold,
        "attack": attack,
        "saturation": saturation,
        "tone_scale": tone_scale,
        "noise_scale": noise_scale,
        "color_ratio": color_ratio,
        "time_scale": time_scale,
        "click_attack": click_attack,
        "global_attack": global_attack,
        "filter_envelope": filter_envelope or _FILTER_ENVELOPES[family],
        "transient": transient or _TRANSIENTS[family],
    }


# These recipes are original synthesis parameters. Noise is generated from the
# stable name/seed stream below; no recorded audio is loaded by the engine.
_RECIPES = {
    "kick_punch": _recipe("kick", 0.32, 210, 56.5, 0.028, 0.024, 1.00, ((1, 1.0), (2, 0.15)),
                           ((200, 1500, 0.08, 0.004, 0.0), (55, 180, 0.08, 0.05, 0.0)),
                           attack=0.024, saturation=4.0, click_attack=0.0005),
    "kick_deep": _recipe("kick", 0.44, 180, 48, 0.042, 0.038, 1.00, ((1, 1.0), (2, 0.15)),
                          ((200, 1500, 0.06, 0.004, 0.0), (55, 180, 0.08, 0.05, 0.0)),
                          attack=0.030, saturation=3.5, click_attack=0.0005),
    "kick_thump": _recipe("kick", 0.52, 112, 47, 0.032, 0.205, 1.00, ((1, 1.0), (2, 0.18)),
                           ((420, 5200, 0.16, 0.009, 0.0), (55, 220, 0.07, 0.045, 0.0)), saturation=1.25),
    "kick_sub": _recipe("kick", 0.68, 82, 38, 0.046, 0.026, 1.00, ((1, 1.0), (2, 0.08)),
                         ((500, 3200, 0.08, 0.008, 0.0), (35, 130, 0.035, 0.04, 0.0)), saturation=1.1,
                         transient=(1000, 10000, 0.06, 0.006)),
    "kick_snap": _recipe("kick", 0.40, 190, 52, 0.012, 0.125, 0.92, ((1, 1.0), (2, 0.2)),
                          ((1400, 14000, 0.34, 0.005, 0.0),), saturation=1.8, sweep_shape="linear"),
    "kick_rumble": _recipe("kick", 0.62, 96, 42, 0.075, 0.29, 1.00, ((1, 1.0), (2, 0.16), (3, 0.05)),
                            ((80, 600, 0.16, 0.085, 0.0), (300, 2600, 0.12, 0.014, 0.0)), saturation=2.0),

    "snare_snap": _recipe("snare", 0.30, 240, 212, 0.020, 0.016, 0.30, ((1, 1.0), (2, 0.15)),
                           ((250, 6500, 0.80, 0.016, 0.0), (1500, 6500, 0.35, 0.0112, 0.0)),
                           hold=0.024, attack=0.004, saturation=2.5, click_attack=0.0003,
                           transient=(1800, 9000, 0.25, 0.010)),
    "snare_body": _recipe("snare", 0.30, 240, 212, 0.020, 0.028, 0.30, ((1, 1.0), (2, 0.15)),
                           ((250, 6000, 0.80, 0.028, 0.0), (1500, 6000, 0.35, 0.0196, 0.0)),
                           hold=0.028, attack=0.004, saturation=2.0, click_attack=0.0003,
                           transient=(1800, 9000, 0.25, 0.010)),
    "snare_crack_wide": _recipe("snare", 0.38, 205, 178, 0.022, 0.075, 0.32, ((1, 1.0), (2, 0.22)),
                                 ((220, 12000, 0.76, 0.052, 0.0), (2500, 15500, 0.32, 0.018, 0.0)), saturation=1.4),
    "snare_snap_dry": _recipe("snare", 0.28, 235, 196, 0.015, 0.047, 0.22, ((1, 1.0),),
                               ((900, 15000, 0.85, 0.034, 0.0), (300, 4200, 0.18, 0.018, 0.0)), saturation=1.7),
    "snare_burst": _recipe("snare", 0.36, 220, 185, 0.018, 0.068, 0.25, ((1, 1.0), (3, 0.12)),
                            ((500, 14500, 0.66, 0.031, 0.0), (700, 12000, 0.32, 0.044, 0.012)), saturation=1.6),
    "snare_dust": _recipe("snare", 0.48, 178, 155, 0.04, 0.12, 0.40, ((1, 1.0), (2, 0.16)),
                           ((250, 8200, 0.62, 0.095, 0.0), (3500, 12500, 0.12, 0.026, 0.0)), saturation=2.1),

    "clap_stack": _recipe("clap", 0.40, 190, 174, 0.020, 0.015, 0.00, ((1, 1.0),),
                           ((700, 2800, 0.90, 0.015, 0.0), (700, 2800, 0.60, 0.017, 0.018),
                            (700, 2800, 0.55, 0.015, 0.032), (700, 2800, 0.50, 0.021, 0.050),
                            (2200, 6000, 0.35, 0.0135, 0.0)),
                           attack=0.002, saturation=1.2, click_attack=0.0003),
    "clap_body": _recipe("clap", 0.44, 175, 160, 0.02, 0.020, 0.00, ((1, 1.0),),
                          ((500, 3000, 0.70, 0.020, 0.0), (500, 3000, 0.55, 0.022, 0.018),
                           (500, 3000, 0.50, 0.022, 0.032), (500, 3000, 0.45, 0.026, 0.050),
                           (2200, 6000, 0.35, 0.018, 0.0)),
                          attack=0.002, saturation=1.6, click_attack=0.0003),
    "clap_wide": _recipe("clap", 0.50, 175, 165, 0.03, 0.12, 0.10, ((1, 1.0), (2, 0.08)),
                          ((160, 9500, 0.58, 0.055, 0.0), (1400, 15500, 0.36, 0.10, 0.014),
                           (500, 14500, 0.25, 0.075, 0.034)), saturation=1.25),
    "clap_sharp": _recipe("clap", 0.32, 205, 190, 0.018, 0.065, 0.08, ((1, 1.0),),
                           ((1500, 15500, 0.88, 0.025, 0.0), (800, 12000, 0.34, 0.045, 0.015)), saturation=1.8),
    "clap_dust": _recipe("clap", 0.48, 155, 145, 0.035, 0.13, 0.18, ((1, 1.0), (2, 0.12)),
                          ((220, 6800, 0.72, 0.10, 0.0), (600, 9000, 0.28, 0.085, 0.022)), saturation=2.0),
    "clap_tail": _recipe("clap", 0.62, 185, 170, 0.04, 0.16, 0.12, ((1, 1.0),),
                          ((220, 12500, 0.58, 0.045, 0.0), (380, 14500, 0.38, 0.07, 0.015),
                           (700, 15000, 0.26, 0.10, 0.037), (900, 14500, 0.16, 0.15, 0.064)), saturation=1.5),

    "hat_tight": _recipe("hat_closed", 0.16, 6200, 6200, 0.0, 0.014, 0.03,
                         ((1, 0.70), (1.31, 0.50), (1.72, 0.35)),
                         ((5200, 15500, 0.55, 0.014, 0.0), (6760, 15500, 0.30, 0.0084, 0.0)),
                         attack=0.0005, saturation=1.0, click_attack=0.0008,
                         transient=(5200, 15500, 0.40, 0.0008)),
    "hat_bright": _recipe("hat_closed", 0.13, 6200, 6200, 0.0, 0.011, 0.02,
                           ((1, 0.70), (1.31, 0.50), (1.72, 0.35)),
                           ((6000, 13000, 0.55, 0.011, 0.0), (7800, 13000, 0.30, 0.0066, 0.0)),
                           attack=0.0005, saturation=1.0, click_attack=0.0008, global_attack=0.003,
                           transient=(6000, 13000, 0.30, 0.0008)),
    "hat_closed_tight_tick": _recipe("hat_closed", 0.10, 6100, 6100, 0.0, 0.024, 0.18,
                                     ((1, 0.75), (1.29, 0.55), (1.67, 0.42), (1.94, 0.31)),
                                     ((4200, 15500, 0.84, 0.022, 0.0),), attack=0.0004, saturation=1.25),
    "hat_closed_bright": _recipe("hat_closed", 0.13, 7200, 6800, 0.006, 0.033, 0.16,
                                  ((1, 0.65), (1.31, 0.48), (1.73, 0.38), (2.11, 0.24)),
                                  ((5200, 15500, 0.92, 0.031, 0.0),), attack=0.0003, saturation=1.3),
    "hat_closed_dark": _recipe("hat_closed", 0.15, 4100, 3900, 0.008, 0.042, 0.22,
                                ((1, 0.72), (1.27, 0.45), (1.65, 0.30)),
                                ((2200, 9200, 0.72, 0.041, 0.0), (700, 2600, 0.08, 0.012, 0.0)), saturation=1.15),
    "hat_closed_dust": _recipe("hat_closed", 0.18, 4900, 4700, 0.01, 0.052, 0.16,
                                ((1, 0.6), (1.41, 0.36), (1.78, 0.24)),
                                ((2800, 11500, 0.82, 0.048, 0.0), (400, 2200, 0.12, 0.014, 0.0)), saturation=1.8),
    "hat_closed_metal": _recipe("hat_closed", 0.22, 5200, 5000, 0.016, 0.068, 0.24,
                                 ((1, 0.8), (1.27, 0.7), (1.58, 0.48), (1.91, 0.35), (2.17, 0.2)),
                                 ((3600, 14500, 0.70, 0.060, 0.0),), saturation=1.2),

    "hat_open_short": _recipe("hat_open", 0.70, 6200, 6200, 0.0, 0.11, 0.03,
                               ((1, 0.70), (1.31, 0.50), (1.72, 0.35)),
                               ((3200, 12000, 0.55, 0.11, 0.0), (4160, 12000, 0.30, 0.066, 0.0)),
                               attack=0.0005, saturation=1.0, click_attack=0.0008,
                               transient=(3200, 12000, 0.50, 0.0008)),
    "hat_open_wash": _recipe("hat_open", 1.60, 6200, 6200, 0.0, 0.33, 0.03,
                              ((1, 0.70), (1.31, 0.50), (1.72, 0.35)),
                              ((3000, 11000, 0.55, 0.33, 0.0), (3900, 11000, 0.30, 0.198, 0.0)),
                              attack=0.0005, saturation=1.0, click_attack=0.0008,
                              transient=(3000, 11000, 0.90, 0.0008)),
    "hat_open_sizzle": _recipe("hat_open", 0.54, 7600, 7100, 0.022, 0.17, 0.14,
                                ((1, 0.55), (1.31, 0.48), (1.73, 0.34), (2.11, 0.22)),
                                ((5200, 15500, 1.0, 0.16, 0.0), (1900, 8800, 0.13, 0.06, 0.0)), saturation=1.35),
    "hat_open_bright": _recipe("hat_open", 0.70, 7000, 6500, 0.035, 0.26, 0.18,
                                ((1, 0.62), (1.28, 0.48), (1.66, 0.34), (1.98, 0.22)),
                                ((4000, 15500, 0.88, 0.25, 0.0), (1300, 6500, 0.15, 0.08, 0.0)), saturation=1.3),
    "hat_open_dark": _recipe("hat_open", 0.72, 4200, 3900, 0.04, 0.29, 0.24,
                              ((1, 0.7), (1.27, 0.48), (1.63, 0.30)),
                              ((1700, 9800, 0.82, 0.27, 0.0), (500, 2300, 0.12, 0.08, 0.0)), saturation=1.2),
    "hat_open_long": _recipe("hat_open", 0.9, 5600, 5200, 0.05, 0.42, 0.18,
                              ((1, 0.62), (1.29, 0.5), (1.67, 0.34), (1.94, 0.27)),
                              ((2700, 15000, 0.86, 0.40, 0.0), (700, 3700, 0.12, 0.12, 0.0)), saturation=1.35),

    "perc_tom_low": _recipe("perc", 0.34, 255, 112, 0.038, 0.015, 0.92, ((1, 1.0), (2, 0.19), (3, 0.06)),
                             ((180, 2400, 0.19, 0.012, 0.0), (1500, 8500, 0.12, 0.012, 0.0)), saturation=1.3,
                             tone_scale=0.18),
    "perc_tom_high": _recipe("perc", 0.30, 430, 210, 0.028, 0.015, 0.88, ((1, 1.0), (2, 0.16), (3, 0.04)),
                              ((220, 3800, 0.17, 0.012, 0.0), (1800, 10000, 0.16, 0.012, 0.0)), saturation=1.4,
                              tone_scale=0.50),
    "perc_woodblock": _recipe("perc", 0.19, 1250, 980, 0.014, 0.045, 0.8, ((1, 1.0), (2, 0.62), (3, 0.22)),
                                ((700, 6500, 0.16, 0.008, 0.0), (2500, 12500, 0.13, 0.004, 0.0)), saturation=1.5),
    "perc_rimshot": _recipe("perc", 0.22, 1580, 1150, 0.012, 0.055, 0.68, ((1, 1.0), (2, 0.32)),
                             ((500, 13000, 0.28, 0.005, 0.0), (2200, 14500, 0.25, 0.004, 0.0)), saturation=1.8),
    "perc_bongo": _recipe("perc", 0.32, 330, 178, 0.024, 0.015, 0.88, ((1, 1.0), (2, 0.22), (3, 0.07)),
                           ((170, 3300, 0.18, 0.012, 0.0), (1100, 8500, 0.13, 0.012, 0.0)), saturation=1.25,
                           tone_scale=0.30),

    "808_round": _recipe("808", 3.0, 90, 36, 0.03, 0.90, 1.0, ((1, 1.0), (2, 0.12)),
                          ((40, 400, 0.02, 0.02, 0.0),), attack=0.06, saturation=3.0,
                          click_attack=0.0, transient=(40, 200, 0.0, 0.01),
                          filter_envelope=(0.9, 0.02)),
    "808_sub_clean": _recipe("808", 2.0, 90, 38, 0.03, 0.60, 1.0, ((1, 1.0), (2, 0.12)),
                              ((40, 400, 0.02, 0.02, 0.0),), attack=0.03, saturation=3.0,
                              click_attack=0.0, transient=(40, 200, 0.0, 0.01),
                              filter_envelope=(0.9, 0.02)),
    "808_long_glide": _recipe("808", 4.0, 83.6, 31.4, 0.12, 1.05, 0.95, ((1, 1.0), (2, 0.16), (3, 0.035)),
                               ((80, 800, 0.08, 0.014, 0.0), (1000, 14000, 0.4, 0.2, 0.0)), saturation=1.5),
    "808_drop": _recipe("808", 1.4, 124, 36, 0.055, 0.53, 0.92, ((1, 1.0), (2, 0.2)),
                         ((100, 1300, 0.09, 0.012, 0.0), (700, 4600, 0.06, 0.006, 0.0)), saturation=1.7),
    "808_bloom": _recipe("808", 6.4, 35.7, 41.0, 6.28, 0.82, 0.98,
                          ((1, 1.0), (2, 0.3), (3, 0.08)),
                          ((70, 600, 0.05, 0.014, 0.0), (1000, 14000, 0.012, 0.2, 0.0)),
                          saturation=1.25, sweep_shape="linear"),
    "808_grit": _recipe("808", 1.65, 61, 37, 0.043, 0.78, 0.88, ((1, 1.0), (2, 0.30), (3, 0.10)),
                         ((70, 1400, 0.11, 0.018, 0.0), (500, 5000, 0.07, 0.008, 0.0)), saturation=2.4),
}

FACTORY_NAMES = _LEGACY_FACTORY_NAMES + tuple(_RECIPES)
BASS_FACTORY_NAMES = frozenset(
    ("808",) + tuple(name for name, recipe in _RECIPES.items() if recipe["family"] == "808")
)
_DURATIONS = _LEGACY_DURATIONS | {name: recipe["duration"] for name, recipe in _RECIPES.items()}

# Targets were fitted against local one-shot measurements; the samples are not
# read by or included in the shipped synthesis path.
_MEASURED_TUNING = {
    "kick_thump": (0.520, 180.81, 56.90, 0.0245, 0.470, 0.050, 8.0, 4.00),
    "kick_sub": (0.680, 115.00, 47.00, 0.0450, 1.000, 1.000, 1.0, 1.00),
    "kick_snap": (0.400, 110.83, 44.59, 0.0800, 0.235, 0.100, 1.0, 1.00),
    "kick_rumble": (0.620, 150.00, 53.57, 0.0300, 0.235, 0.050, 8.0, 4.00),
    "snare_crack_wide": (0.380, 205.00, 178.00, 0.0220, 0.216, 0.050, 8.0, 1.00),
    "snare_snap_dry": (0.531, 235.00, 196.00, 0.0150, 1.446, 1.000, 1.0, 1.00),
    "snare_burst": (0.543, 220.00, 185.00, 0.0180, 1.310, 0.062, 1.0, 1.00),
    "snare_dust": (0.531, 178.00, 155.00, 0.0400, 0.548, 0.400, 1.0, 1.00),
    "clap_wide": (0.500, 175.00, 165.00, 0.0300, 0.162, 0.050, 8.0, 1.00),
    "clap_sharp": (0.358, 205.00, 190.00, 0.0180, 0.548, 1.000, 1.0, 1.00),
    "clap_dust": (0.480, 155.00, 145.00, 0.0350, 0.284, 0.100, 1.0, 1.00),
    "clap_tail": (0.620, 185.00, 170.00, 0.0400, 0.055, 4.000, 0.1, 1.00),
    "hat_closed_tight_tick": (0.223, 6100.00, 6100.00, 0.0000, 0.333, 0.050, 8.0, 1.00),
    "hat_closed_bright": (0.185, 7200.00, 6800.00, 0.0060, 0.101, 0.062, 8.0, 1.00),
    "hat_closed_dark": (0.194, 4100.00, 3900.00, 0.0080, 0.113, 1.000, 1.0, 1.00),
    "hat_closed_dust": (0.180, 4900.00, 4700.00, 0.0100, 0.053, 0.100, 1.0, 1.00),
    "hat_closed_metal": (0.340, 5200.00, 5000.00, 0.0160, 0.372, 0.100, 8.0, 1.00),
    "hat_open_sizzle": (0.663, 7600.00, 7100.00, 0.0220, 0.372, 4.000, 8.0, 1.00),
    "hat_open_bright": (0.700, 7000.00, 6500.00, 0.0350, 0.276, 4.000, 0.1, 1.00),
    "hat_open_dark": (0.795, 4200.00, 3900.00, 0.0400, 0.357, 0.050, 1.0, 1.00),
    "hat_open_long": (0.900, 5600.00, 5200.00, 0.0500, 0.151, 0.250, 8.0, 1.00),
    "perc_tom_low": (0.340, 255.00, 112.00, 0.0380, 1.000, 0.180, 1.0, 1.00),
    "perc_tom_high": (0.300, 430.00, 210.00, 0.0280, 1.000, 0.500, 1.0, 1.00),
    "perc_woodblock": (0.315, 1250.00, 980.00, 0.0140, 0.709, 0.100, 8.0, 1.00),
    "perc_rimshot": (0.315, 1580.00, 1150.00, 0.0120, 0.343, 4.000, 8.0, 4.00),
    "perc_bongo": (0.320, 330.00, 178.00, 0.0240, 1.000, 0.300, 1.0, 1.00),
    "808_long_glide": (4.000, 83.60, 31.40, 0.1200, 0.610, 1.000, 1.0, 1.00),
    "808_drop": (1.400, 133.65, 36.19, 0.0491, 1.095, 0.050, 8.0, 4.00),
    "808_bloom": (6.400, 35.70, 41.00, 6.2800, 0.880, 1.000, 1.0, 1.00),
    "808_grit": (3.261, 81.40, 31.43, 0.0332, 1.270, 0.050, 2.0, 1.00),
}
for _name, (_duration, _start, _end, _sweep, _time, _tone, _noise, _color) in _MEASURED_TUNING.items():
    _recipe_values = _RECIPES[_name]
    _recipe_values.update(
        duration=_duration, start_hz=_start, end_hz=_end, sweep=_sweep,
        time_scale=_time, tone_scale=_tone, noise_scale=_noise, color_ratio=_color,
    )
    _DURATIONS[_name] = _duration


def _rng(name: str, seed: int) -> np.random.Generator:
    # Stable across processes and Python versions; unlike hash(), no hash randomization.
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    name_seed = int.from_bytes(digest[:8], "little")
    return np.random.default_rng(np.random.SeedSequence([int(seed), name_seed]))


def _envelope(n: int, sr: int, decay: float, attack: float = 0.002) -> np.ndarray:
    t = np.arange(n, dtype=np.float64) / sr
    env = np.exp(-t / max(decay, 1e-4))
    env[: min(n, round(sr * attack))] *= np.linspace(0.0, 1.0, min(n, round(sr * attack)), endpoint=True)
    if n:
        env[-min(n, round(sr * 0.002)) :] *= np.linspace(1.0, 0.0, min(n, round(sr * 0.002)), endpoint=True)
    return env


def _recipe_envelope(t: np.ndarray, sr: int, decay: float, hold: float, attack: float) -> np.ndarray:
    env = np.exp(-np.maximum(t - hold, 0.0) / max(decay, 1e-4))
    attack_count = min(len(t), round(sr * attack))
    if attack_count:
        env[:attack_count] *= np.linspace(0.0, 1.0, attack_count, endpoint=True)
    tail_count = min(len(t), round(sr * 0.002))
    if tail_count:
        env[-tail_count:] *= np.linspace(1.0, 0.0, tail_count, endpoint=True)
    return env


def _synthesize_recipe(name: str, sr: int, seed: int, ratio: float, seconds: float) -> np.ndarray:
    recipe = _RECIPES[name]
    n = max(1, round(seconds * sr))
    t = np.arange(n, dtype=np.float64) / sr
    rng = _rng(name, seed)

    start_hz = recipe["start_hz"] * ratio
    end_hz = recipe["end_hz"] * ratio
    sweep = recipe["sweep"]
    if sweep > 0 and recipe["sweep_shape"] == "linear":
        fraction = np.minimum(t / sweep, 1.0)
        frequency = start_hz + (end_hz - start_hz) * fraction
    elif sweep > 0:
        frequency = end_hz + (start_hz - end_hz) * np.exp(-t / sweep)
    else:
        frequency = np.full(n, start_hz, dtype=np.float64)
    phase = np.zeros(n, dtype=np.float64)
    if n > 1:
        phase[1:] = np.cumsum(frequency[:-1]) * (2.0 * np.pi / sr)

    oscillator = np.zeros(n, dtype=np.float64)
    for harmonic, level in recipe["partials"]:
        oscillator += level * np.sin(phase * harmonic)
    signal = recipe["tone"] * recipe["tone_scale"] * oscillator * _recipe_envelope(
        t, sr, recipe["decay"] * recipe["time_scale"], recipe["hold"], recipe["attack"]
    )

    def filtered_noise(noise: np.ndarray, low: float, high: float) -> np.ndarray:
        color = recipe["color_ratio"]
        low = max(20.0, min(float(low) * ratio * color, sr * 0.45))
        high = max(low * 1.1, min(float(high) * ratio * color, sr * 0.48))
        return sosfilt(butter(2, (low, high), btype="bandpass", fs=sr, output="sos"), noise)

    filter_end_ratio, filter_sweep = recipe["filter_envelope"]
    for low, high, gain, noise_decay, delay in recipe["noise"]:
        white_noise = rng.standard_normal(n)
        layer_noise = filtered_noise(white_noise, low, high)
        if filter_sweep > 0 and filter_end_ratio < 1:
            settled_high = max(float(low) * 1.1, float(high) * filter_end_ratio)
            settled_noise = filtered_noise(white_noise, low, settled_high)
            blend = np.exp(-t / filter_sweep)
            layer_noise = settled_noise + (layer_noise - settled_noise) * blend
        delay_samples = min(n, round(delay * sr))
        if delay_samples:
            shifted = np.zeros(n, dtype=np.float64)
            shifted[delay_samples:] = layer_noise[:n - delay_samples]
            layer_noise = shifted
        layer_env = np.exp(-np.maximum(t - delay - recipe["hold"], 0.0) / max(noise_decay * recipe["time_scale"], 1e-4))
        layer_env[t < delay] = 0.0
        signal += recipe["noise_scale"] * gain * layer_noise * layer_env

    click_low, click_high, click_gain, click_decay = recipe["transient"]
    click_noise = filtered_noise(rng.standard_normal(n), click_low, click_high)
    click_env = np.exp(-t / max(click_decay * recipe["time_scale"], 1e-4))
    click_attack = recipe.get("click_attack", 0.0)
    if click_attack > 0:
        ramp = np.minimum(t / click_attack, 1.0)
        click_env *= ramp
    signal += recipe["noise_scale"] * click_gain * click_noise * click_env

    # Normalise before the saturator so the drive is predictable across
    # recipes: a high drive compresses the body up towards the peaks, which is
    # what makes commercial one-shots read as loud and clipped.
    before = np.max(np.abs(signal)) if n else 0.0
    if before > 0:
        signal = signal / before
    global_attack = recipe.get("global_attack", 0.0)
    if global_attack > 0:
        count = min(n, round(global_attack * sr))
        if count:
            signal[:count] *= np.linspace(0.0, 1.0, count, endpoint=True)
    drive = recipe["saturation"]
    if drive > 0:
        signal = np.tanh(signal * drive) / np.tanh(drive)
    peak = np.max(np.abs(signal)) if n else 0.0
    if peak > 0:
        signal = signal / peak * 0.9
    return np.asarray(signal, dtype=np.float32)


def synthesize(name, sr=44100, seed=1337, pitch=0, duration=None, note_hz=None) -> np.ndarray:
    """Synthesize one mono float32 voice with deterministic seeded noise."""
    if name not in FACTORY_NAMES:
        raise ValueError(f"unknown factory sound: {name}")
    if not isinstance(sr, int) or sr < 8000 or sr > 192000:
        raise ValueError("sample rate must be an integer from 8000 to 192000")
    seconds = _DURATIONS[name] if duration is None else float(duration)
    if not np.isfinite(seconds) or seconds <= 0 or seconds > 30:
        raise ValueError("duration must be greater than 0 and at most 30 seconds")
    n = max(1, round(seconds * sr))
    t = np.arange(n, dtype=np.float64) / sr
    rng = _rng(name, seed)
    noise = rng.standard_normal(n)
    semitones = float(pitch)
    if not np.isfinite(semitones) or not -48 <= semitones <= 48:
        raise ValueError("pitch must be finite and between -48 and 48 semitones")
    ratio = 2.0 ** (semitones / 12.0)

    if name in _RECIPES:
        if note_hz is not None:
            if isinstance(note_hz, bool) or not isinstance(note_hz, (int, float)):
                raise ValueError("note_hz must be a finite frequency from 1 to 20000 Hz")
            if not np.isfinite(note_hz) or not 1 <= note_hz <= 20000:
                raise ValueError("note_hz must be a finite frequency from 1 to 20000 Hz")
            if name not in BASS_FACTORY_NAMES:
                raise ValueError("note_hz is only supported by 808 recipes")
            ratio *= float(note_hz) / _RECIPES[name]["end_hz"]
        return _synthesize_recipe(name, sr, seed, ratio, seconds)
    if note_hz is not None:
        raise ValueError("note_hz is only supported by 808 recipes")

    def filtered_noise(low, high):
        low = max(20.0, min(float(low) * ratio, sr * 0.45))
        high = max(low * 1.1, min(float(high) * ratio, sr * 0.48))
        return sosfilt(butter(2, (low, high), btype="bandpass", fs=sr, output="sos"), noise)

    signal: np.ndarray

    if name == "kick_boom":
        f0 = 47.0 * ratio
        phase = 2 * np.pi * (f0 * t + 125.0 * 0.055 * (1.0 - np.exp(-t / 0.055)))
        signal = np.sin(phase) * np.exp(-t / 0.19) + 0.12 * noise * np.exp(-t / 0.009)
    elif name == "808":
        f0 = 41.2 * ratio
        phase = 2 * np.pi * (f0 * t + 23.0 * 0.08 * (1.0 - np.exp(-t / 0.08)))
        signal = np.tanh(1.25 * np.sin(phase)) * np.exp(-t / max(seconds * 0.72, 0.1))
        signal += 0.06 * noise * np.exp(-t / 0.008)
    elif name == "snare_crack":
        tone = np.sin(2 * np.pi * (190.0 * ratio * t - 90.0 * ratio * 0.025 * (1.0 - np.exp(-t / 0.025))))
        signal = 0.75 * filtered_noise(250, 12000) * np.exp(-t / 0.052) + 0.42 * tone * np.exp(-t / 0.075)
    elif name == "clap":
        signal = np.zeros(n, dtype=np.float64)
        for delay, gain in ((0.0, 0.8), (0.012, 0.62), (0.025, 0.48), (0.042, 0.25)):
            offset = round(delay * sr)
            if offset < n:
                count = n - offset
                signal[offset:] += gain * filtered_noise(250, 12000)[:count] * np.exp(-np.arange(count) / (sr * 0.025))
        signal += 0.12 * np.sin(2 * np.pi * 175 * ratio * t) * np.exp(-t / 0.09)
    elif name in ("hat_closed", "hat_open"):
        decay = 0.045 if name == "hat_closed" else 0.32
        metallic = sum(np.sin(2 * np.pi * f * ratio * t) for f in (4120, 5270, 6810, 7930)) / 4
        signal = (0.78 * filtered_noise(3500, 11000) + 0.34 * metallic) * np.exp(-t / decay)
    elif name == "rim":
        signal = (0.7 * filtered_noise(500, 12000) * np.exp(-t / 0.006)
                  + 0.45 * np.sin(2 * np.pi * 1550 * ratio * t) * np.exp(-t / 0.026))
    else:  # perc
        f = 320.0 * ratio
        signal = np.sin(2 * np.pi * f * t - 190 * 0.035 * (1 - np.exp(-t / 0.035))) * np.exp(-t / 0.11)
        signal += 0.16 * noise * np.exp(-t / 0.012)

    signal *= _envelope(n, sr, _DURATIONS[name])
    peak = np.max(np.abs(signal)) if n else 0.0
    if peak > 0:
        signal = signal / peak * 0.9
    return np.asarray(signal, dtype=np.float32)


def is_kick_source(source) -> bool:
    """Whether a track source is a factory kick (any `factory:kick_*`), for kick-driven features."""
    return isinstance(source, str) and source.startswith("factory:kick")

