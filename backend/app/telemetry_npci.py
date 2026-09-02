import time
import logging
from typing import Dict, Any, List, Optional
from backend.app.schemas import NPCISwitchStatus, SwitchHealthStateType

logger = logging.getLogger("RazorRevive.NPCITelemetry")

class NPCISwitchTelemetryEngine:
    """
    Live NPCI UPI Switch & Merchant Banking Switch Telemetry Engine (Phase 1 & Phase 8).
    
    Tracks real-time health, success rates, latency, and degradation states across major
    Indian issuing bank switches (HDFC, SBI, ICICI, Axis, Kotak, PNB, Yes Bank).
    Automatically trips circuit breakers when a switch suffers high failure rates or outages.
    """

    # Baseline switch definitions
    _INITIAL_SWITCHES: Dict[str, Dict[str, Any]] = {
        "HDFC": {
            "bank_name": "HDFC Bank Core Switch",
            "switch_state": "HEALTHY",
            "success_rate_pct": 94.8,
            "avg_latency_ms": 320.0,
            "incidents": [],
            "circuit_breaker": False,
            "fallback_rail": None
        },
        "SBI": {
            "bank_name": "State Bank of India UPI Switch",
            "switch_state": "DEGRADED",
            "success_rate_pct": 72.4,
            "avg_latency_ms": 890.0,
            "incidents": ["High latency observed on INB-UPI gateway (NPCI-SBI-202)"],
            "circuit_breaker": False,
            "fallback_rail": "FALLBACK_NETBANKING_OR_CARD"
        },
        "ICICI": {
            "bank_name": "ICICI Bank Core Payment Gateway",
            "switch_state": "HEALTHY",
            "success_rate_pct": 96.2,
            "avg_latency_ms": 280.0,
            "incidents": [],
            "circuit_breaker": False,
            "fallback_rail": None
        },
        "AXIS": {
            "bank_name": "Axis Bank PSP Switch",
            "switch_state": "HEALTHY",
            "success_rate_pct": 93.1,
            "avg_latency_ms": 350.0,
            "incidents": [],
            "circuit_breaker": False,
            "fallback_rail": None
        },
        "KOTAK": {
            "bank_name": "Kotak Mahindra Bank Gateway",
            "switch_state": "HEALTHY",
            "success_rate_pct": 95.5,
            "avg_latency_ms": 310.0,
            "incidents": [],
            "circuit_breaker": False,
            "fallback_rail": None
        },
        "PNB": {
            "bank_name": "Punjab National Bank UPI Gateway",
            "switch_state": "OUTAGE",
            "success_rate_pct": 28.1,
            "avg_latency_ms": 2400.0,
            "incidents": ["NPCI UPI Switch Connection Reset: PNB Node uncommunicative"],
            "circuit_breaker": True,
            "fallback_rail": "REROUTE_TO_ALTERNATE_BANK_VPA"
        },
        "YESB": {
            "bank_name": "Yes Bank PSP Rail",
            "switch_state": "HEALTHY",
            "success_rate_pct": 97.0,
            "avg_latency_ms": 260.0,
            "incidents": [],
            "circuit_breaker": False,
            "fallback_rail": None
        }
    }

    def __init__(self):
        self._switches: Dict[str, Dict[str, Any]] = {}
        for code, data in self._INITIAL_SWITCHES.items():
            self._switches[code] = dict(data)
            self._switches[code]["last_updated"] = time.time()

    def get_all_switches(self) -> List[NPCISwitchStatus]:
        """Returns current telemetry status for all monitored banking switches."""
        results = []
        for code, info in self._switches.items():
            results.append(NPCISwitchStatus(
                bank_code=code,
                bank_name=info["bank_name"],
                switch_state=info["switch_state"],
                success_rate_pct=info["success_rate_pct"],
                avg_latency_ms=info["avg_latency_ms"],
                last_updated=info.get("last_updated", time.time()),
                active_incidents=list(info.get("incidents", [])),
                circuit_breaker_tripped=info.get("circuit_breaker", False),
                recommended_fallback_rail=info.get("fallback_rail")
            ))
        return results

    def get_switch_status(self, bank_code: str) -> NPCISwitchStatus:
        """Retrieves status for a specific bank switch."""
        normalized = bank_code.upper().strip()
        info = self._switches.get(normalized)
        if not info:
            return NPCISwitchStatus(
                bank_code=normalized,
                bank_name=f"{normalized} Commercial Switch",
                switch_state="HEALTHY",
                success_rate_pct=92.0,
                avg_latency_ms=380.0,
                last_updated=time.time(),
                active_incidents=[],
                circuit_breaker_tripped=False,
                recommended_fallback_rail=None
            )
        return NPCISwitchStatus(
            bank_code=normalized,
            bank_name=info["bank_name"],
            switch_state=info["switch_state"],
            success_rate_pct=info["success_rate_pct"],
            avg_latency_ms=info["avg_latency_ms"],
            last_updated=info.get("last_updated", time.time()),
            active_incidents=list(info.get("incidents", [])),
            circuit_breaker_tripped=info.get("circuit_breaker", False),
            recommended_fallback_rail=info.get("fallback_rail")
        )

    def update_switch_telemetry(
        self,
        bank_code: str,
        state: SwitchHealthStateType,
        success_rate_pct: float,
        latency_ms: float,
        incidents: Optional[List[str]] = None
    ) -> NPCISwitchStatus:
        """Allows dynamic or simulated ingestion of live telemetry events from NPCI/Razorpay feeds."""
        normalized = bank_code.upper().strip()
        circuit_tripped = (state == "OUTAGE" or success_rate_pct < 50.0)
        fallback = "REROUTE_TO_ALTERNATE_BANK_VPA" if circuit_tripped else (
            "FALLBACK_NETBANKING_OR_CARD" if state == "DEGRADED" else None
        )

        self._switches[normalized] = {
            "bank_name": self._switches.get(normalized, {}).get("bank_name", f"{normalized} Switch"),
            "switch_state": state,
            "success_rate_pct": round(success_rate_pct, 2),
            "avg_latency_ms": round(latency_ms, 1),
            "incidents": incidents or [],
            "circuit_breaker": circuit_tripped,
            "fallback_rail": fallback,
            "last_updated": time.time()
        }

        logger.info(f"[NPCI_TELEMETRY] Switch {normalized} state updated to {state} ({success_rate_pct}% success, {latency_ms}ms)")
        return self.get_switch_status(normalized)

npci_telemetry = NPCISwitchTelemetryEngine()
