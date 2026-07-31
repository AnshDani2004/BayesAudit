"""Workflow architecture implementations."""

from bayesaudit.architectures.single_agent import SingleAgentWorkflow
from bayesaudit.architectures.structured import StructuredInheritanceWorkflow
from bayesaudit.architectures.unstructured import UnstructuredDelegationWorkflow
from bayesaudit.architectures.verified import VerifiedInheritanceWorkflow

__all__ = [
    "SingleAgentWorkflow",
    "StructuredInheritanceWorkflow",
    "UnstructuredDelegationWorkflow",
    "VerifiedInheritanceWorkflow",
]
