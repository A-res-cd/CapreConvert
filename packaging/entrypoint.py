"""PyInstaller entry point: dispatch frozen children before importing the application."""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from localraw.__main__ import main

    main()
