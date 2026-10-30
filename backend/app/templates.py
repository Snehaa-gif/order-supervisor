"""Built-in supervisor templates, seeded into the database on startup."""

from app.agent import tools as t
from app.domain import SupervisorConfig, WakeAggressiveness

TEMPLATES: tuple[SupervisorConfig, ...] = (
    SupervisorConfig(
        id="tpl-standard",
        name="Standard Order Guardian",
        base_instruction=(
            "Make sure this order reaches the customer smoothly. Keep the customer informed about anything "
            "that affects them (failed payments, delays), escalate problems you cannot solve to the right team, "
            "and leave internal notes so the operations team understands what happened. Do not over-message: "
            "routine progress needs no customer contact."
        ),
        tools=list(t.ALL_ACTION_TOOLS),
        default_wake_minutes=5,
        max_sleep_minutes=60,
        wake_aggressiveness=WakeAggressiveness.BALANCED,
    ),
    SupervisorConfig(
        id="tpl-vip",
        name="VIP White-Glove Supervisor",
        base_instruction=(
            "This is a high-value customer. Be proactive: confirm key milestones to the customer, react to any "
            "sign of trouble immediately, and escalate with high severity when the experience is at risk."
        ),
        tools=list(t.ALL_ACTION_TOOLS),
        default_wake_minutes=2,
        max_sleep_minutes=20,
        wake_aggressiveness=WakeAggressiveness.HIGH,
    ),
    SupervisorConfig(
        id="tpl-risk",
        name="Fraud & Risk Watch",
        base_instruction=(
            "Watch this order for payment and fraud risk. Never contact the customer yourself. Flag anything "
            "suspicious for manual review and escalate to the fraud or payments team with clear reasoning."
        ),
        tools=[t.CREATE_INTERNAL_NOTE, t.ESCALATE_ISSUE, t.MARK_ORDER_FOR_REVIEW],
        default_wake_minutes=10,
        max_sleep_minutes=120,
        wake_aggressiveness=WakeAggressiveness.LOW,
    ),
)
