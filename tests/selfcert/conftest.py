"""Isolation of the reader's digest memo between the tests of the rule reader.

Several tests here point the reader at a copy of its own files (``monkeypatch.setattr(selfcert, "_HERE", copy)``, and with it
``_external_root``) to show that a change to the rule's data or code moves :func:`epinoic_logic.selfcert.rules_digest`. The reader
memoises the closure and the digest in ``_CLOSURE_MEMO``, keyed on the stored state of the files and directories it read, but not
on where ``_HERE`` points: once the patch is undone and the copy is still on disk (pytest keeps ``tmp_path``), the memo still
holds the copy's closure, and every later ``rules_digest()`` in the same process returns the copy's digest (found when the
self-certification label's digest pin, which covers ``rules_digest()``, ran after ``test_fold_table.py`` in one process: the
pin failed there and passed alone). The same gap runs the other way: a test that points ``_HERE`` at a copy made by
``shutil.copytree`` (which keeps each file's modification time and size) finds a memo computed on the real package still
matching, since the memo's directories are the real ones and the copied modules have the stored state of the originals, so
``rules_digest()`` reuses the real tree's closure and ignores a module added to the copy (found when
``test_a_new_module_of_the_reader_changes_the_digest`` failed after other tests in one process and passed alone). Each test here
therefore starts from an EMPTY memo, discarded at teardown, so every closure and digest a test sees is computed from the files
under its own ``_HERE``, and a test can neither see nor leave another test's state. Nothing is asserted differently.

Since c3k (stage 2a of the meaning check, rules ``selfcert-5``) the cause is fixed in the reader: the memo is keyed on the
directories it reads (``selfcert._memo_roots``), so neither leak can happen (``test_c3k_reader.py`` pins it). The isolation here
stays: each test still starts from an empty memo.
"""
from __future__ import annotations

import pytest

import epinoic_logic.selfcert as _selfcert


@pytest.fixture(autouse=True)
def _own_digest_memo(monkeypatch):
    monkeypatch.setattr(_selfcert, "_CLOSURE_MEMO", {})
    yield
