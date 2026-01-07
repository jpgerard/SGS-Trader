"""
Deterministic trigger rules for SGS alerts.

Trigger logic:
- Primary condition: contradiction_with_headlines == "yes"
- Secondary conditions (need at least 2 of 5):
  1. demand classification in {softening, deteriorating} and conf >= 0.70
  2. margin classification == under_pressure and conf >= 0.65
  3. uncertainty direction == increase and conf >= 0.70
  4. guidance implicit_shift == negative
  5. narrative_shift in {subtle_deterioration, clear_deterioration}
"""

from typing import Dict, Tuple, List
from sgs.utils.logging import get_logger

logger = get_logger("triggers")


def evaluate_trigger(sgs_json: Dict) -> Tuple[bool, List[str]]:
    """
    Evaluate whether SGS data triggers an alert.
    
    Args:
        sgs_json: Validated SGS JSON dict
    
    Returns:
        Tuple of (trigger_flag, trigger_reasons)
        - trigger_flag: True if alert should be sent
        - trigger_reasons: List of reason strings (empty if no trigger)
    """
    reasons = []
    
    # Primary condition: contradiction with headlines
    contradiction = sgs_json.get('contradiction_with_headlines', '')
    
    if contradiction != 'yes':
        logger.debug(f"Primary condition not met: contradiction_with_headlines={contradiction}")
        return (False, [])
    
    # Primary condition met
    reasons.append(f"Contradiction with headlines: {contradiction}")
    logger.debug("Primary condition met: contradiction_with_headlines=yes")
    
    # Evaluate secondary conditions
    secondary_conditions_met = 0
    
    # Condition 1: Demand softening/deteriorating with high confidence
    demand = sgs_json.get('demand_trajectory', {})
    demand_class = demand.get('classification', '')
    demand_conf = demand.get('confidence', 0.0)
    
    if demand_class in ['softening', 'deteriorating'] and demand_conf >= 0.70:
        secondary_conditions_met += 1
        reasons.append(f"Demand {demand_class} (confidence: {demand_conf:.2f})")
        logger.debug(f"Condition 1 met: demand={demand_class}, conf={demand_conf}")
    
    # Condition 2: Margin under pressure with moderate confidence
    margin = sgs_json.get('margin_outlook', {})
    margin_class = margin.get('classification', '')
    margin_conf = margin.get('confidence', 0.0)
    
    if margin_class == 'under_pressure' and margin_conf >= 0.65:
        secondary_conditions_met += 1
        reasons.append(f"Margins under pressure (confidence: {margin_conf:.2f})")
        logger.debug(f"Condition 2 met: margin=under_pressure, conf={margin_conf}")
    
    # Condition 3: Uncertainty increasing with high confidence
    uncertainty = sgs_json.get('uncertainty_change', {})
    uncertainty_dir = uncertainty.get('direction', '')
    uncertainty_conf = uncertainty.get('confidence', 0.0)
    
    if uncertainty_dir == 'increase' and uncertainty_conf >= 0.70:
        secondary_conditions_met += 1
        reasons.append(f"Uncertainty increasing (confidence: {uncertainty_conf:.2f})")
        logger.debug(f"Condition 3 met: uncertainty=increase, conf={uncertainty_conf}")
    
    # Condition 4: Guidance implicit shift negative
    guidance = sgs_json.get('guidance_quality', {})
    implicit_shift = guidance.get('implicit_shift', '')
    
    if implicit_shift == 'negative':
        secondary_conditions_met += 1
        reasons.append(f"Guidance implicit shift: {implicit_shift}")
        logger.debug(f"Condition 4 met: implicit_shift=negative")
    
    # Condition 5: Narrative deterioration
    narrative = sgs_json.get('narrative_shift', '')
    
    if narrative in ['subtle_deterioration', 'clear_deterioration']:
        secondary_conditions_met += 1
        reasons.append(f"Narrative shift: {narrative}")
        logger.debug(f"Condition 5 met: narrative={narrative}")
    
    # Need at least 2 secondary conditions
    logger.debug(f"Secondary conditions met: {secondary_conditions_met}/5")
    
    if secondary_conditions_met >= 2:
        logger.info(f"Trigger activated: {secondary_conditions_met} secondary conditions met")
        return (True, reasons)
    else:
        logger.debug(f"Trigger NOT activated: only {secondary_conditions_met} secondary conditions met (need 2)")
        return (False, [])
