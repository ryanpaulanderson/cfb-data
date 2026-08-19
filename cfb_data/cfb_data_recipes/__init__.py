"""Provide independently authored first-party analytics recipes.

The package root intentionally imports no recipe modules. Installed-provider
discovery imports the individual modules transactionally, while analysts may
import any recipe module directly.
"""
