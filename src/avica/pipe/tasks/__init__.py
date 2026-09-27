"""Task entry points, loaded on demand to keep CLI startup lightweight."""

__all__ = ["exec_FFT_fringefit"]


def __getattr__(name):
    if name == "exec_FFT_fringefit":
        from avica.pipe.tasks.fringefit import exec_FFT_fringefit

        return exec_FFT_fringefit
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
