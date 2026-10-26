"""Spawn-safe one-file process entry; full pixel buffers never cross IPC."""

import os
from pathlib import Path


def run_worker(source, destination, settings, limits, connection, stop):
    for variable in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[variable] = "1"
    try:
        from .errors import ConversionError
        from .formats import format_for
        from .models import ConversionSettings

        def progress(stage):
            connection.send({"stage": stage})

        def request_memory(message):
            connection.send(message)
            # A second worker may park here while the first finishes. The parent
            # still enforces the total file timeout and cancellation grace period.
            while not connection.poll(0.25):
                if stop.is_set():
                    raise ConversionError("Conversion cancelled while waiting for memory.")
            admitted = connection.recv().get("admitted")
            if stop.is_set():
                raise ConversionError("Conversion cancelled while waiting for memory.")
            if not admitted:
                raise ConversionError("Insufficient memory or workspace capacity for this image.")

        config = ConversionSettings(**settings)
        if format_for(config).engine == "raw":
            from .conversion import convert

            def admit(pixels):
                request_memory({"pixels": pixels})
        elif format_for(config).engine == "raster":
            from .raster import convert_raster as convert

            def admit(pixels):
                request_memory({"raster_pixels": pixels})
        else:
            from .documents import convert_document as convert

            def admit(budget):
                request_memory({"memory_request": budget})

        result = convert(
            Path(source),
            Path(destination),
            config,
            limits,
            progress,
            admit,
            stop.is_set,
        )
        connection.send({"result": result})
    except Exception as exc:
        from .errors import ConversionError

        message = str(exc) if isinstance(exc, ConversionError) else "File conversion failed safely."
        try:
            connection.send({"error": message})
        except (OSError, EOFError):
            pass
    finally:
        try:
            from .memory import process_memory

            memory = process_memory(os.getpid())
            connection.send(
                {
                    "memory": {
                        "end_rss_bytes": memory.rss,
                        "peak_rss_bytes": memory.peak_rss,
                        "peak_source": "Windows lifetime working set"
                        if os.name == "nt"
                        else "RSS samples",
                    }
                }
            )
        except Exception:
            # Optional diagnostics must not discard a validated result or prevent
            # closure when a process exits during the final memory measurement.
            pass
        connection.close()
