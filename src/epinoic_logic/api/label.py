"""Public API of the translator, label: the self-certification meaning label (meaning check, decision 1 of 25 November; API 1.5).

What an integrator needs to configure the label (its version and digest, the ``Labeller`` interface, the production default
``UnconfiguredLabeller``, the recorded and provider labellers, the model digest, and the default labeller's switch, read at call
time) and what the overseer's label gate and the sub-project test fixtures need (re-validation of a journaled record, its
states and kinds, the result type, and :func:`labelled_text`, the text a channel event's label read). Nothing here releases or
labels an answer on its own: the release paths call the label through the channel and the overseer.

TEST-ONLY (:data:`TEST_ONLY`): ``ReaderBackedLabeller`` (the faithful fake, which answers exactly as the rule reader reads),
``ScriptedLabeller`` (replies scripted by a test) and ``check_t24`` (the invariant test T24 applies to every receipt). They are
exported for the sub-projects' test fixtures and must never configure a deployment.

Part of :mod:`epinoic_logic.api` (``docs/PUBLIC_API.md``). Each name resolves to the internal module and attribute
listed below when it is imported; the internal name may differ (a name that is private inside the translator has a
public name here). Changing or removing a name here is a breaking change for every attached component.
"""
from __future__ import annotations

from ._lazy import exports

#: public name -> (internal module, attribute; None: the module itself)
EXPORTS: dict[str, tuple[str, str | None]] = {
    # the label's identity
    'LABEL_VERSION': ('epinoic_logic.selfcert_label', 'LABEL_VERSION'),
    'label_digest': ('epinoic_logic.selfcert_label', 'label_digest'),
    'model_digest': ('epinoic_logic.selfcert_label', 'model_digest'),
    # the labellers an integrator configures (the production default withholds every answer the reader passes)
    'Labeller': ('epinoic_logic.selfcert_label', 'Labeller'),
    'UnconfiguredLabeller': ('epinoic_logic.selfcert_label', 'UnconfiguredLabeller'),
    'RecordedLabeller': ('epinoic_logic.selfcert_label', 'RecordedLabeller'),
    'ProviderLabeller': ('epinoic_logic.selfcert_label', 'ProviderLabeller'),
    # the default labeller's switch: every release path calls default_labeller() at use time
    'default_labeller': ('epinoic_logic.selfcert_label', 'default_labeller'),
    'set_default_labeller': ('epinoic_logic.selfcert_label', 'set_default_labeller'),
    'restore_default_labeller': ('epinoic_logic.selfcert_label', 'restore_default_labeller'),
    # re-validation of a journaled record (the overseer's label gate)
    'revalidate': ('epinoic_logic.selfcert_label', 'revalidate'),
    'Revalidation': ('epinoic_logic.selfcert_label', 'Revalidation'),
    'LabelResult': ('epinoic_logic.selfcert_label', 'LabelResult'),
    'STATES': ('epinoic_logic.selfcert_label', 'STATES'),
    'KINDS': ('epinoic_logic.selfcert_label', 'KINDS'),
    'labelled_text': ('epinoic_logic.api._access', 'labelled_text'),
    # TEST-ONLY (TEST_ONLY below; docs/PUBLIC_API.md marks them)
    'ReaderBackedLabeller': ('epinoic_logic.selfcert_label.fakes', 'ReaderBackedLabeller'),
    'ScriptedLabeller': ('epinoic_logic.selfcert_label.fakes', 'ScriptedLabeller'),
    'check_t24': ('epinoic_logic.selfcert_label', 'check_t24'),
}

#: The names exported for test fixtures only: never a deployment's configuration.
TEST_ONLY: frozenset[str] = frozenset({"ReaderBackedLabeller", "ScriptedLabeller", "check_t24"})

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
