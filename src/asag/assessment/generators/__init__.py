"""Question generators — one module per question type (mcq, short).

Generators are registered into the question-type registry in
``asag.assessment.__init__``; they are not auto-imported here to keep this
package importable without triggering registry side effects.
"""

from __future__ import annotations
