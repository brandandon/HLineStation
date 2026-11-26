"""Shared receiver-event acceptance policy, independent of Qt widgets."""

def is_current_event(event_generation, active_generation, receiver_present):
    """Reject signals queued by a retired receiver or after stop."""
    return receiver_present and event_generation == active_generation
