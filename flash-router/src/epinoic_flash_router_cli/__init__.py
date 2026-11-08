"""The flash router's runner: the router operated as a separate sub-agent from the command line
(``python -m epinoic_flash_router_cli <operation>``, or the ``epinoic-flash-router`` script). It is a package apart from
:mod:`epinoic_flash_router` so that the router itself stays pure (standard library, no process I/O): this runner reads
the request from standard input and writes the router's answer to standard output, and nothing else.
"""
