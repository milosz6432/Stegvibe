"""Built-in plugins. Add new built-ins to BUILTIN_PLUGINS (explicit list: no dynamic code loading)."""

from spectra.plugins.builtin.integrity import IntegrityVerifyPlugin

BUILTIN_PLUGINS = [IntegrityVerifyPlugin]
