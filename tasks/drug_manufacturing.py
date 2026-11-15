"""
Performs drug manufacturing when the action timer is ready.
Requires the Gangster occupation and the Mortician Assistant earn unlocked
(and a science degree — the game redirects to the income page otherwise).
"""

from tasks.base import Task, Action
from state import GameState, is_gangster

# Earn that must be unlocked before drug manufacturing is attempted.
REQUIRED_EARN = "mortician_assistant"


def required_earn_unlocked() -> bool:
    """True if the earn catalog (scraped from earn.asp) lists Mortician
    Assistant as an available earn."""
    import earn_planner
    return earn_planner.catalog_available(REQUIRED_EARN)


def eligibility_reasons(state: GameState) -> list:
    """Reasons drug manufacturing isn't allowed for this character (empty if it is)."""
    reasons = []
    if not is_gangster(state.occupation, state.rank):
        reasons.append("Not a gangster")
    if not required_earn_unlocked():
        reasons.append("Mortician Assistant earn not unlocked")
    return reasons


def is_eligible(state: GameState) -> bool:
    return (is_gangster(state.occupation, state.rank)
            and required_earn_unlocked())


class DrugManufacturingTask(Task):
    priority = 60
    label = 'Drug Manufacturing'

    def can_run(self, state: GameState) -> bool:
        import executor
        if executor.drug_manufacture_cooldown_active():
            return False
        # Eligibility last: it reads the earn catalog from disk.
        return (state.logged_in
                and not state.in_jail
                and state.action_available()
                and state.in_home_city()
                and not state.hold_action_timer
                and is_eligible(state))

    def blocked_reasons(self, state):
        reasons = []
        import executor
        if executor.drug_manufacture_cooldown_active():
            reasons.append("Manufacture cooldown")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if not state.action_available():
            reasons.append("Action timer busy")
        if not state.in_home_city():
            reasons.append("Not in home city")
        reasons.extend(eligibility_reasons(state))
        if state.hold_action_timer:
            reasons.append("Action timer held")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("do_drug_manufacturing"), state)
