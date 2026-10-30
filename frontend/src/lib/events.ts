import type { JsonObject } from "@/lib/api";

/** Default payloads for one-click event injection. Keyed by backend event type. */
export const EVENT_PRESETS: Record<string, JsonObject> = {
  order_created: { channel: "web" },
  payment_confirmed: { method: "upi", amount: 2499 },
  payment_failed: { reason: "card_declined" },
  shipment_created: { carrier: "BlueDart", tracking_id: "BD123456789IN" },
  shipment_delayed: { carrier: "BlueDart", new_eta_days: 3, reason: "weather" },
  out_for_delivery: { courier: "Ravi", eta: "today 6pm" },
  delivered: { signed_by: "customer" },
  refund_requested: { reason: "Item arrived damaged" },
  refund_completed: { amount: 2499 },
  order_cancelled: { reason: "customer_request" },
  customer_message_received: { message: "Where is my order? It was supposed to arrive yesterday." },
  no_update_for_n_hours: { hours: 30 },
};

/** Events that need attention get visual weight in the injector. */
export const CRITICAL_EVENTS = new Set([
  "payment_failed",
  "shipment_delayed",
  "refund_requested",
  "customer_message_received",
  "no_update_for_n_hours",
]);

export const TERMINAL_EVENTS = new Set(["delivered", "refund_completed", "order_cancelled"]);

export interface ScenarioStep {
  type: string;
  payload: JsonObject;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  steps: ScenarioStep[];
}

const step = (type: string, payload: JsonObject = EVENT_PRESETS[type] ?? {}): ScenarioStep => ({ type, payload });

export const SCENARIOS: Scenario[] = [
  {
    id: "happy",
    name: "Happy path",
    description: "Paid, shipped, delivered. The agent should mostly sleep, then close.",
    steps: [step("payment_confirmed"), step("shipment_created"), step("out_for_delivery"), step("delivered")],
  },
  {
    id: "rough",
    name: "Rough delivery",
    description: "A delay followed by an anxious customer message.",
    steps: [
      step("payment_confirmed"),
      step("shipment_created"),
      step("shipment_delayed"),
      step("customer_message_received"),
    ],
  },
  {
    id: "payment",
    name: "Payment trouble",
    description: "Payment fails, the order goes quiet, then a refund request.",
    steps: [step("payment_failed"), step("no_update_for_n_hours"), step("refund_requested")],
  },
];

/** Gap between scenario events, so each one is visible in the timeline during a demo. */
export const SCENARIO_STEP_DELAY_MS = 4000;
