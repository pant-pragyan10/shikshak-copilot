"""LLM provider clients and the routing layer.

Every external LLM call in the codebase flows through
:class:`~teacher_copilot.providers.router.ProviderRouter`. No other module may
import a provider SDK directly.
"""
