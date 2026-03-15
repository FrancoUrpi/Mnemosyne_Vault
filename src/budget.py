#!/usr/bin/env python3
"""
Budget Manager for Mnemosyne Knowledge Vault.

Manages token allocation for vault context within a fixed context window.
Handles budget allocation, tracking, and degradation when limits are hit.

Context Window Budget (128K model):
  System prompt base:     ~2,000 tokens
  Tool schemas:           ~15,000 tokens
  Conversation history:   ~50,000 tokens
  Vault context:          ~4,000 tokens  ← THIS MANAGES THIS
  Response generation:    ~20,000 tokens
  Buffer:                 ~37,000 tokens

Usage:
    from budget import BudgetManager

    budget = BudgetManager(total_budget=4000)
    budget.allocate("always", 500)   # _index.md + active_context.md
    budget.allocate("project", 500)  # project overview
    print(f"Remaining: {budget.remaining()} tokens")

    if budget.can_fit(800):
        budget.allocate("relevant", 800)
    else:
        print("Need to degrade")
"""

import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


# ─── Constants ────────────────────────────────────────────────────

# Default budget allocations (tokens)
DEFAULT_CONTEXT_WINDOW = 128_000

DEFAULT_ALLOCATIONS = {
    "system_prompt":    2_000,
    "tool_schemas":     15_000,
    "conversation":     50_000,
    "vault":            4_000,   # ← Our budget
    "response":         20_000,
    "buffer":           37_000,
}

# Vault sub-allocations (within vault budget)
VAULT_SUB_ALLOCATIONS = {
    "always":      500,   # _index.md + active_context.md
    "project":     500,   # project overview
    "relevant":    2500,  # scored relevant files
    "linked":      500,   # explicitly requested via links
}

# Degradation levels
class DegradationLevel(Enum):
    NONE = "none"           # Full budget available
    SQUEEZE = "squeeze"     # Reduce vault budget by 50%
    MINIMAL = "minimal"     # Only always-load files
    OFF = "off"             # No vault context


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class TokenEstimate:
    """Token usage estimate for a piece of content."""
    text: str
    char_count: int
    token_estimate: int
    method: str = "char_div_4"  # Estimation method used


@dataclass
class AllocationRecord:
    """Record of a budget allocation."""
    category: str
    tokens: int
    description: str


@dataclass
class BudgetStatus:
    """Current budget status snapshot."""
    total_budget: int
    allocated: int
    remaining: int
    utilization_pct: float
    degradation: DegradationLevel
    allocations: List[AllocationRecord]
    can_fit_more: bool


# ─── Budget Manager ───────────────────────────────────────────────

class BudgetManager:
    """
    Manages token budget for vault context loading.

    Tracks allocations, enforces limits, and handles degradation.
    """

    def __init__(
        self,
        total_budget: int = 4000,
        context_window: int = DEFAULT_CONTEXT_WINDOW,
        allocations: Optional[Dict[str, int]] = None,
    ):
        self.total_budget = total_budget
        self.context_window = context_window
        self.base_allocations = allocations or VAULT_SUB_ALLOCATIONS.copy()
        self.records: List[AllocationRecord] = []
        self._degradation = DegradationLevel.NONE

    @property
    def allocated(self) -> int:
        """Total tokens allocated so far."""
        return sum(r.tokens for r in self.records)

    @property
    def remaining(self) -> int:
        """Tokens remaining in budget."""
        return max(0, self.total_budget - self.allocated)

    @property
    def degradation(self) -> DegradationLevel:
        """Current degradation level."""
        return self._degradation

    # ─── Core Operations ──────────────────────────────────────────

    def allocate(self, category: str, tokens: int, description: str = "") -> bool:
        """
        Allocate tokens from the budget.

        Returns True if allocation succeeded, False if would exceed budget.
        """
        if tokens <= 0:
            return True

        if self.allocated + tokens > self.total_budget:
            return False

        self.records.append(AllocationRecord(
            category=category,
            tokens=tokens,
            description=description or category,
        ))
        return True

    def allocate_text(self, category: str, text: str, description: str = "") -> Tuple[bool, int]:
        """
        Allocate based on text content. Estimates tokens, then allocates.

        Returns (success, token_estimate).
        """
        tokens = self.estimate_tokens(text)
        success = self.allocate(category, tokens, description)
        return success, tokens

    def can_fit(self, tokens: int) -> bool:
        """Check if a number of tokens would fit in remaining budget."""
        return self.allocated + tokens <= self.total_budget

    def can_fit_text(self, text: str) -> bool:
        """Check if text would fit in remaining budget."""
        return self.can_fit(self.estimate_tokens(text))

    def reset(self) -> None:
        """Clear all allocations and reset to full budget."""
        self.records.clear()
        self._degradation = DegradationLevel.NONE

    # ─── Budget for Categories ────────────────────────────────────

    def get_category_budget(self, category: str) -> int:
        """Get the budget allocated to a category."""
        base = self.base_allocations.get(category, 0)

        # Apply degradation
        if self._degradation == DegradationLevel.SQUEEZE:
            if category in ("relevant", "linked"):
                base = int(base * 0.5)
        elif self._degradation == DegradationLevel.MINIMAL:
            if category not in ("always",):
                base = 0
        elif self._degradation == DegradationLevel.OFF:
            base = 0

        return base

    def get_category_used(self, category: str) -> int:
        """Get tokens used by a category so far."""
        return sum(r.tokens for r in self.records if r.category == category)

    def get_category_remaining(self, category: str) -> int:
        """Get remaining tokens for a category."""
        budget = self.get_category_budget(category)
        used = self.get_category_used(category)
        return max(0, budget - used)

    # ─── Degradation ──────────────────────────────────────────────

    def set_degradation(self, level: DegradationLevel) -> None:
        """Set degradation level."""
        self._degradation = level

    def auto_degrade(self) -> DegradationLevel:
        """
        Automatically set degradation based on utilization.
        Returns the degradation level applied.
        """
        util = self.utilization

        if util < 0.7:
            self._degradation = DegradationLevel.NONE
        elif util < 0.9:
            self._degradation = DegradationLevel.SQUEEZE
        elif util < 1.0:
            self._degradation = DegradationLevel.MINIMAL
        else:
            self._degradation = DegradationLevel.OFF

        return self._degradation

    # ─── Status ───────────────────────────────────────────────────

    @property
    def utilization(self) -> float:
        """Budget utilization as a fraction (0.0 to 1.0+)."""
        if self.total_budget == 0:
            return 1.0
        return self.allocated / self.total_budget

    def get_status(self) -> BudgetStatus:
        """Get current budget status snapshot."""
        return BudgetStatus(
            total_budget=self.total_budget,
            allocated=self.allocated,
            remaining=self.remaining,
            utilization_pct=self.utilization * 100,
            degradation=self._degradation,
            allocations=list(self.records),
            can_fit_more=self.remaining > 100,  # 100 token minimum
        )

    def get_breakdown(self) -> Dict[str, int]:
        """Get allocation breakdown by category."""
        breakdown = {}
        for r in self.records:
            breakdown[r.category] = breakdown.get(r.category, 0) + r.tokens
        return breakdown

    # ─── Token Estimation ─────────────────────────────────────────

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Estimate token count from text.
        Uses ~4 chars per token heuristic (conservative for English).
        """
        return max(1, len(text) // 4)

    @staticmethod
    def estimate_tokens_precise(text: str) -> TokenEstimate:
        """More detailed token estimate with metadata."""
        char_count = len(text)
        token_estimate = max(1, char_count // 4)
        return TokenEstimate(
            text=text[:50] + "..." if len(text) > 50 else text,
            char_count=char_count,
            token_estimate=token_estimate,
        )

    # ─── Context Window Helpers ───────────────────────────────────

    @classmethod
    def for_context_window(
        cls,
        window_size: int = DEFAULT_CONTEXT_WINDOW,
        vault_pct: float = 0.03125,  # ~4000/128000
    ) -> "BudgetManager":
        """
        Create a budget manager sized for a specific context window.

        Args:
            window_size: Total context window in tokens
            vault_pct: Percentage of window for vault (default ~3%)
        """
        vault_budget = int(window_size * vault_pct)
        return cls(total_budget=vault_budget, context_window=window_size)

    @classmethod
    def for_model(cls, model_name: str) -> "BudgetManager":
        """Create budget manager for a known model."""
        model_windows = {
            "gpt-4": 8_192,
            "gpt-4-32k": 32_768,
            "gpt-4-turbo": 128_000,
            "gpt-4o": 128_000,
            "claude-3": 200_000,
            "claude-3-opus": 200_000,
            "claude-3-sonnet": 200_000,
            "claude-3-haiku": 200_000,
            "kimi-k2.5": 128_000,
        }

        # Fuzzy match
        window = DEFAULT_CONTEXT_WINDOW
        for model, size in model_windows.items():
            if model in model_name.lower():
                window = size
                break

        return cls.for_context_window(window)


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "status":
        budget = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
        mgr = BudgetManager(total_budget=budget)

        # Simulate typical allocation
        mgr.allocate("always", 200, "_index.md + active_context.md")
        mgr.allocate("project", 450, "project overview")
        mgr.allocate("relevant", 1800, "3 relevant files")
        mgr.allocate("linked", 300, "1 linked file")

        status = mgr.get_status()
        print(f"Budget: {status.total_budget} tokens")
        print(f"Used:   {status.allocated} tokens ({status.utilization_pct:.1f}%)")
        print(f"Remain: {status.remaining} tokens")
        print(f"Degradation: {status.degradation.value}")
        print()
        print("Breakdown:")
        for cat, tokens in mgr.get_breakdown().items():
            print(f"  {cat:12} {tokens:6} tokens")

    elif cmd == "estimate":
        text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Sample text for estimation"
        est = BudgetManager.estimate_tokens_precise(text)
        print(f"Text: {est.text}")
        print(f"Chars: {est.char_count}")
        print(f"Estimated tokens: {est.token_estimate}")

    elif cmd == "model":
        model = sys.argv[2] if len(sys.argv) > 2 else "kimi-k2.5"
        mgr = BudgetManager.for_model(model)
        print(f"Model: {model}")
        print(f"Context window: {mgr.context_window:,} tokens")
        print(f"Vault budget: {mgr.total_budget:,} tokens")

    else:
        print("Commands: status [budget], estimate <text>, model <model_name>")
