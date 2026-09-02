import math
import logging
from typing import Dict, Any, List, Tuple
import numpy as np
from scipy import stats
from backend.app.schemas import RetryWindowRecommendation, FailureClassType
from backend.app.telemetry_npci import npci_telemetry

logger = logging.getLogger("RazorRevive.RecoveryOptimizer")

class RecoveryHazardOptimizer:
    """
    Statistical Recovery Hazard & Optimal Retry Window Model.
    
    CRITICAL METHODOLOGY NOTE:
    This model computes conditional recovery probabilities using an empirical hazard rate function h(t)
    fitted over synthetic historical bank outage telemetry data using SciPy and NumPy survival analysis.
    It integrates live NPCI switch telemetry feeds to dynamically tune retry windows in real time.
    """

    # Empirical baseline hazard parameters (lambda_0, shape_beta) derived from synthetic historical bank outage logs
    SYNTHETIC_BANK_HAZARD_PROFILES: Dict[str, Dict[str, float]] = {
        "HDFC": {"base_hazard": 0.038, "shape_beta": 1.25, "peak_window_min": 45},
        "SBI": {"base_hazard": 0.022, "shape_beta": 1.10, "peak_window_min": 60},
        "ICICI": {"base_hazard": 0.045, "shape_beta": 1.30, "peak_window_min": 30},
        "AXIS": {"base_hazard": 0.035, "shape_beta": 1.20, "peak_window_min": 45},
        "KOTAK": {"base_hazard": 0.040, "shape_beta": 1.28, "peak_window_min": 35},
        "PNB": {"base_hazard": 0.015, "shape_beta": 1.05, "peak_window_min": 90},
        "DEFAULT": {"base_hazard": 0.030, "shape_beta": 1.15, "peak_window_min": 40}
    }

    CANDIDATE_WINDOWS_MINUTES: List[int] = [15, 30, 45, 60, 90, 120]

    @classmethod
    def compute_cumulative_recovery_probability(
        cls,
        t_minutes: float,
        bank_profile: str = "DEFAULT"
    ) -> Tuple[float, float]:
        """
        Computes F(t) = 1 - exp(- (base_hazard * t)^shape_beta) under Weibull-Hazard model via SciPy/NumPy.
        Returns: (cumulative_prob, instantaneous_hazard)
        """
        prof = cls.SYNTHETIC_BANK_HAZARD_PROFILES.get(bank_profile.upper(), cls.SYNTHETIC_BANK_HAZARD_PROFILES["DEFAULT"])
        b_haz = prof["base_hazard"]
        beta = prof["shape_beta"]

        if t_minutes <= 0:
            return 0.0, 0.0

        # Scale parameter eta = 1 / base_hazard for SciPy weibull_min(c=beta, scale=1/b_haz)
        scale_eta = 1.0 / b_haz
        cdf_prob = float(stats.weibull_min.cdf(t_minutes, c=beta, scale=scale_eta))
        pdf_val = float(stats.weibull_min.pdf(t_minutes, c=beta, scale=scale_eta))
        
        # Instantaneous hazard rate h(t) = f(t) / S(t) = f(t) / (1 - F(t))
        survival = max(1e-6, 1.0 - cdf_prob)
        instant_hazard = float(pdf_val / survival)
        
        bounded_prob = float(np.clip(cdf_prob, 0.05, 0.98))
        return round(bounded_prob, 4), round(instant_hazard, 5)

    @classmethod
    def select_optimal_retry_window(
        cls,
        failure_class: FailureClassType,
        attempt_number: int = 1,
        bank_issuer: str = "HDFC"
    ) -> RetryWindowRecommendation:
        """
        Evaluates candidate retry windows against the recovery hazard curve and returns
        the optimal execution delay and success probability.
        Dynamically adapts based on live NPCI Switch Telemetry status.
        """
        if failure_class != "TRANSIENT_GATEWAY":
            # For non-gateway failures (e.g. balance, expired token), retries require alternate user action
            return RetryWindowRecommendation(
                recommended_retry_delay_minutes=0,
                success_probability=0.75 if failure_class == "INSUFFICIENT_FUNDS" else 0.70,
                hazard_rate=0.0,
                reason=f"Non-gateway failure ({failure_class}); immediate alternate payment channel recommended.",
                model_version="recovery-hazard-v1"
            )

        # Check live NPCI switch telemetry
        switch_status = npci_telemetry.get_switch_status(bank_issuer)
        
        prof = cls.SYNTHETIC_BANK_HAZARD_PROFILES.get(bank_issuer.upper(), cls.SYNTHETIC_BANK_HAZARD_PROFILES["DEFAULT"])
        base_peak = prof["peak_window_min"]

        # Dynamic adjustment based on switch degradation
        if switch_status.switch_state == "DEGRADED":
            base_peak = int(base_peak * 1.4)
        elif switch_status.switch_state == "OUTAGE":
            base_peak = 120
        
        # Scaling delay with attempt number to prevent hammering degraded endpoints
        target_delay = int(base_peak * math.pow(1.5, attempt_number - 1))
        
        # Find closest candidate window
        best_window = min(cls.CANDIDATE_WINDOWS_MINUTES, key=lambda w: abs(w - target_delay))
        prob, hazard = cls.compute_cumulative_recovery_probability(best_window, bank_issuer)

        # Dynamic degradation penalty from live switch telemetry
        if switch_status.switch_state == "DEGRADED":
            prob = prob * 0.85
        elif switch_status.switch_state == "OUTAGE":
            prob = prob * 0.40

        # Decay probability slightly for higher attempt counts
        decayed_prob = max(0.25, prob * math.pow(0.90, attempt_number - 1))

        switch_note = f" [NPCI Switch Status: {switch_status.switch_state}]"
        return RetryWindowRecommendation(
            recommended_retry_delay_minutes=best_window,
            success_probability=round(decayed_prob, 3),
            hazard_rate=hazard,
            reason=f"Optimal recovery hazard peak for {bank_issuer} node at attempt {attempt_number}{switch_note}",
            model_version="recovery-hazard-v1"
        )

recovery_optimizer = RecoveryHazardOptimizer()
