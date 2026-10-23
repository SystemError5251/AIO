"""Terminal UI. Plain stdlib (input/print) so it runs on any Termux install.

The UI only talks to i18n, config and registry, so a richer front end
(Textual or Rich) can replace it later without touching the core.
"""
